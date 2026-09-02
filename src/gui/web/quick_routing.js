// Draws the Quick Routing matrix from the quick_routing.state payload.
(function (global) {
  "use strict";

  var METHOD = "quick_routing.state";

  var BUS = "bus";
  var CALLS = "calls";
  var COLORS = "colors";
  var CONFIRMATION = "confirmation";
  var LABELS = "labels";
  var LAYOUT = "layout";
  var NAMES = "names";
  var PLATFORM_VALUES = "platform_values";
  var RATE = "rate";
  var REFUSALS = "refusals";
  var ROWS = "rows";
  var SCOPE_IDS = "scope_ids";
  var SCROLL = "scroll";
  var SELECTED = "selected";
  var STOPS = "stops";
  var STYLES = "styles";
  var TAB = "tab";
  var TEXTS = "texts";
  var TOOLTIPS = "tooltips";
  var WIRING = "wiring";

  // DECLARED_FIELDS names every top-level field the surface publishes.
  var DECLARED_FIELDS = [
    BUS,
    CALLS,
    COLORS,
    CONFIRMATION,
    LABELS,
    LAYOUT,
    NAMES,
    PLATFORM_VALUES,
    RATE,
    REFUSALS,
    ROWS,
    SCOPE_IDS,
    SCROLL,
    SELECTED,
    STOPS,
    STYLES,
    TAB,
    TEXTS,
    TOOLTIPS,
    WIRING
  ];

  var LIST_SURFACE = "list_surface";
  var LIST_BORDER = "list_border";
  var LIST_TEXT = "list_text";
  var INPUT_SURFACE = "input_surface";
  var INPUT_BORDER = "input_border";
  var COLOR_NAMES_FIELD = "names";
  var COLOR_FIELDS = [
    LIST_SURFACE,
    LIST_BORDER,
    LIST_TEXT,
    INPUT_SURFACE,
    INPUT_BORDER,
    COLOR_NAMES_FIELD
  ];

  var OUTER_MARGINS = "outer_margins";
  var OUTER_SPACING = "outer_spacing";
  var COLUMN_MARGINS = "column_margins";
  var COLUMN_SPACING = "column_spacing";
  var COLUMN_STRETCH = "column_stretch";
  var RATE_MARGINS = "rate_margins";
  var BUTTON_MARGINS = "button_margins";
  var BUTTON_SPACING = "button_spacing";
  var BUTTON_ROW_STRETCHES = "button_row_stretches";
  var LAYOUT_FIELDS = [
    OUTER_MARGINS,
    OUTER_SPACING,
    COLUMN_MARGINS,
    COLUMN_SPACING,
    COLUMN_STRETCH,
    RATE_MARGINS,
    BUTTON_MARGINS,
    BUTTON_SPACING,
    BUTTON_ROW_STRETCHES
  ];

  var LIST_STYLE = "list";
  var RATE_ZONE_STYLE = "rate_zone";
  var RATE_LABEL_STYLE = "rate_label";
  var RATE_INPUT_STYLE = "rate_input";
  var FRAME_SHAPE = "frame_shape";
  var SIZE_POLICY = "size_policy";
  var STYLE_FIELDS = [
    LIST_STYLE,
    RATE_ZONE_STYLE,
    RATE_LABEL_STYLE,
    RATE_INPUT_STYLE,
    FRAME_SHAPE,
    SIZE_POLICY
  ];

  var RATE_LABEL_TEXT = "rate_label";
  var DEFAULT_RATE = "default_rate";
  var BUTTONS = "buttons";
  var TEXT_FIELDS = [RATE_LABEL_TEXT, DEFAULT_RATE, BUTTONS];

  var SOURCE_TOOLTIP = "source";
  var DEST_TOOLTIP = "destination";
  var RATE_TOOLTIP = "rate";
  var TOOLTIP_FIELDS = [SOURCE_TOOLTIP, DEST_TOOLTIP, RATE_TOOLTIP];

  var SELECTION_MODE = "selection_mode";
  var SELECTION_MODE_VALUE = "selection_mode_value";
  var SCROLL_POLICY = "scroll_policy";
  var SCROLL_POLICY_VALUE = "scroll_policy_value";
  var ALIGNMENT = "alignment";
  var ALIGNMENT_VALUE = "alignment_value";
  var USER_ROLE = "user_role";
  var USER_ROLE_VALUE = "user_role_value";
  var USER_CHECKABLE_VALUE = "user_checkable_value";
  var ROW_FLAGS = "row_flags";
  var CHECKED = "checked";
  var UNCHECKED = "unchecked";
  var PLATFORM_FIELDS = [
    SELECTION_MODE,
    SELECTION_MODE_VALUE,
    SCROLL_POLICY,
    SCROLL_POLICY_VALUE,
    ALIGNMENT,
    ALIGNMENT_VALUE,
    USER_ROLE,
    USER_ROLE_VALUE,
    USER_CHECKABLE_VALUE,
    ROW_FLAGS,
    CHECKED,
    UNCHECKED
  ];

  var LABEL_FORMAT = "format";
  var SHORT_ID_LENGTH = "short_id_length";
  var MASK_FIELD_ID = "mask_field_id";
  var SYMBOL_MASK = "symbol_mask";
  var SHORT_ID_MASK = "short_id_mask";
  var UNKNOWN_SYMBOL = "unknown_symbol";
  var EMPTY_SYMBOL = "empty_symbol";
  var LABEL_FIELDS = [
    LABEL_FORMAT,
    SHORT_ID_LENGTH,
    MASK_FIELD_ID,
    SYMBOL_MASK,
    SHORT_ID_MASK,
    UNKNOWN_SYMBOL,
    EMPTY_SYMBOL
  ];

  var RATE_SUFFIX = "suffix";
  var MIN_PCT = "min_pct";
  var MAX_PCT = "max_pct";
  var ZERO_PCT = "zero_pct";
  var RATE_TEXT = "text";
  var RATE_FIELDS = [RATE_SUFFIX, MIN_PCT, MAX_PCT, ZERO_PCT, RATE_TEXT];

  var REFUSAL_TITLE = "title";
  var NOT_A_NUMBER = "not_a_number";
  var OUT_OF_RANGE = "out_of_range";
  var NO_SOURCES = "no_sources";
  var NO_DESTINATIONS = "no_destinations";
  var ZERO_RATE = "zero_rate";
  var SELF_WIRE_CONNECT = "self_wire_connect";
  var SELF_WIRE_DISCONNECT = "self_wire_disconnect";
  var SAVE_FAILED = "save_failed";
  var STEP_REFUSAL = "step";
  var REFUSAL_FIELDS = [
    REFUSAL_TITLE,
    NOT_A_NUMBER,
    OUT_OF_RANGE,
    NO_SOURCES,
    NO_DESTINATIONS,
    ZERO_RATE,
    SELF_WIRE_CONNECT,
    SELF_WIRE_DISCONNECT,
    SAVE_FAILED,
    STEP_REFUSAL
  ];

  var CREATE_VERB = "create_verb";
  var DISCONNECT_VERB = "disconnect_verb";
  var CONFIRM_TITLE = "title";
  var CONFIRM_BODY = "body";
  var PLURAL_SUFFIX = "plural_suffix";
  var SINGULAR_COUNT = "singular_count";
  var CREATE_WARNING = "create_warning";
  var DISCONNECT_WARNING = "disconnect_warning";
  var CONNECT_DETAIL = "connect_detail";
  var DISCONNECT_DETAIL = "disconnect_detail";
  var ALL_TITLE = "all_title";
  var ALL_BODY = "all_body";
  var CONFIRMATION_FIELDS = [
    CREATE_VERB,
    DISCONNECT_VERB,
    CONFIRM_TITLE,
    CONFIRM_BODY,
    PLURAL_SUFFIX,
    SINGULAR_COUNT,
    CREATE_WARNING,
    DISCONNECT_WARNING,
    CONNECT_DETAIL,
    DISCONNECT_DETAIL,
    ALL_TITLE,
    ALL_BODY
  ];

  var WIRE_CREATED = "created";
  var WIRE_REMOVED = "removed";
  var BUS_TOPICS = "topics";
  var BUS_FIELDS = [WIRE_CREATED, WIRE_REMOVED, BUS_TOPICS];

  var ACTIONS = "actions";
  var ACTION_ORDER = "action_order";
  var BUTTON_KEYS = "button_keys";
  var SIGNALS = "signals";
  var TIMERS = "timers";
  var TIMER_DELAYS_MS = "timer_delays_ms";
  var SINGLE_SHOT_TIMERS = "single_shot_timers";
  var SCROLL_RESTORE_TIMER = "scroll_restore_timer";
  var SCREEN_ELEMENTS = "screen_elements";
  var WIRING_FIELDS = [
    ACTIONS,
    ACTION_ORDER,
    BUTTON_KEYS,
    SIGNALS,
    TIMERS,
    TIMER_DELAYS_MS,
    SINGLE_SHOT_TIMERS,
    SCROLL_RESTORE_TIMER,
    SCREEN_ELEMENTS
  ];

  var COLUMNS = "columns";
  var SOURCE_COLUMN = "source_column";
  var DEST_COLUMN = "dest_column";
  var ROUTES = "routes";
  var RATE_PARAM = "rate_param";
  var STEPS_PARAM = "steps_param";
  var CHECKED_PARAMS = "checked_params";
  var PANEL_CALLS = "panel_calls";
  var BRANCHES = "branches";
  var STEPS = "steps";
  var NAME_FIELDS = [
    COLUMNS,
    SOURCE_COLUMN,
    DEST_COLUMN,
    ROUTES,
    RATE_PARAM,
    STEPS_PARAM,
    CHECKED_PARAMS,
    PANEL_CALLS,
    BRANCHES,
    STEPS
  ];

  var DEFERRED = "deferred";
  var SCROLL_FIELDS = [DEFERRED];

  var SOURCES = "sources";
  var DESTINATIONS = "destinations";
  var SELECTED_FIELDS = [SOURCES, DESTINATIONS];

  var WIDGET_SYMBOLS = "widget_symbols";
  var STATE_SYMBOLS = "state_symbols";
  var WIDGET_SYMBOL_ORDER = "widget_symbol_order";
  var STATE_SYMBOL_ORDER = "state_symbol_order";
  var CLEARED_PAIRS = "cleared_pairs";
  var ANSWERS = "answers";
  var DEFAULT_ANSWER = "default_answer";
  var MASKED = "masked";
  var WIDGET_REFUSAL = "widget_refusal";
  var ASKED = "asked";
  var SAVED = "saved";
  var EMITTED = "emitted";
  var CLEARED = "cleared";
  var SHOWN = "shown";
  var TAB_FIELDS = [
    WIDGET_SYMBOLS,
    STATE_SYMBOLS,
    WIDGET_SYMBOL_ORDER,
    STATE_SYMBOL_ORDER,
    CLEARED_PAIRS,
    ANSWERS,
    DEFAULT_ANSWER,
    MASKED,
    WIDGET_REFUSAL,
    ASKED,
    SAVED,
    EMITTED,
    CLEARED,
    SHOWN,
    CALLS
  ];

  var BAG_FIELDS = {};
  BAG_FIELDS[COLORS] = COLOR_FIELDS;
  BAG_FIELDS[LAYOUT] = LAYOUT_FIELDS;
  BAG_FIELDS[STYLES] = STYLE_FIELDS;
  BAG_FIELDS[TEXTS] = TEXT_FIELDS;
  BAG_FIELDS[TOOLTIPS] = TOOLTIP_FIELDS;
  BAG_FIELDS[PLATFORM_VALUES] = PLATFORM_FIELDS;
  BAG_FIELDS[LABELS] = LABEL_FIELDS;
  BAG_FIELDS[RATE] = RATE_FIELDS;
  BAG_FIELDS[REFUSALS] = REFUSAL_FIELDS;
  BAG_FIELDS[CONFIRMATION] = CONFIRMATION_FIELDS;
  BAG_FIELDS[BUS] = BUS_FIELDS;
  BAG_FIELDS[WIRING] = WIRING_FIELDS;
  BAG_FIELDS[NAMES] = NAME_FIELDS;
  BAG_FIELDS[SCROLL] = SCROLL_FIELDS;
  BAG_FIELDS[SELECTED] = SELECTED_FIELDS;
  BAG_FIELDS[TAB] = TAB_FIELDS;

  // LIST_FIELDS and BAG_SHAPES name the shape each top-level field arrives in.
  var LIST_FIELDS = [CALLS, SCOPE_IDS, STOPS];
  var BAG_SHAPES = Object.keys(BAG_FIELDS).concat([ROWS]);

  var ROW_LABEL = "label";
  var ROW_BOT_ID = "bot_id";
  var ROW_CHECK_STATE = "check_state";
  var ROW_FLAG_FIELD = "flags";
  var ROW_MEMBERS = [ROW_LABEL, ROW_BOT_ID, ROW_CHECK_STATE, ROW_FLAG_FIELD];

  var MISSING_FAULT = "missing";
  var NULL_FAULT = "null";
  var NOT_A_LIST_FAULT = "not-a-list";
  var NOT_AN_OBJECT_FAULT = "not-an-object";
  var WRONG_TYPE_FAULT = "wrong-type";
  var QT_COLOUR_FAULT = "qt-colour";
  var MARKUP_FAULT = "markup";
  var UNKNOWN_BOT_FAULT = "unknown-bot";
  var DISAGREES_FAULT = "disagrees";
  var NO_SHEET_SOURCE_FAULT = "no-sheet-source";

  var NULL_KIND = "null";
  var OBJECT_KIND = "object";
  var ROW_AT = "row:";
  var SAVED_AT = "saved:";
  var EMITTED_AT = "emitted:";
  var NO_BRIDGE = "the preload bridge is not present";

  // Qt reads an eight-digit hex colour alpha first, and CSS reads it last.
  var HEX_ARGB = "AARRGGBB";
  // Qt counts an rgba alpha in bytes, and CSS counts it as a fraction.
  var RGBA_OPEN = "rgba(";
  // MARKUP_OPEN starts a tag a rich-text widget would read as formatting.
  var MARKUP_OPEN = "<";

  var EMPTY = "";
  var GAP = " ";
  var HASH = "#";
  var DOT = ".";
  var COMMA = ",";
  var CLOSE = ")";
  var COLON = ":";
  var SEMICOLON = ";";
  var PATH_SPLIT = ".";
  var PX = "px";
  var VAR_OPEN = "var(--";
  var VAR_SPLIT = ", ";
  var VAR_CLOSE = ")";
  var CALC_OPEN = "calc(";
  // PX_FACTOR turns a unitless token into a CSS length inside calc.
  var PX_FACTOR = " * 1px)";

  // A gap borrows only from spacing, because a radius means something else.
  var SPACE_GROUPS = ["spacing"];

  // ITEM_SELECTOR and HOVER_SELECTOR name the two sub-blocks of the list sheet.
  var ITEM_SELECTOR = "QListWidget::item";
  var HOVER_SELECTOR = "QListWidget::item:hover";

  var ROW = "row";
  var COLUMN = "column";
  var FLEX = "flex";
  var HIDDEN = "hidden";
  var AUTO = "auto";
  var NOWRAP = "nowrap";
  var NONE = "none";
  var CENTER = "center";
  var ELLIPSIS = "ellipsis";
  var POINTER = "pointer";
  var TEXT_TYPE = "text";
  var CHECKBOX_TYPE = "checkbox";
  var BUTTON_TYPE = "button";
  var DIV_TAG = "div";
  var SPAN_TAG = "span";
  var INPUT_TAG = "input";
  var BUTTON_TAG = "button";

  var MATRIX_CLASS = "acervator-quick-routing";
  var INPUT_CLASS = "acervator-quick-routing-input";

  var MATRIX_PART = "quick-routing";
  var COLUMNS_PART = "columns";
  var LIST_PART = "bot-list";
  var ROW_PART = "list-row";
  var CHECK_PART = "row-check";
  var ROW_LABEL_PART = "row-label";
  var RATE_ZONE_PART = "rate-zone";
  var RATE_LABEL_PART = "rate-label";
  var RATE_INPUT_PART = "rate-input";
  var RATE_STRETCH_PART = "rate-stretch";
  var BUTTON_ROW_PART = "button-row";
  var LEAD_STRETCH_PART = "lead-stretch";
  var TAIL_STRETCH_PART = "tail-stretch";
  var BUTTON_PART = "action-button";
  var NOTICES_PART = "notices";
  var NOTICE_PART = "notice";

  var PART_ATTR = "data-part";
  var SLOT_ATTR = "data-slot";
  var KEY_ATTR = "data-key";
  var COLUMN_ATTR = "data-column";
  var INDEX_ATTR = "data-index";
  var ACTION_ATTR = "data-action";
  var STEP_ATTR = "data-step";
  var COUNT_ATTR = "data-count";
  var SCROLL_ATTR = "data-scroll";
  var DEFERRED_ATTR = "data-deferred";
  var CHECKED_ATTR = "data-checked";
  var FLAGS_ATTR = "data-flags";
  var ARIA_LABEL = "aria-label";

  var ZERO = Number(EMPTY);
  var ONE = Number(true);

  var held = null;
  var routingFaults = [];
  var loadFault = null;
  var asked = null;
  var dispatched = [];
  var roots = [];

  function isPlainObject(value) {
    return value !== null && typeof value === "object" && !Array.isArray(value);
  }

  function owns(bag, name) {
    return Object.prototype.hasOwnProperty.call(bag, name);
  }

  function objectField(model, name) {
    return isPlainObject(model) && isPlainObject(model[name]) ? model[name] : {};
  }

  function listField(model, name) {
    return isPlainObject(model) && Array.isArray(model[name]) ? model[name] : [];
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

  // text answers nothing for a null, so an attribute is left off.
  function text(value) {
    return value === null || value === undefined ? undefined : String(value);
  }

  // label answers nothing for an empty tooltip, so no title is written.
  function label(value) {
    return typeof value === "string" && value.length ? value : undefined;
  }

  function fault(where, name, kind, detail) {
    return { where: where, field: name, fault: kind, detail: detail };
  }

  function afterFirst(value, splitter) {
    var parts = String(value).split(splitter);
    parts.shift();
    return parts;
  }

  function carries(value, splitter) {
    return Boolean(afterFirst(value, splitter).length);
  }

  function merged(base, extra) {
    Object.keys(extra).forEach(function (name) {
      base[name] = extra[name];
    });
    return base;
  }

  // shared_widgets.js owns the one-carrier rule that names a token.
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

  // The token name for a value, only from groups meaning the same thing.
  function variableInGroups(value, groups) {
    var name = variableFor(value);
    if (name === undefined || !inGroups(name, groups)) {
      return undefined;
    }
    return name;
  }

  // A token holds a bare number, so calc scales it to a CSS length.
  function length(value) {
    if (value === null || value === undefined) {
      return undefined;
    }
    var name = variableInGroups(value, SPACE_GROUPS);
    if (name === undefined) {
      return String(value) + PX;
    }
    return (
      CALC_OPEN + VAR_OPEN + name + VAR_SPLIT + String(value) + VAR_CLOSE + PX_FACTOR
    );
  }

  // A colour painted through the one token that carries it.
  function colour(value) {
    var name = variableFor(value);
    if (name === undefined) {
      return text(value);
    }
    return VAR_OPEN + name + VAR_SPLIT + String(value) + VAR_CLOSE;
  }

  // header_strip.js owns the sheet parser and the camel-case rule.
  function declarations(sheet) {
    var api = global.acervatorHeader;
    if (!api || typeof api.declarations !== "function") {
      return [];
    }
    return api.declarations(sheet);
  }

  function stateRules(sheet) {
    var api = global.acervatorHeader;
    if (!api || typeof api.stateRules !== "function") {
      return [];
    }
    return api.stateRules(sheet);
  }

  function headerStyleOf(sheet) {
    var api = global.acervatorHeader;
    if (!api || typeof api.styleOf !== "function") {
      return {};
    }
    return api.styleOf(sheet);
  }

  function hasSheetSource() {
    var api = global.acervatorHeader;
    return Boolean(api && typeof api.styleOf === "function");
  }

  // The first hex word of one value, empty when the value carries none.
  function hexWord(value) {
    var parts = afterFirst(value, HASH);
    if (!parts.length) {
      return EMPTY;
    }
    return String(parts.shift()).trim().split(GAP).shift();
  }

  // Whether one value counts its alpha in bytes, as Qt does and CSS does not.
  function byteAlpha(value) {
    var parts = afterFirst(value, RGBA_OPEN);
    if (!parts.length) {
      return false;
    }
    var fields = String(parts.shift()).split(CLOSE).shift().split(COMMA);
    fields.shift();
    fields.shift();
    fields.shift();
    var alpha = fields.shift();
    if (alpha === undefined || String(alpha).trim() === EMPTY) {
      return false;
    }
    return !carries(alpha, DOT) && !isNaN(Number(alpha));
  }

  // The reason CSS would read one value as a different colour.
  function qtColour(value) {
    if (hexWord(value).length === HEX_ARGB.length) {
      return HEX_ARGB;
    }
    if (byteAlpha(value)) {
      return RGBA_OPEN;
    }
    return undefined;
  }

  // The sheet without the declarations CSS would read as another colour.
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
    return headerStyleOf(keptSheet(sheet));
  }

  // The style one named sub-block paints, matched whole so hover cannot bleed.
  function partStyle(sheet, selector) {
    var found = {};
    stateRules(sheet).forEach(function (rule) {
      if (String(rule.selector).trim() !== selector) {
        return;
      }
      merged(found, headerStyleOf(keptSheet(rule.body)));
    });
    return found;
  }

  // The surface publishes a margin in left, top, right and bottom order.
  var PADDING_SIDES = ["paddingLeft", "paddingTop", "paddingRight", "paddingBottom"];

  function marginStyle(margins) {
    var style = {};
    var values = Array.isArray(margins) ? margins : [];
    PADDING_SIDES.forEach(function (side, at) {
      if (at < values.length) {
        style[side] = length(values[at]);
      }
    });
    return style;
  }

  function boxStyle(margins, spacing, direction) {
    var style = marginStyle(margins);
    style.display = FLEX;
    style.flexDirection = direction;
    style.gap = length(spacing);
    return style;
  }

  function outerStyle(model) {
    var box = objectField(model, LAYOUT);
    var style = boxStyle(box[OUTER_MARGINS], box[OUTER_SPACING], COLUMN);
    style.flex = AUTO;
    style.minWidth = ZERO;
    style.overflow = HIDDEN;
    return style;
  }

  function columnsStyle(model) {
    var box = objectField(model, LAYOUT);
    var style = boxStyle(box[COLUMN_MARGINS], box[COLUMN_SPACING], ROW);
    style.flex = AUTO;
    style.minHeight = ZERO;
    return style;
  }

  function buttonRowStyle(model) {
    var box = objectField(model, LAYOUT);
    var style = boxStyle(box[BUTTON_MARGINS], box[BUTTON_SPACING], ROW);
    style.alignItems = CENTER;
    return style;
  }

  // A Qt zone takes its width from its stretch, and clips rather than growing.
  function zoneStyle(model) {
    var box = objectField(model, LAYOUT);
    return {
      flexGrow: text(box[COLUMN_STRETCH]),
      flexShrink: text(box[COLUMN_STRETCH]),
      flexBasis: ZERO,
      minWidth: ZERO,
      overflow: HIDDEN
    };
  }

  // The style scrolls when it must, and never lets a row be selected.
  function listStyle(model) {
    var style = merged(zoneStyle(model), styleOf(objectField(model, STYLES)[LIST_STYLE]));
    style.display = FLEX;
    style.flexDirection = COLUMN;
    style.overflowY = AUTO;
    style.overflowX = HIDDEN;
    style.userSelect = NONE;
    style.flexGrow = text(objectField(model, LAYOUT)[COLUMN_STRETCH]);
    style.flexShrink = text(objectField(model, LAYOUT)[COLUMN_STRETCH]);
    style.flexBasis = ZERO;
    style.minWidth = ZERO;
    return style;
  }

  // A row keeps to one line and cuts a long name off, as the delegate does.
  function rowStyle(model) {
    var style = partStyle(objectField(model, STYLES)[LIST_STYLE], ITEM_SELECTOR);
    style.display = FLEX;
    style.flexDirection = ROW;
    style.alignItems = CENTER;
    style.flex = NONE;
    style.whiteSpace = NOWRAP;
    style.overflow = HIDDEN;
    style.textOverflow = ELLIPSIS;
    style.cursor = POINTER;
    return style;
  }

  function hoverStyle(model) {
    return partStyle(objectField(model, STYLES)[LIST_STYLE], HOVER_SELECTOR);
  }

  function rowLabelStyle() {
    return {
      overflow: HIDDEN,
      whiteSpace: NOWRAP,
      textOverflow: ELLIPSIS,
      minWidth: ZERO
    };
  }

  function rateZoneStyle(model) {
    var box = objectField(model, LAYOUT);
    var style = merged(
      zoneStyle(model),
      styleOf(objectField(model, STYLES)[RATE_ZONE_STYLE])
    );
    merged(style, boxStyle(box[RATE_MARGINS], ZERO, COLUMN));
    style.flexGrow = text(box[COLUMN_STRETCH]);
    style.flexShrink = text(box[COLUMN_STRETCH]);
    style.flexBasis = ZERO;
    style.minWidth = ZERO;
    return style;
  }

  function rateLabelStyle(model) {
    var style = styleOf(objectField(model, STYLES)[RATE_LABEL_STYLE]);
    style.textAlign = CENTER;
    style.userSelect = NONE;
    return style;
  }

  function rateInputStyle(model) {
    var style = styleOf(objectField(model, STYLES)[RATE_INPUT_STYLE]);
    style.textAlign = CENTER;
    style.minWidth = ZERO;
    return style;
  }

  function element() {
    return global.React.createElement.apply(null, arguments);
  }

  function hooks() {
    return global.React;
  }

  function dispatch(name, params) {
    dispatched.push({ action: name, params: params });
    if (!global.acervator || typeof global.acervator.call !== "function") {
      return null;
    }
    return global.acervator.call(METHOD, copyOf(params));
  }

  function columnNames(model) {
    return listField(objectField(model, NAMES), COLUMNS);
  }

  function rowsOf(model, column) {
    return listField(objectField(model, ROWS), column);
  }

  // Every bot ticked in one column, taken from the rows in the order drawn.
  function checkedOf(model, column) {
    var ticked = objectField(model, PLATFORM_VALUES)[CHECKED];
    var found = [];
    rowsOf(model, column).forEach(function (row) {
      if (isPlainObject(row) && row[ROW_CHECK_STATE] === ticked && row[ROW_BOT_ID]) {
        found.push(String(row[ROW_BOT_ID]));
      }
    });
    return found;
  }

  // The ticks both columns send, so one change carries the other column too.
  function tickParams(model, column, botId, ticking) {
    var wanted = listField(objectField(model, NAMES), CHECKED_PARAMS);
    var params = {};
    columnNames(model).forEach(function (name, at) {
      var picked = checkedOf(model, String(name));
      if (String(name) === column) {
        picked = picked.filter(function (one) {
          return one !== String(botId);
        });
        if (ticking) {
          picked.push(String(botId));
        }
      }
      params[wanted[at]] = picked;
    });
    return params;
  }

  // What a button click carries: the step, the typed rate and both tick lists.
  function pressParams(model, step, typed) {
    var names = objectField(model, NAMES);
    var wanted = listField(names, CHECKED_PARAMS);
    var params = {};
    params[names[STEPS_PARAM]] = [step];
    params[names[RATE_PARAM]] = typed;
    columnNames(model).forEach(function (name, at) {
      params[wanted[at]] = checkedOf(model, String(name));
    });
    return params;
  }

  // Names the symbol bag order from the list beside it, never from its keys.
  function symbolNames(model, which) {
    var bag = objectField(model, TAB);
    var order = which === WIDGET_SYMBOLS ? WIDGET_SYMBOL_ORDER : STATE_SYMBOL_ORDER;
    return listField(bag, order).map(function (one) {
      return String(one);
    });
  }

  function ListRow(props) {
    var model = props.model;
    var row = isPlainObject(props.row) ? props.row : {};
    var ticked = objectField(model, PLATFORM_VALUES)[CHECKED];
    var state = hooks().useState(false);
    var hovered = state.shift();
    var setHovered = state.shift();
    var style = rowStyle(model);
    if (hovered === true) {
      merged(style, hoverStyle(model));
    }
    var rowProps = {
      style: style,
      onMouseOver: function () {
        setHovered(true);
      },
      onMouseOut: function () {
        setHovered(false);
      }
    };
    rowProps[PART_ATTR] = ROW_PART;
    rowProps[KEY_ATTR] = text(row[ROW_BOT_ID]);
    rowProps[INDEX_ATTR] = String(props.at);
    rowProps[COLUMN_ATTR] = props.column;
    rowProps[CHECKED_ATTR] = String(row[ROW_CHECK_STATE] === ticked);
    rowProps[FLAGS_ATTR] = text(row[ROW_FLAG_FIELD]);
    var checkProps = {
      type: CHECKBOX_TYPE,
      className: INPUT_CLASS,
      checked: row[ROW_CHECK_STATE] === ticked,
      onChange: function (event) {
        props.onTick(String(row[ROW_BOT_ID]), Boolean(event.target.checked));
      }
    };
    checkProps[PART_ATTR] = CHECK_PART;
    checkProps[KEY_ATTR] = text(row[ROW_BOT_ID]);
    checkProps[COLUMN_ATTR] = props.column;
    checkProps[ARIA_LABEL] = label(text(row[ROW_LABEL]));
    var labelProps = { style: rowLabelStyle() };
    labelProps[PART_ATTR] = ROW_LABEL_PART;
    labelProps[KEY_ATTR] = text(row[ROW_BOT_ID]);
    labelProps[COLUMN_ATTR] = props.column;
    return element(
      DIV_TAG,
      rowProps,
      element(INPUT_TAG, checkProps, null),
      element(SPAN_TAG, labelProps, text(row[ROW_LABEL]))
    );
  }

  // BotList holds one column and puts its saved offset back after layout.
  function BotList(props) {
    var model = props.model;
    var rows = rowsOf(model, props.column);
    var offset = objectField(model, SCROLL)[props.column];
    var listProps = {
      className: MATRIX_CLASS,
      style: listStyle(model),
      title: label(objectField(model, TOOLTIPS)[props.tooltip]),
      ref: function (node) {
        if (node !== null && typeof offset === "number") {
          node.scrollTop = offset;
        }
      }
    };
    listProps[PART_ATTR] = LIST_PART;
    listProps[COLUMN_ATTR] = props.column;
    listProps[COUNT_ATTR] = String(rows.length);
    listProps[SCROLL_ATTR] = text(offset);
    listProps[DEFERRED_ATTR] = String(
      listField(objectField(model, SCROLL), DEFERRED).filter(function (one) {
        return Array.isArray(one) && one.shift() === props.column;
      }).length
    );
    listProps[ARIA_LABEL] = label(objectField(model, TOOLTIPS)[props.tooltip]);
    return element(
      DIV_TAG,
      listProps,
      rows.map(function (row, at) {
        return element(ListRow, {
          key: String(at),
          at: at,
          row: row,
          column: props.column,
          model: model,
          onTick: props.onTick
        });
      })
    );
  }

  function RateZone(props) {
    var model = props.model;
    var typed = props.typed;
    var zoneProps = { className: MATRIX_CLASS, style: rateZoneStyle(model) };
    zoneProps[PART_ATTR] = RATE_ZONE_PART;
    zoneProps[KEY_ATTR] = text(objectField(model, STYLES)[FRAME_SHAPE]);
    var labelProps = { style: rateLabelStyle(model) };
    labelProps[PART_ATTR] = RATE_LABEL_PART;
    var inputProps = {
      type: TEXT_TYPE,
      className: INPUT_CLASS,
      style: rateInputStyle(model),
      title: label(objectField(model, TOOLTIPS)[RATE_TOOLTIP]),
      value: typed === undefined ? EMPTY : typed,
      onChange: function (event) {
        props.onRate(event.target.value);
      }
    };
    inputProps[PART_ATTR] = RATE_INPUT_PART;
    inputProps[ARIA_LABEL] = label(objectField(model, TEXTS)[RATE_LABEL_TEXT]);
    var stretchProps = { style: { flex: AUTO } };
    stretchProps[PART_ATTR] = RATE_STRETCH_PART;
    return element(
      DIV_TAG,
      zoneProps,
      element(DIV_TAG, labelProps, text(objectField(model, TEXTS)[RATE_LABEL_TEXT])),
      element(INPUT_TAG, inputProps, null),
      element(DIV_TAG, stretchProps, null)
    );
  }

  function ActionButton(props) {
    var model = props.model;
    var buttonProps = {
      className: INPUT_CLASS,
      type: BUTTON_TYPE,
      title: label(objectField(model, TOOLTIPS)[props.name]),
      onClick: function () {
        props.onPress(props.name, props.at);
      }
    };
    buttonProps[PART_ATTR] = BUTTON_PART;
    buttonProps[KEY_ATTR] = props.name;
    buttonProps[ACTION_ATTR] = text(props.action);
    buttonProps[STEP_ATTR] = props.name;
    buttonProps[INDEX_ATTR] = String(props.at);
    buttonProps[ARIA_LABEL] = label(objectField(model, TOOLTIPS)[props.name]);
    return element(
      BUTTON_TAG,
      buttonProps,
      text(objectField(model, TEXTS)[props.name])
    );
  }

  function Stretch(props) {
    var stretchProps = { style: { flex: AUTO } };
    stretchProps[PART_ATTR] = props.part;
    return element(DIV_TAG, stretchProps, null);
  }

  function ButtonRow(props) {
    var model = props.model;
    var wiring = objectField(model, WIRING);
    var keys = listField(wiring, BUTTON_KEYS);
    var order = listField(wiring, ACTION_ORDER);
    var rowProps = { className: MATRIX_CLASS, style: buttonRowStyle(model) };
    rowProps[PART_ATTR] = BUTTON_ROW_PART;
    rowProps[COUNT_ATTR] = String(keys.length);
    var drawn = [element(Stretch, { key: LEAD_STRETCH_PART, part: LEAD_STRETCH_PART })];
    keys.forEach(function (name, at) {
      drawn.push(
        element(ActionButton, {
          key: String(name),
          at: at,
          name: String(name),
          action: order[at],
          model: model,
          onPress: props.onPress
        })
      );
    });
    drawn.push(element(Stretch, { key: TAIL_STRETCH_PART, part: TAIL_STRETCH_PART }));
    return element(DIV_TAG, rowProps, drawn);
  }

  // Every notice the panel showed the operator, drawn as words and not as markup.
  function Notices(props) {
    var model = props.model;
    var shown = listField(objectField(model, TAB), SHOWN);
    var noticesProps = { className: MATRIX_CLASS, style: { display: FLEX, flexDirection: COLUMN } };
    noticesProps[PART_ATTR] = NOTICES_PART;
    noticesProps[COUNT_ATTR] = String(shown.length);
    return element(
      DIV_TAG,
      noticesProps,
      shown.map(function (one, at) {
        var entry = Array.isArray(one) ? one.slice() : [];
        var kind = entry.shift();
        var title = entry.shift();
        var body = entry.shift();
        var noticeProps = {
          key: String(at),
          style: { whiteSpace: NOWRAP, overflow: HIDDEN }
        };
        noticeProps[PART_ATTR] = NOTICE_PART;
        noticeProps[KEY_ATTR] = text(kind);
        noticeProps[INDEX_ATTR] = String(at);
        return element(DIV_TAG, noticeProps, text(title) + GAP + text(body));
      })
    );
  }

  // Matrix keeps the typed rate, as the Qt rate box does until a click reads it.
  function Matrix(props) {
    var model = isPlainObject(props.model) ? props.model : {};
    var names = objectField(model, NAMES);
    var wiring = objectField(model, WIRING);
    var tooltips = [SOURCE_TOOLTIP, DEST_TOOLTIP];
    var state = hooks().useState(text(objectField(model, RATE)[RATE_TEXT]));
    var typed = state.shift();
    var setTyped = state.shift();
    var matrixProps = { className: MATRIX_CLASS, style: outerStyle(model) };
    matrixProps[PART_ATTR] = MATRIX_PART;
    matrixProps[SLOT_ATTR] = MATRIX_PART;
    matrixProps[COUNT_ATTR] = String(listField(model, SCOPE_IDS).length);
    var columnsProps = { className: MATRIX_CLASS, style: columnsStyle(model) };
    columnsProps[PART_ATTR] = COLUMNS_PART;
    var zones = [];
    columnNames(model).forEach(function (name, at) {
      zones.push(
        element(BotList, {
          key: String(name),
          column: String(name),
          tooltip: tooltips[at],
          model: model,
          onTick: function (botId, ticking) {
            dispatch(
              listField(names, CHECKED_PARAMS)[at],
              tickParams(model, String(name), botId, ticking)
            );
          }
        })
      );
      if (at === ZERO) {
        zones.push(
          element(RateZone, {
            key: RATE_ZONE_PART,
            model: model,
            typed: typed,
            onRate: function (entered) {
              setTyped(entered);
              var params = {};
              params[names[RATE_PARAM]] = entered;
              dispatch(names[RATE_PARAM], params);
            }
          })
        );
      }
    });
    return element(
      DIV_TAG,
      matrixProps,
      element(DIV_TAG, columnsProps, zones),
      element(ButtonRow, {
        key: BUTTON_ROW_PART,
        model: model,
        onPress: function (step, at) {
          dispatch(
            listField(wiring, ACTION_ORDER)[at],
            pressParams(model, step, typed)
          );
        }
      }),
      element(Notices, { key: NOTICES_PART, model: model })
    );
  }

  function checkFields(model) {
    DECLARED_FIELDS.forEach(function (name) {
      if (!owns(model, name)) {
        routingFaults.push(fault(null, name, MISSING_FAULT, null));
        return;
      }
      if (model[name] === null) {
        routingFaults.push(fault(null, name, NULL_FAULT, null));
      }
    });
  }

  // A scalar arriving where a list or a bag belongs slips past every member walk.
  function checkShapes(model) {
    LIST_FIELDS.forEach(function (name) {
      if (owns(model, name) && !Array.isArray(model[name])) {
        routingFaults.push(fault(null, name, NOT_A_LIST_FAULT, kindOf(model[name])));
      }
    });
    BAG_SHAPES.forEach(function (name) {
      if (owns(model, name) && !isPlainObject(model[name])) {
        routingFaults.push(fault(null, name, NOT_AN_OBJECT_FAULT, kindOf(model[name])));
      }
    });
  }

  function checkBags(model) {
    Object.keys(BAG_FIELDS).forEach(function (where) {
      var bag = objectField(model, where);
      BAG_FIELDS[where].forEach(function (name) {
        if (!owns(bag, name)) {
          routingFaults.push(fault(where, name, MISSING_FAULT, null));
          return;
        }
        if (bag[name] === null && name !== WIDGET_REFUSAL) {
          routingFaults.push(fault(where, name, NULL_FAULT, null));
        }
      });
    });
  }

  // A wrong type is named only where a published value of the same meaning holds it.
  function checkTypeAgainst(where, name, carried, against) {
    if (against === null || against === undefined || carried === undefined) {
      return;
    }
    if (kindOf(carried) !== kindOf(against)) {
      routingFaults.push(fault(where, name, WRONG_TYPE_FAULT, kindOf(carried)));
    }
  }

  function checkTypes(model) {
    var rate = objectField(model, RATE);
    var texts = objectField(model, TEXTS);
    var platform = objectField(model, PLATFORM_VALUES);
    checkTypeAgainst(RATE, RATE_TEXT, rate[RATE_TEXT], texts[DEFAULT_RATE]);
    checkTypeAgainst(RATE, MIN_PCT, rate[MIN_PCT], rate[MAX_PCT]);
    checkTypeAgainst(RATE, ZERO_PCT, rate[ZERO_PCT], platform[UNCHECKED]);
    columnNames(model).forEach(function (column) {
      rowsOf(model, column).forEach(function (row, at) {
        var where = ROW_AT + column;
        if (!isPlainObject(row)) {
          routingFaults.push(fault(where, String(at), WRONG_TYPE_FAULT, kindOf(row)));
          return;
        }
        ROW_MEMBERS.forEach(function (name) {
          if (!owns(row, name)) {
            routingFaults.push(fault(where, name, MISSING_FAULT, String(at)));
          }
        });
        checkTypeAgainst(where, ROW_LABEL, row[ROW_LABEL], texts[DEFAULT_RATE]);
        checkTypeAgainst(
          where,
          ROW_CHECK_STATE,
          row[ROW_CHECK_STATE],
          platform[UNCHECKED]
        );
        checkTypeAgainst(where, ROW_FLAG_FIELD, row[ROW_FLAG_FIELD], platform[ROW_FLAGS]);
      });
    });
  }

  // Every colour and every sheet CSS would read as a different colour.
  function checkColours(model) {
    var colors = objectField(model, COLORS);
    if (!hasSheetSource()) {
      routingFaults.push(fault(null, STYLES, NO_SHEET_SOURCE_FAULT, null));
    }
    listField(colors, COLOR_NAMES_FIELD).forEach(function (name) {
      var named = qtColour(colors[name]);
      if (named !== undefined) {
        routingFaults.push(fault(COLORS, String(name), QT_COLOUR_FAULT, named));
      }
    });
    var styles = objectField(model, STYLES);
    STYLE_FIELDS.forEach(function (name) {
      declarations(styles[name]).forEach(function (one) {
        var named = qtColour(one.value);
        if (named !== undefined) {
          routingFaults.push(fault(STYLES, name, QT_COLOUR_FAULT, named));
        }
      });
      stateRules(styles[name]).forEach(function (rule) {
        declarations(rule.body).forEach(function (one) {
          var named = qtColour(one.value);
          if (named !== undefined) {
            routingFaults.push(fault(STYLES, name, QT_COLOUR_FAULT, named));
          }
        });
      });
    });
  }

  // Names caller text carrying a tag, which this file draws as characters.
  function checkMarkup(model) {
    var typed = objectField(model, RATE)[RATE_TEXT];
    if (typeof typed === "string" && carries(typed, MARKUP_OPEN)) {
      routingFaults.push(fault(RATE, RATE_TEXT, MARKUP_FAULT, MARKUP_OPEN));
    }
    listField(objectField(model, TAB), SHOWN).forEach(function (one, at) {
      var entry = Array.isArray(one) ? one.slice() : [];
      entry.forEach(function (part) {
        if (typeof part === "string" && carries(part, MARKUP_OPEN)) {
          routingFaults.push(fault(SHOWN, String(at), MARKUP_FAULT, MARKUP_OPEN));
        }
      });
    });
    columnNames(model).forEach(function (column) {
      rowsOf(model, column).forEach(function (row, at) {
        var drawn = isPlainObject(row) ? row[ROW_LABEL] : undefined;
        if (typeof drawn === "string" && carries(drawn, MARKUP_OPEN)) {
          routingFaults.push(fault(ROW_AT + column, String(at), MARKUP_FAULT, MARKUP_OPEN));
        }
      });
    });
  }

  // Names a wire whose end is a bot the panel never put on screen.
  function checkRoutes(model) {
    var known = listField(model, SCOPE_IDS).map(function (one) {
      return String(one);
    });
    function name(where, botId) {
      if (known.indexOf(String(botId)) < ZERO) {
        routingFaults.push(fault(where, String(botId), UNKNOWN_BOT_FAULT, null));
      }
    }
    listField(objectField(model, TAB), SAVED).forEach(function (one, at) {
      var pass = Array.isArray(one) ? one : [];
      pass.forEach(function (group) {
        (Array.isArray(group) ? group : []).forEach(function (wire) {
          var ends = Array.isArray(wire) ? wire.slice() : [];
          name(SAVED_AT + String(at), ends.shift());
          name(SAVED_AT + String(at), ends.shift());
        });
      });
    });
    listField(objectField(model, TAB), EMITTED).forEach(function (one, at) {
      var entry = Array.isArray(one) ? one.slice() : [];
      entry.shift();
      (Array.isArray(entry[ZERO]) ? entry[ZERO] : []).forEach(function (pair) {
        var named = Array.isArray(pair) ? pair.slice() : [];
        var key = named.shift();
        var value = named.shift();
        if (key !== undefined && String(key) !== EMPTY && typeof value === "string") {
          name(EMITTED_AT + String(at), value);
        }
      });
    });
  }

  // The ticks this module counts, held against the selected list the surface sent.
  function checkSelection(model) {
    var selected = objectField(model, SELECTED);
    var wanted = [SOURCES, DESTINATIONS];
    columnNames(model).forEach(function (column, at) {
      var mine = checkedOf(model, String(column));
      var theirs = listField(selected, wanted[at]).map(function (one) {
        return String(one);
      });
      if (mine.join(COMMA) !== theirs.join(COMMA)) {
        routingFaults.push(
          fault(SELECTED, wanted[at], DISAGREES_FAULT, mine.join(COMMA))
        );
      }
    });
  }

  function heldFieldCount(model) {
    return DECLARED_FIELDS.filter(function (name) {
      return owns(model, name);
    }).length;
  }

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

  function declaredRowCount(model) {
    return columnNames(model).length * listField(model, SCOPE_IDS).length;
  }

  function heldRowCount(model) {
    var total = ZERO;
    columnNames(model).forEach(function (column) {
      total = total + rowsOf(model, String(column)).length;
    });
    return total;
  }

  // Counts the fields, the nested fields, the rows and the buttons apart.
  function report(model) {
    var wiring = objectField(model, WIRING);
    return {
      declared: {
        fields: DECLARED_FIELDS.length,
        nested: nestedPaths().length,
        rows: declaredRowCount(model),
        buttons: listField(wiring, BUTTON_KEYS).length
      },
      held: {
        fields: heldFieldCount(model),
        nested: heldNestedPaths(model).length,
        rows: heldRowCount(model),
        buttons: listField(objectField(model, TEXTS), BUTTONS).length
      },
      faults: routingFaults.slice()
    };
  }

  function setRouting(model) {
    dispatched = [];
    if (!isPlainObject(model)) {
      held = null;
      routingFaults = [fault(null, null, NOT_AN_OBJECT_FAULT, kindOf(model))];
      return { declared: null, held: null, faults: routingFaults.slice() };
    }
    held = { model: model };
    routingFaults = [];
    checkFields(model);
    checkShapes(model);
    checkBags(model);
    checkTypes(model);
    checkColours(model);
    checkMarkup(model);
    checkRoutes(model);
    checkSelection(model);
    return report(model);
  }

  // loadRouting asks METHOD once, clearing asked so a refusal retries.
  function loadRouting(params) {
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
        setRouting(model);
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

  function declaredNames() {
    return DECLARED_FIELDS.slice();
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
    return held === null ? [] : copyOf(listField(held.model, name));
  }

  function rows(column) {
    return held === null ? [] : copyOf(rowsOf(held.model, column));
  }

  // The bot names of one column in the order drawn, never taken from a bag.
  function rowOrder(column) {
    return rows(column).map(function (row) {
      return isPlainObject(row) ? text(row[ROW_BOT_ID]) : undefined;
    });
  }

  function checked(column) {
    return held === null ? [] : checkedOf(held.model, column);
  }

  function symbolOrder(which) {
    return held === null ? [] : symbolNames(held.model, which);
  }

  function actions() {
    return bag(WIRING)[ACTIONS];
  }

  function actionOrder() {
    return held === null ? [] : listField(objectField(held.model, WIRING), ACTION_ORDER);
  }

  function buttonKeys() {
    return held === null ? [] : listField(objectField(held.model, WIRING), BUTTON_KEYS);
  }

  function sent() {
    return dispatched.slice();
  }

  // Every payload value's JavaScript type, by dotted path, scalars included.
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
    return routingFaults.slice();
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

  function renderMatrix(target, model) {
    var drawn = model;
    if (!isPlainObject(drawn)) {
      drawn = held === null ? null : held.model;
    }
    return draw(target, element(Matrix, { model: drawn }));
  }

  function forget() {
    held = null;
    routingFaults = [];
    loadFault = null;
    asked = null;
    dispatched = [];
  }

  global.acervatorSetQuickRouting = setRouting;
  global.acervatorLoadQuickRouting = loadRouting;
  global.acervatorQuickRouting = {
    method: METHOD,
    Matrix: Matrix,
    BotList: BotList,
    ListRow: ListRow,
    RateZone: RateZone,
    ButtonRow: ButtonRow,
    ActionButton: ActionButton,
    Notices: Notices,
    Stretch: Stretch,
    payload: payload,
    declaredNames: declaredNames,
    nestedNames: nestedNames,
    field: field,
    bag: bag,
    list: list,
    rows: rows,
    rowOrder: rowOrder,
    checked: checked,
    symbolOrder: symbolOrder,
    actions: actions,
    actionOrder: actionOrder,
    buttonKeys: buttonKeys,
    sent: sent,
    outerStyle: outerStyle,
    columnsStyle: columnsStyle,
    buttonRowStyle: buttonRowStyle,
    zoneStyle: zoneStyle,
    listStyle: listStyle,
    rowStyle: rowStyle,
    hoverStyle: hoverStyle,
    rowLabelStyle: rowLabelStyle,
    rateZoneStyle: rateZoneStyle,
    rateLabelStyle: rateLabelStyle,
    rateInputStyle: rateInputStyle,
    marginStyle: marginStyle,
    styleOf: styleOf,
    partStyle: partStyle,
    keptSheet: keptSheet,
    declarations: declarations,
    stateRules: stateRules,
    qtColour: qtColour,
    variableFor: variableFor,
    variableInGroups: variableInGroups,
    colour: colour,
    length: length,
    kinds: kinds,
    faults: faults,
    loadError: loadError,
    isLoaded: isLoaded,
    renderMatrix: renderMatrix,
    forget: forget
  };
})(window);
