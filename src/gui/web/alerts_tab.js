// The Notifications and Alerts tab, as the Python surface serves it.
(function (global) {
  "use strict";

  var METHOD = "alerts_tab.state";

  var ACCESSIBLE_NAME = "accessible_name";
  var ACK_PATH = "ack_path";
  var ACK_PATHS = "ack_paths";
  var ACTIONS = "actions";
  var ALIGNMENT = "alignment";
  var ALIGNMENT_VALUE = "alignment_value";
  var ALTERNATING_ROW_COLORS = "alternating_row_colors";
  var BUS_TOPICS = "bus_topics";
  var BUTTON_NAMES = "button_names";
  var BUTTON_TEXTS = "button_texts";
  var BUTTONS_ENABLED = "buttons_enabled";
  var CALLS = "calls";
  var CELL_COLORS = "cell_colors";
  var CELL_ELIDE = "cell_elide";
  var CHANNELS = "channels";
  var CHAT_ID = "chat_id";
  var COLORED_FROM_COLUMN = "colored_from_column";
  var CONFIG_KEYS = "config_keys";
  var CONTENT_MARGINS = "content_margins";
  var CONTENT_SPACING = "content_spacing";
  var DEFAULT_PRIORITY = "default_priority";
  var ECHO_MODES = "echo_modes";
  var ECHO_VALUES = "echo_values";
  var EDIT_TRIGGERS_DEFAULT = "edit_triggers_default";
  var EDIT_TRIGGERS_DEFAULT_VALUE = "edit_triggers_default_value";
  var EDIT_TRIGGERS_NONE = "edit_triggers_none";
  var EDIT_TRIGGERS_NONE_VALUE = "edit_triggers_none_value";
  var FOCUS_POLICY = "focus_policy";
  var FOCUS_POLICY_VALUE = "focus_policy_value";
  var FORM_LABEL_ALIGNMENT = "form_label_alignment";
  var FORM_LABEL_ALIGNMENT_VALUE = "form_label_alignment_value";
  var FORM_SPACING = "form_spacing";
  var GROUP_TITLES = "group_titles";
  var HAS_MANAGER = "has_manager";
  var HEADER_ALIGNMENT = "header_alignment";
  var HEADER_ALIGNMENT_VALUE = "header_alignment_value";
  var HEADER_RESIZE_MODE = "header_resize_mode";
  var HEADER_RESIZE_VALUE = "header_resize_value";
  var HISTORY_COLUMN_COUNT = "history_column_count";
  var HISTORY_COLUMNS = "history_columns";
  var HISTORY_LIMIT = "history_limit";
  var HISTORY_ROWS = "history_rows";
  var LABEL_ALIGNMENT = "label_alignment";
  var LABEL_ALIGNMENT_VALUE = "label_alignment_value";
  var LABEL_WORD_WRAP = "label_word_wrap";
  var MESSAGE_MAX_CHARS = "message_max_chars";
  var METHOD_FIELD = "method";
  var NO_PATH = "no_path";
  var PANE_MARGINS = "pane_margins";
  var PANE_SPACING = "pane_spacing";
  var PHONE = "phone";
  var PLACEHOLDERS = "placeholders";
  var PRIORITIES = "priorities";
  var PRIORITY_COLORS = "priority_colors";
  var PRIORITY_COLUMN = "priority_column";
  var PRIORITY_FALLBACK_COLOR = "priority_fallback_color";
  var REFRESH_PATH = "refresh_path";
  var REFRESH_PATHS = "refresh_paths";
  var ROUTED_CHANNELS = "routed_channels";
  var ROW_LABELS = "row_labels";
  var RULE_KEYS = "rule_keys";
  var RULES_COLUMN_COUNT = "rules_column_count";
  var RULES_COLUMNS = "rules_columns";
  var RULES_ROWS = "rules_rows";
  var SAFE_TEXT_FORMAT = "safe_text_format";
  var SAVE_PATH = "save_path";
  var SAVE_PATHS = "save_paths";
  var SCROLL_BAR_POLICY = "scroll_bar_policy";
  var SELECTION_BEHAVIOR = "selection_behavior";
  var SELECTION_MODE = "selection_mode";
  var SHOW_GRID = "show_grid";
  var SKIN = "skin";
  var SMS_STATUS_STYLE = "sms_status_style";
  var SMS_STATUS_TEXT = "sms_status_text";
  var SPLITTER_CHILDREN_COLLAPSIBLE = "splitter_children_collapsible";
  var SPLITTER_HANDLE_WIDTH = "splitter_handle_width";
  var SPLITTER_ORIENTATION = "splitter_orientation";
  var SPLITTER_ORIENTATION_VALUE = "splitter_orientation_value";
  var SPLITTER_SIZES = "splitter_sizes";
  var STATUS_STYLE = "status_style";
  var STATUS_TEXT = "status_text";
  var STYLES = "styles";
  var TAB_STYLE_SHEET = "tab_style_sheet";
  var TABLE_WORD_WRAP = "table_word_wrap";
  var TELEGRAM_STATUS_STYLE = "telegram_status_style";
  var TELEGRAM_STATUS_TEXT = "telegram_status_text";
  var TELEGRAM_TEST_PRIORITY = "telegram_test_priority";
  var TEST_PATH = "test_path";
  var TEST_PATHS = "test_paths";
  var TEXT_FORMAT = "text_format";
  var TEXT_SELECTABLE = "text_selectable";
  var TEXTS = "texts";
  var TIMER_DELAYS_MS = "timer_delays_ms";
  var TIMERS = "timers";
  var TOKEN = "token";
  var UNREAD_STYLE = "unread_style";
  var UNREAD_TEXT = "unread_text";
  var VERTICAL_HEADER_VISIBLE = "vertical_header_visible";
  var WIDGET_CHILDREN = "widget_children";
  var WIDGET_INDEX = "widget_index";
  var WIDGET_KINDS = "widget_kinds";
  var WIDGET_NAMES = "widget_names";
  var WIDGET_PARENTS = "widget_parents";
  var WIDGETS = "widgets";

  var DECLARED_FIELDS = [
    ACCESSIBLE_NAME,
    ACK_PATH,
    ACK_PATHS,
    ACTIONS,
    ALIGNMENT,
    ALIGNMENT_VALUE,
    ALTERNATING_ROW_COLORS,
    BUS_TOPICS,
    BUTTON_NAMES,
    BUTTON_TEXTS,
    BUTTONS_ENABLED,
    CALLS,
    CELL_COLORS,
    CELL_ELIDE,
    CHANNELS,
    CHAT_ID,
    COLORED_FROM_COLUMN,
    CONFIG_KEYS,
    CONTENT_MARGINS,
    CONTENT_SPACING,
    DEFAULT_PRIORITY,
    ECHO_MODES,
    ECHO_VALUES,
    EDIT_TRIGGERS_DEFAULT,
    EDIT_TRIGGERS_DEFAULT_VALUE,
    EDIT_TRIGGERS_NONE,
    EDIT_TRIGGERS_NONE_VALUE,
    FOCUS_POLICY,
    FOCUS_POLICY_VALUE,
    FORM_LABEL_ALIGNMENT,
    FORM_LABEL_ALIGNMENT_VALUE,
    FORM_SPACING,
    GROUP_TITLES,
    HAS_MANAGER,
    HEADER_ALIGNMENT,
    HEADER_ALIGNMENT_VALUE,
    HEADER_RESIZE_MODE,
    HEADER_RESIZE_VALUE,
    HISTORY_COLUMN_COUNT,
    HISTORY_COLUMNS,
    HISTORY_LIMIT,
    HISTORY_ROWS,
    LABEL_ALIGNMENT,
    LABEL_ALIGNMENT_VALUE,
    LABEL_WORD_WRAP,
    MESSAGE_MAX_CHARS,
    METHOD_FIELD,
    NO_PATH,
    PANE_MARGINS,
    PANE_SPACING,
    PHONE,
    PLACEHOLDERS,
    PRIORITIES,
    PRIORITY_COLORS,
    PRIORITY_COLUMN,
    PRIORITY_FALLBACK_COLOR,
    REFRESH_PATH,
    REFRESH_PATHS,
    ROUTED_CHANNELS,
    ROW_LABELS,
    RULE_KEYS,
    RULES_COLUMN_COUNT,
    RULES_COLUMNS,
    RULES_ROWS,
    SAFE_TEXT_FORMAT,
    SAVE_PATH,
    SAVE_PATHS,
    SCROLL_BAR_POLICY,
    SELECTION_BEHAVIOR,
    SELECTION_MODE,
    SHOW_GRID,
    SKIN,
    SMS_STATUS_STYLE,
    SMS_STATUS_TEXT,
    SPLITTER_CHILDREN_COLLAPSIBLE,
    SPLITTER_HANDLE_WIDTH,
    SPLITTER_ORIENTATION,
    SPLITTER_ORIENTATION_VALUE,
    SPLITTER_SIZES,
    STATUS_STYLE,
    STATUS_TEXT,
    STYLES,
    TAB_STYLE_SHEET,
    TABLE_WORD_WRAP,
    TELEGRAM_STATUS_STYLE,
    TELEGRAM_STATUS_TEXT,
    TELEGRAM_TEST_PRIORITY,
    TEST_PATH,
    TEST_PATHS,
    TEXT_FORMAT,
    TEXT_SELECTABLE,
    TEXTS,
    TIMER_DELAYS_MS,
    TIMERS,
    TOKEN,
    UNREAD_STYLE,
    UNREAD_TEXT,
    VERTICAL_HEADER_VISIBLE,
    WIDGET_CHILDREN,
    WIDGET_INDEX,
    WIDGET_KINDS,
    WIDGET_NAMES,
    WIDGET_PARENTS,
    WIDGETS
  ];

  var NAME = "name";
  var KIND = "kind";
  var PARENT = "parent";
  var TEXT = "text";
  var COLOR = "color";
  var TITLE = "title";
  var LAYOUT = "layout";
  var MARGINS = "margins";
  var SPACING = "spacing";
  var STRETCH = "stretch";
  var STYLE_SHEET = "style_sheet";
  var ACTION = "action";
  var ENABLED = "enabled";
  var ROW_LABEL = "row_label";
  var PLACEHOLDER = "placeholder";
  var ECHO_MODE = "echo_mode";
  var ORIENTATION = "orientation";
  var HANDLE_WIDTH = "handle_width";
  var CHILDREN_COLLAPSIBLE = "children_collapsible";
  var SIZES = "sizes";
  var COLUMNS = "columns";
  var COLUMN_COUNT = "column_count";
  var RESIZE_MODE = "resize_mode";
  var EDIT_TRIGGERS = "edit_triggers";

  var STATUS_KEY = "status";
  var UNREAD_START_KEY = "unread_start";
  var UNREAD_WARNING_KEY = "unread_warning";
  var TELEGRAM_STATUS_KEY = "telegram_status";
  var SMS_STATUS_KEY = "sms_status";
  var EMPTY_KEY = "empty";
  var NONE_KEY = "none";

  var STATUS_LABEL = "status_label";
  var UNREAD_LABEL = "unread_label";
  var TELEGRAM_STATUS_NODE = "telegram_status";
  var SMS_STATUS_NODE = "sms_status";
  var TOKEN_INPUT = "token_input";
  var CHAT_INPUT = "chat_input";
  var PHONE_INPUT = "phone_input";
  var RULES_TABLE = "rules_table";
  var HISTORY_TABLE = "history_table";

  // The Telegram test sends no priority, so this field's null is its value.
  var NULLABLE = [TELEGRAM_TEST_PRIORITY];

  // Each label the surface repaints, with the two live fields it reads.
  var BOUND = [
    { node: STATUS_LABEL, text: STATUS_TEXT, style: STATUS_STYLE },
    { node: UNREAD_LABEL, text: UNREAD_TEXT, style: UNREAD_STYLE },
    {
      node: TELEGRAM_STATUS_NODE,
      text: TELEGRAM_STATUS_TEXT,
      style: TELEGRAM_STATUS_STYLE
    },
    { node: SMS_STATUS_NODE, text: SMS_STATUS_TEXT, style: SMS_STATUS_STYLE }
  ];

  // Each text field the operator types into, with the field it seeds from.
  var TYPED = [
    { node: TOKEN_INPUT, field: TOKEN },
    { node: CHAT_INPUT, field: CHAT_ID },
    { node: PHONE_INPUT, field: PHONE }
  ];

  var TABLES = [
    { node: RULES_TABLE, rows: RULES_ROWS },
    { node: HISTORY_TABLE, rows: HISTORY_ROWS }
  ];

  // Each live field with the published value whose type it must share.
  var PEERED = [
    { field: STATUS_TEXT, bag: TEXTS, key: STATUS_KEY },
    { field: UNREAD_TEXT, bag: TEXTS, key: UNREAD_START_KEY },
    { field: TELEGRAM_STATUS_TEXT, bag: TEXTS, key: TELEGRAM_STATUS_KEY },
    { field: SMS_STATUS_TEXT, bag: TEXTS, key: SMS_STATUS_KEY },
    { field: STATUS_STYLE, bag: STYLES, key: STATUS_KEY },
    { field: UNREAD_STYLE, bag: STYLES, key: UNREAD_WARNING_KEY },
    { field: TELEGRAM_STATUS_STYLE, bag: STYLES, key: EMPTY_KEY },
    { field: SMS_STATUS_STYLE, bag: STYLES, key: SMS_STATUS_KEY },
    { field: TEST_PATH, bag: null, key: NO_PATH },
    { field: SAVE_PATH, bag: null, key: NO_PATH },
    { field: ACK_PATH, bag: null, key: NO_PATH },
    { field: REFRESH_PATH, bag: null, key: NO_PATH }
  ];

  var MISSING_FAULT = "missing";
  var NULL_FAULT = "null";
  var NOT_AN_OBJECT_FAULT = "not-an-object";
  var WRONG_TYPE_FAULT = "wrong-type";
  var QT_COLOUR_FAULT = "qt-colour";
  var MARKUP_FAULT = "markup";
  var DISAGREES_FAULT = "disagrees";
  var SHORT_LIST_FAULT = "short-list";
  var UNSLOTTED_FAULT = "unslotted";
  var OVER_LIMIT_FAULT = "over-limit";

  var NO_BRIDGE = "the preload bridge is not present";

  var NODE_AT = "node:";
  var ROW_AT = "row:";
  var PATH_SPLIT = ".";
  var EMPTY = "";
  var GAP = " ";
  var SEMICOLON = ";";
  var COLON = ":";
  var COMMA = ",";
  var HASH = "#";
  var DOT = ".";
  var PERCENT = "%";
  var CLOSE = ")";
  var PX = "px";
  var VAR_OPEN = "var(--";
  var VAR_SPLIT = ", ";
  var VAR_CLOSE = ")";
  var CALC_OPEN = "calc(";
  // The unit factor that turns a unitless token into a CSS length.
  var PX_FACTOR = " * 1px)";
  var TAG_OPEN = "<";
  var TAG_CLOSE = ">";

  // Qt reads an eight-digit hex colour alpha first; CSS reads it last.
  var HEX_ARGB = "AARRGGBB";
  // Qt counts an rgba alpha in bytes; CSS counts it as a fraction.
  var RGBA_OPEN = "rgba(";

  // Only these token groups carry a value a CSS length may borrow.
  var LENGTH_GROUPS = ["spacing", "radii", "target_sizes", "table_columns", "focus"];

  // The Qt elide word that clips a cell with an ellipsis.
  var ELIDE_RIGHT = "ElideRight";
  // The Qt scrollbar word that shows a bar only when one is needed.
  var SCROLL_AS_NEEDED = "ScrollBarAsNeeded";
  // The Qt splitter word that lays its panes out across the tab.
  var HORIZONTAL = "Horizontal";
  // The Qt text-format word under which a label renders markup.
  var AUTO_TEXT = "AutoText";
  // The three Qt edit gestures that open a cell editor.
  var EDIT_WORDS = ["DoubleClicked", "EditKeyPressed", "AnyKeyPressed"];

  var ROW = "row";
  var COLUMN = "column";
  var FLEX = "flex";
  var FLEX_NONE = "none";
  var HIDDEN = "hidden";
  var AUTO = "auto";
  var FIXED = "fixed";
  var ELLIPSIS = "ellipsis";
  var NOWRAP = "nowrap";
  var NORMAL_WRAP = "normal";
  var COLLAPSE = "collapse";
  var GRID_ROLE = "grid";
  var CENTER = "center";
  var LEFT = "left";
  var FLEX_START = "flex-start";
  var TEXT_TYPE = "text";
  var PASSWORD_TYPE = "password";
  var GRID_COLUMNS = "auto 1fr";
  var GRID_SPAN = "1 / -1";
  var FULL = "100%";
  var COL_RESIZE = "col-resize";
  var ROW_RESIZE = "row-resize";
  var BUTTON_TYPE = "button";
  var DIV_TAG = "div";
  var SPAN_TAG = "span";
  var BUTTON_TAG = "button";
  var INPUT_TAG = "input";
  var TABLE_TAG = "table";
  var THEAD_TAG = "thead";
  var TBODY_TAG = "tbody";
  var TR_TAG = "tr";
  var TH_TAG = "th";
  var TD_TAG = "td";
  var FIELDSET_TAG = "fieldset";
  var LEGEND_TAG = "legend";
  var LABEL_TAG = "label";

  var TAB_CLASS = "acervator-alerts-tab";
  var PANE_CLASS = "acervator-alerts-pane";
  var GROUP_CLASS = "acervator-alerts-group";
  var TABLE_CLASS = "acervator-alerts-table";
  var FIELD_CLASS = "acervator-alerts-field";

  var TAB_PART = "tab";
  var SPLITTER_PART = "splitter";
  var PANE_PART = "pane";
  var SPLITTER_PANE_PART = "splitter-pane";
  var GROUP_BODY_PART = "group-body";
  var HANDLE_PART = "handle";
  var GROUP_PART = "group";
  var GROUP_TITLE_PART = "group-title";
  var FORM_PART = "form";
  var FORM_LABEL_PART = "form-label";
  var LABEL_PART = "label";
  var INPUT_PART = "input";
  var BUTTON_PART = "button";
  var TABLE_PART = "table";
  var SCROLL_PART = "table-scroll";
  var HEADER_CELL_PART = "header-cell";
  var ROW_PART = "row";
  var CELL_PART = "cell";
  var STRETCH_PART = "stretch";
  var ROW_BOX_PART = "row-box";

  var PART_ATTR = "data-part";
  var NAME_ATTR = "data-name";
  var KIND_ATTR = "data-kind";
  var INDEX_ATTR = "data-index";
  var ROW_ATTR = "data-row";
  var COLUMN_ATTR = "data-column";
  var ORIENTATION_ATTR = "data-orientation";
  var COLLAPSIBLE_ATTR = "data-collapsible";
  var ALTERNATING_ATTR = "data-alternating";
  var GRID_ATTR = "data-grid";
  var RESIZE_ATTR = "data-resize";
  var SELECTED_ATTR = "data-selected";
  var EDITABLE_ATTR = "data-editable";
  var HOVERED_ATTR = "data-hovered";
  var ACTION_ATTR = "data-action";
  var PATH_ATTR = "data-path";
  var SELECTION_MODE_ATTR = "data-selection-mode";
  var SELECTION_BEHAVIOR_ATTR = "data-selection-behavior";
  var ARIA_LABEL = "aria-label";
  var ARIA_ORIENTATION = "aria-orientation";
  var ARIA_SELECTED = "aria-selected";
  var ARIA_READONLY = "aria-readonly";
  var SEPARATOR_ROLE = "separator";
  var GRIDCELL_ROLE = "gridcell";
  var COLUMNHEADER_ROLE = "columnheader";

  var MOUSE_MOVE = "mousemove";
  var MOUSE_UP = "mouseup";
  var HOVER_STATE = "hover";

  var ARROW_LEFT = "ArrowLeft";
  var ARROW_RIGHT = "ArrowRight";
  var ARROW_UP = "ArrowUp";
  var ARROW_DOWN = "ArrowDown";
  var EDIT_KEY = "F2";
  var ESCAPE_KEY = "Escape";
  var ENTER_KEY = "Enter";

  // The Qt alignment word beside the CSS align it settles into.
  var ALIGN_WORDS = {
    "AlignCenter": { textAlign: CENTER, justifyContent: CENTER },
    "AlignLeft": { textAlign: LEFT, justifyContent: FLEX_START },
    "AlignLeft|AlignVCenter": { textAlign: LEFT, justifyContent: FLEX_START }
  };

  // The Qt echo word beside the input type it settles into.
  var ECHO_TYPES = { "Normal": TEXT_TYPE, "Password": PASSWORD_TYPE };

  var ONE = Number(true);
  var ZERO = Number(EMPTY);
  var NONE_AT = -ONE;

  var held = null;
  var alertFaults = [];
  var loadFault = null;
  var asked = null;
  var roots = [];

  function isPlainObject(value) {
    return value !== null && typeof value === "object" && !Array.isArray(value);
  }

  function owns(bag, name) {
    return Object.prototype.hasOwnProperty.call(bag, name);
  }

  function objectField(model, field) {
    return isPlainObject(model) && isPlainObject(model[field]) ? model[field] : {};
  }

  function listField(model, field) {
    return isPlainObject(model) && Array.isArray(model[field]) ? model[field] : [];
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

  function fault(where, field, kind, detail) {
    return { where: where, field: field, fault: kind, detail: detail };
  }

  // Undefined leaves an attribute off the element instead of writing one.
  function text(value) {
    return value === null || value === undefined ? undefined : String(value);
  }

  function afterFirst(value, splitter) {
    var parts = String(value).split(splitter);
    parts.shift();
    return parts;
  }

  function carries(value, splitter) {
    return Boolean(afterFirst(value, splitter).length);
  }

  // The token name shared_widgets.js gives one value, or undefined.
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

  // A colour painted through the one token that carries it.
  function colour(value) {
    var name = variableFor(value);
    if (name === undefined) {
      return text(value);
    }
    return VAR_OPEN + name + VAR_SPLIT + String(value) + VAR_CLOSE;
  }

  // `header_strip.js` owns the Qt sheet parser and the camel-case rule.
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

  // The style a named Qt state paints, `:hover` among them.
  function stateStyle(sheet, state) {
    var found = {};
    stateRules(sheet).forEach(function (rule) {
      if (!carries(rule.selector, state)) {
        return;
      }
      var painted = styleOf(rule.body);
      Object.keys(painted).forEach(function (name) {
        found[name] = painted[name];
      });
    });
    return found;
  }

  // Whether one value carries a tag Qt would render as markup.
  function markupIn(value) {
    return carries(value, TAG_OPEN) && carries(value, TAG_CLOSE);
  }

  // The surface publishes a margin in left, top, right, bottom order.
  var PADDING_SIDES = ["paddingLeft", "paddingTop", "paddingRight", "paddingBottom"];

  function marginStyle(margins) {
    var style = {};
    PADDING_SIDES.forEach(function (side, at) {
      if (at < margins.length) {
        style[side] = length(margins[at]);
      }
    });
    return style;
  }

  function aligned(style, word) {
    if (!owns(ALIGN_WORDS, word)) {
      return style;
    }
    var painted = ALIGN_WORDS[word];
    Object.keys(painted).forEach(function (name) {
      style[name] = painted[name];
    });
    return style;
  }

  function selectStyle(model) {
    return model[TEXT_SELECTABLE] === true ? undefined : FLEX_NONE;
  }

  function element() {
    return global.React.createElement.apply(null, arguments);
  }

  function hooks() {
    return global.React;
  }

  function nodes(model) {
    return listField(model, WIDGETS).filter(isPlainObject);
  }

  function nodeNamed(model, name) {
    var found;
    nodes(model).forEach(function (one) {
      if (one[NAME] === name) {
        found = one;
      }
    });
    return found;
  }

  function childrenOf(model, name) {
    return nodes(model).filter(function (one) {
      return one[PARENT] === name;
    });
  }

  function boundFor(name) {
    var found;
    BOUND.forEach(function (one) {
      if (one.node === name) {
        found = one;
      }
    });
    return found;
  }

  function typedFor(name) {
    var found;
    TYPED.forEach(function (one) {
      if (one.node === name) {
        found = one;
      }
    });
    return found;
  }

  function tableFor(name) {
    var found;
    TABLES.forEach(function (one) {
      if (one.node === name) {
        found = one;
      }
    });
    return found;
  }

  function rowsFor(model, name) {
    var slot = tableFor(name);
    return slot === undefined ? [] : listField(model, slot.rows);
  }

  // A spacer carries no value of its own and no child of its own.
  function isSpacer(model, node) {
    var own = Object.keys(node).filter(function (key) {
      return key !== NAME && key !== KIND && key !== PARENT;
    });
    return !own.length && !childrenOf(model, node[NAME]).length;
  }

  function Handle(props) {
    var model = props.model;
    var across = model[SPLITTER_ORIENTATION] === HORIZONTAL;
    var style = { flex: FLEX_NONE, cursor: across ? COL_RESIZE : ROW_RESIZE };
    if (across) {
      style.width = length(model[SPLITTER_HANDLE_WIDTH]);
    } else {
      style.height = length(model[SPLITTER_HANDLE_WIDTH]);
    }
    var handleProps = { style: style, role: SEPARATOR_ROLE, onMouseDown: props.onGrab };
    handleProps[PART_ATTR] = HANDLE_PART;
    handleProps[INDEX_ATTR] = String(props.at);
    handleProps[ARIA_ORIENTATION] = text(model[SPLITTER_ORIENTATION]);
    return element(DIV_TAG, handleProps, null);
  }

  // The splitter lays one pane per child out, a draggable handle between two.
  function Splitter(props) {
    var model = props.model;
    var across = model[SPLITTER_ORIENTATION] === HORIZONTAL;
    var state = hooks().useState(listField(model, SPLITTER_SIZES));
    var sizes = state.shift();
    var setSizes = state.shift();
    var panes = hooks().useRef([]);

    function grab(at) {
      return function (event) {
        var first = panes.current[at];
        var next = panes.current[at + ONE];
        if (!first || !next) {
          return;
        }
        event.preventDefault();
        var startAt = across ? event.clientX : event.clientY;
        var firstBox = first.getBoundingClientRect();
        var nextBox = next.getBoundingClientRect();
        var firstSize = across ? firstBox.width : firstBox.height;
        var nextSize = across ? nextBox.width : nextBox.height;
        var least =
          model[SPLITTER_CHILDREN_COLLAPSIBLE] === false
            ? model[SPLITTER_HANDLE_WIDTH]
            : ZERO;

        function move(moved) {
          var now = across ? moved.clientX : moved.clientY;
          var shift = now - startAt;
          var taken = Math.min(Math.max(shift, least - firstSize), nextSize - least);
          var drawn = sizes.slice();
          drawn[at] = firstSize + taken;
          drawn[at + ONE] = nextSize - taken;
          setSizes(drawn);
        }

        function drop() {
          global.document.removeEventListener(MOUSE_MOVE, move);
          global.document.removeEventListener(MOUSE_UP, drop);
        }

        global.document.addEventListener(MOUSE_MOVE, move);
        global.document.addEventListener(MOUSE_UP, drop);
      };
    }

    function keep(at) {
      return function (node) {
        panes.current[at] = node;
      };
    }

    var style = { display: FLEX, flexDirection: across ? ROW : COLUMN };
    style.flex = AUTO;
    style.overflow = HIDDEN;
    var splitterProps = { style: style };
    splitterProps[PART_ATTR] = SPLITTER_PART;
    splitterProps[NAME_ATTR] = text(props.node[NAME]);
    splitterProps[ORIENTATION_ATTR] = text(model[SPLITTER_ORIENTATION]);
    splitterProps[COLLAPSIBLE_ATTR] = text(model[SPLITTER_CHILDREN_COLLAPSIBLE]);

    var drawn = [];
    props.panes.forEach(function (child, at) {
      if (drawn.length) {
        drawn.push(
          element(Handle, {
            key: HANDLE_PART + String(at),
            at: at - ONE,
            model: model,
            onGrab: grab(at - ONE)
          })
        );
      }
      var paneStyle = { display: FLEX, flexDirection: COLUMN, overflow: HIDDEN };
      paneStyle.flex = String(at < sizes.length ? sizes[at] : EMPTY);
      var paneProps = { key: PANE_PART + String(at), style: paneStyle, ref: keep(at) };
      paneProps[PART_ATTR] = SPLITTER_PANE_PART;
      paneProps[INDEX_ATTR] = String(at);
      paneProps[NAME_ATTR] = text(child.name);
      drawn.push(element(DIV_TAG, paneProps, child.node));
    });
    return element(DIV_TAG, splitterProps, drawn);
  }

  function Pane(props) {
    var model = props.model;
    var style = marginStyle(listField(model, PANE_MARGINS));
    style.display = FLEX;
    style.flexDirection = COLUMN;
    style.gap = length(model[PANE_SPACING]);
    style.overflow = HIDDEN;
    style.flex = AUTO;
    var paneProps = { className: PANE_CLASS, style: style };
    paneProps[PART_ATTR] = PANE_PART;
    paneProps[NAME_ATTR] = text(props.node[NAME]);
    return element(DIV_TAG, paneProps, props.children);
  }

  function StatusLabel(props) {
    var model = props.model;
    var node = props.node;
    var slot = boundFor(node[NAME]);
    var painted = slot === undefined ? node[STYLE_SHEET] : model[slot.style];
    var shown = slot === undefined ? node[TEXT] : model[slot.text];
    var style = styleOf(painted);
    style.whiteSpace = model[LABEL_WORD_WRAP] === true ? NORMAL_WRAP : NOWRAP;
    style.overflow = HIDDEN;
    style.userSelect = selectStyle(model);
    aligned(style, model[LABEL_ALIGNMENT]);
    var labelProps = { style: style };
    labelProps[PART_ATTR] = LABEL_PART;
    labelProps[NAME_ATTR] = text(node[NAME]);
    labelProps[KIND_ATTR] = text(node[KIND]);
    return element(DIV_TAG, labelProps, text(shown));
  }

  function LineEdit(props) {
    var model = props.model;
    var node = props.node;
    var slot = typedFor(node[NAME]);
    var seeded = slot === undefined ? EMPTY : model[slot.field];
    var inputProps = {
      className: FIELD_CLASS,
      type: ECHO_TYPES[node[ECHO_MODE]],
      placeholder: text(node[PLACEHOLDER]),
      defaultValue: text(seeded),
      key: String(seeded),
      onChange: function (event) {
        props.onTyped(slot === undefined ? node[NAME] : slot.field, event.target.value);
      }
    };
    inputProps[PART_ATTR] = INPUT_PART;
    inputProps[NAME_ATTR] = text(node[NAME]);
    return element(INPUT_TAG, inputProps, null);
  }

  function Button(props) {
    var model = props.model;
    var node = props.node;
    var state = hooks().useState(false);
    var hovered = state.shift();
    var setHovered = state.shift();
    var style = styleOf(node[STYLE_SHEET]);
    if (hovered) {
      var painted = stateStyle(node[STYLE_SHEET], HOVER_STATE);
      Object.keys(painted).forEach(function (name) {
        style[name] = painted[name];
      });
    }
    style.userSelect = selectStyle(model);
    var enabled = objectField(model, BUTTONS_ENABLED)[node[NAME]];
    var buttonProps = {
      className: FIELD_CLASS,
      style: style,
      type: BUTTON_TYPE,
      disabled: enabled === false,
      onMouseEnter: function () {
        setHovered(true);
      },
      onMouseLeave: function () {
        setHovered(false);
      },
      onClick: function () {
        props.onAction(node[ACTION]);
      }
    };
    buttonProps[PART_ATTR] = BUTTON_PART;
    buttonProps[NAME_ATTR] = text(node[NAME]);
    buttonProps[ACTION_ATTR] = text(node[ACTION]);
    buttonProps[HOVERED_ATTR] = String(hovered);
    return element(BUTTON_TAG, buttonProps, text(node[TEXT]));
  }

  function Cell(props) {
    var model = props.model;
    var cell = isPlainObject(props.cell) ? props.cell : {};
    var editable = props.editable;
    var style = { color: colour(cell[COLOR]) };
    style.overflow = HIDDEN;
    style.textOverflow = model[CELL_ELIDE] === ELIDE_RIGHT ? ELLIPSIS : undefined;
    style.whiteSpace = model[TABLE_WORD_WRAP] === true ? NORMAL_WRAP : NOWRAP;
    style.userSelect = selectStyle(model);
    aligned(style, cell[ALIGNMENT]);
    var cellProps = {
      style: style,
      role: GRIDCELL_ROLE,
      tabIndex: props.current ? ZERO : NONE_AT,
      contentEditable: editable && props.editing ? true : undefined,
      suppressContentEditableWarning: editable ? true : undefined,
      onMouseDown: function (event) {
        props.onPick(event, props.at, props.column);
      },
      onDoubleClick: function () {
        props.onOpen(props.at, props.column);
      },
      onKeyDown: function (event) {
        props.onKey(event, props.at, props.column, editable);
      },
      ref: props.keep
    };
    cellProps[PART_ATTR] = CELL_PART;
    cellProps[ROW_ATTR] = String(props.at);
    cellProps[COLUMN_ATTR] = String(props.column);
    cellProps[SELECTED_ATTR] = String(props.selected);
    cellProps[EDITABLE_ATTR] = String(editable);
    cellProps[ARIA_SELECTED] = String(props.selected);
    return element(TD_TAG, cellProps, text(cell[TEXT]));
  }

  // The table draws the rows the surface published, in the order it published.
  function Table(props) {
    var model = props.model;
    var node = props.node;
    var rows = props.rows;
    var columns = listField(node, COLUMNS);
    var editable = Boolean(listField(node, EDIT_TRIGGERS).length);
    var picked = hooks().useState([]);
    var chosen = picked.shift();
    var setChosen = picked.shift();
    var placed = hooks().useState({ row: ZERO, column: ZERO });
    var at = placed.shift();
    var setAt = placed.shift();
    var editState = hooks().useState(false);
    var editing = editState.shift();
    var setEditing = editState.shift();
    var cells = hooks().useRef({});

    function keyOf(row, column) {
      return String(row) + PATH_SPLIT + String(column);
    }

    function isChosen(row, column) {
      return chosen.indexOf(keyOf(row, column)) !== NONE_AT;
    }

    function pick(event, row, column) {
      var one = keyOf(row, column);
      setAt({ row: row, column: column });
      setEditing(false);
      if (event.ctrlKey) {
        setChosen(
          isChosen(row, column)
            ? chosen.filter(function (other) {
                return other !== one;
              })
            : chosen.concat([one])
        );
        return;
      }
      if (event.shiftKey) {
        setChosen(chosen.concat([one]));
        return;
      }
      setChosen([one]);
    }

    function move(row, column) {
      var lastRow = rows.length - ONE;
      var lastColumn = columns.length - ONE;
      var nextRow = Math.min(Math.max(row, ZERO), Math.max(lastRow, ZERO));
      var nextColumn = Math.min(Math.max(column, ZERO), Math.max(lastColumn, ZERO));
      setAt({ row: nextRow, column: nextColumn });
      setChosen([keyOf(nextRow, nextColumn)]);
      var moved = cells.current[keyOf(nextRow, nextColumn)];
      if (moved) {
        moved.focus();
      }
    }

    function open(row, column) {
      if (!editable) {
        return;
      }
      setAt({ row: row, column: column });
      setEditing(true);
    }

    function onKey(event, row, column, cellEditable) {
      if (event.key === ESCAPE_KEY) {
        setEditing(false);
        return;
      }
      if (editing) {
        if (event.key === ENTER_KEY) {
          setEditing(false);
        }
        return;
      }
      if (event.key === ARROW_LEFT) {
        move(row, column - ONE);
        return;
      }
      if (event.key === ARROW_RIGHT) {
        move(row, column + ONE);
        return;
      }
      if (event.key === ARROW_UP) {
        move(row - ONE, column);
        return;
      }
      if (event.key === ARROW_DOWN) {
        move(row + ONE, column);
        return;
      }
      if (!cellEditable) {
        return;
      }
      if (event.key === EDIT_KEY || event.key.length === ONE) {
        setEditing(true);
      }
    }

    var headStyle = {};
    aligned(headStyle, model[HEADER_ALIGNMENT]);
    headStyle.userSelect = selectStyle(model);
    var head = columns.map(function (title, column) {
      var headProps = { key: String(column), style: headStyle, scope: COLUMN };
      headProps[PART_ATTR] = HEADER_CELL_PART;
      headProps[COLUMN_ATTR] = String(column);
      headProps.role = COLUMNHEADER_ROLE;
      return element(TH_TAG, headProps, text(title));
    });

    var body = rows.map(function (row, index) {
      var rowProps = { key: String(index) };
      rowProps[PART_ATTR] = ROW_PART;
      rowProps[ROW_ATTR] = String(index);
      var drawn = columns.map(function (unused, column) {
        var cell = Array.isArray(row) ? row[column] : undefined;
        return element(Cell, {
          key: String(column),
          model: model,
          cell: cell,
          at: index,
          column: column,
          editable: editable,
          editing: editing && at.row === index && at.column === column,
          current: at.row === index && at.column === column,
          selected: isChosen(index, column),
          onPick: pick,
          onOpen: open,
          onKey: onKey,
          keep: function (found) {
            cells.current[keyOf(index, column)] = found;
          }
        });
      });
      return element(TR_TAG, rowProps, drawn);
    });

    var tableStyle = {
      width: FULL,
      borderCollapse: model[SHOW_GRID] === true ? COLLAPSE : undefined
    };
    tableStyle.tableLayout = node[RESIZE_MODE] === model[HEADER_RESIZE_MODE]
      ? FIXED
      : AUTO;
    var tableProps = { className: TABLE_CLASS, style: tableStyle, role: GRID_ROLE };
    tableProps[PART_ATTR] = TABLE_PART;
    tableProps[NAME_ATTR] = text(node[NAME]);
    tableProps[ALTERNATING_ATTR] = text(node[ALTERNATING_ROW_COLORS]);
    tableProps[GRID_ATTR] = text(model[SHOW_GRID]);
    tableProps[RESIZE_ATTR] = text(node[RESIZE_MODE]);
    tableProps[EDITABLE_ATTR] = String(editable);
    tableProps[SELECTION_MODE_ATTR] = text(model[SELECTION_MODE]);
    tableProps[SELECTION_BEHAVIOR_ATTR] = text(model[SELECTION_BEHAVIOR]);
    tableProps[ARIA_READONLY] = String(!editable);

    var scrollStyle = {
      flex: AUTO,
      overflow: model[SCROLL_BAR_POLICY] === SCROLL_AS_NEEDED ? AUTO : HIDDEN
    };
    var scrollProps = { style: scrollStyle };
    scrollProps[PART_ATTR] = SCROLL_PART;
    scrollProps[NAME_ATTR] = text(node[NAME]);
    return element(
      DIV_TAG,
      scrollProps,
      element(TABLE_TAG, tableProps, [
        element(THEAD_TAG, { key: THEAD_TAG }, element(TR_TAG, null, head)),
        element(TBODY_TAG, { key: TBODY_TAG }, body)
      ])
    );
  }

  function GroupBox(props) {
    var node = props.node;
    var style = styleOf(node[STYLE_SHEET]);
    style.display = FLEX;
    style.flexDirection = COLUMN;
    style.minWidth = ZERO;
    if (node[STRETCH] !== undefined) {
      style.flex = String(node[STRETCH]);
    }
    var groupProps = { className: GROUP_CLASS, style: style };
    groupProps[PART_ATTR] = GROUP_PART;
    groupProps[NAME_ATTR] = text(node[NAME]);
    var titleProps = {};
    titleProps[PART_ATTR] = GROUP_TITLE_PART;
    titleProps[NAME_ATTR] = text(node[NAME]);
    var legend = element(LEGEND_TAG, titleProps, text(node[TITLE]));
    return element(FIELDSET_TAG, groupProps, [legend].concat(props.children));
  }

  // A form row spans both columns when the surface publishes no label for it.
  function FormRow(props) {
    var model = props.model;
    var node = props.node;
    var shownLabel = node[ROW_LABEL];
    var spans = !shownLabel;
    var labelStyle = {};
    aligned(labelStyle, model[FORM_LABEL_ALIGNMENT]);
    labelStyle.userSelect = selectStyle(model);
    var drawn = [];
    if (!spans) {
      var labelProps = { key: FORM_LABEL_PART, style: labelStyle };
      labelProps[PART_ATTR] = FORM_LABEL_PART;
      labelProps[NAME_ATTR] = text(node[NAME]);
      drawn.push(element(LABEL_TAG, labelProps, text(shownLabel)));
    }
    var fieldProps = {
      key: node[NAME],
      style: { gridColumn: spans ? GRID_SPAN : undefined }
    };
    drawn.push(element(DIV_TAG, fieldProps, props.children));
    return drawn;
  }

  function RowBox(props) {
    var style = { display: FLEX, flexDirection: ROW };
    var boxProps = { style: style };
    boxProps[PART_ATTR] = ROW_BOX_PART;
    boxProps[NAME_ATTR] = text(props.node[NAME]);
    return element(DIV_TAG, boxProps, props.children);
  }

  function Stretch(props) {
    var stretchProps = { style: { flex: AUTO } };
    stretchProps[PART_ATTR] = STRETCH_PART;
    stretchProps[NAME_ATTR] = text(props.node[NAME]);
    return element(DIV_TAG, stretchProps, null);
  }

  function drawChildren(model, name, hand) {
    return childrenOf(model, name).map(function (child) {
      return drawNode(model, child, hand);
    });
  }

  function isForm(model, node) {
    return childrenOf(model, node[NAME]).filter(function (child) {
      return owns(child, ROW_LABEL);
    }).length > ZERO;
  }

  function formStyle(model) {
    return {
      display: GRID_ROLE,
      gridTemplateColumns: GRID_COLUMNS,
      gap: length(model[FORM_SPACING]),
      alignItems: CENTER
    };
  }

  function paneBodyStyle(model) {
    return {
      display: FLEX,
      flexDirection: COLUMN,
      flex: AUTO,
      minHeight: ZERO,
      gap: length(model[PANE_SPACING])
    };
  }

  function drawGroup(model, node, hand) {
    if (!isForm(model, node)) {
      var bodyProps = { style: paneBodyStyle(model) };
      bodyProps[PART_ATTR] = GROUP_BODY_PART;
      bodyProps[NAME_ATTR] = text(node[NAME]);
      return element(
        GroupBox,
        { key: node[NAME], node: node },
        element(DIV_TAG, bodyProps, drawChildren(model, node[NAME], hand))
      );
    }
    var formProps = { style: formStyle(model) };
    formProps[PART_ATTR] = FORM_PART;
    formProps[NAME_ATTR] = text(node[NAME]);
    return element(
      GroupBox,
      { key: node[NAME], node: node },
      element(DIV_TAG, formProps, wrapRows(model, node, hand))
    );
  }

  function drawLeaf(model, node, hand) {
    if (owns(node, PLACEHOLDER)) {
      return element(LineEdit, {
        key: node[NAME],
        model: model,
        node: node,
        onTyped: hand.onTyped
      });
    }
    if (owns(node, ACTION)) {
      return element(Button, {
        key: node[NAME],
        model: model,
        node: node,
        onAction: hand.onAction
      });
    }
    if (owns(node, COLUMNS)) {
      return element(Table, {
        key: node[NAME],
        model: model,
        node: node,
        rows: rowsFor(model, node[NAME])
      });
    }
    return element(StatusLabel, { key: node[NAME], model: model, node: node });
  }

  function drawNode(model, node, hand) {
    var name = node[NAME];
    if (isSpacer(model, node)) {
      return element(Stretch, { key: name, node: node });
    }
    if (owns(node, TITLE)) {
      return drawGroup(model, node, hand);
    }
    if (owns(node, ORIENTATION)) {
      var panes = childrenOf(model, name).map(function (child) {
        return { name: child[NAME], node: drawNode(model, child, hand) };
      });
      return element(Splitter, { key: name, model: model, node: node, panes: panes });
    }
    if (owns(node, MARGINS)) {
      return element(
        Pane,
        { key: name, model: model, node: node },
        drawChildren(model, name, hand)
      );
    }
    if (childrenOf(model, name).length) {
      return element(
        RowBox,
        { key: name, node: node },
        drawChildren(model, name, hand)
      );
    }
    return drawLeaf(model, node, hand);
  }

  // A row with a label becomes two grid cells, so it is wrapped after drawing.
  function wrapRows(model, node, hand) {
    return childrenOf(model, node[NAME]).map(function (child) {
      return element(
        FormRow,
        { key: child[NAME], model: model, node: child },
        drawNode(model, child, hand)
      );
    });
  }

  function Tab(props) {
    var model = props.model;
    if (!isPlainObject(model)) {
      return null;
    }
    var typed = hooks().useRef({});
    var hand = {
      onAction: function (name) {
        if (typeof props.onAction === "function") {
          props.onAction(name, copyOf(typed.current));
        }
      },
      onTyped: function (field, value) {
        typed.current[field] = value;
      }
    };
    var root = nodes(model).filter(function (one) {
      return !one[PARENT];
    });
    var style = marginStyle(listField(model, CONTENT_MARGINS));
    var painted = styleOf(model[TAB_STYLE_SHEET]);
    Object.keys(painted).forEach(function (name) {
      style[name] = painted[name];
    });
    style.display = FLEX;
    style.flexDirection = COLUMN;
    style.gap = length(model[CONTENT_SPACING]);
    style.overflow = HIDDEN;
    var first = root.shift();
    var tabProps = { className: TAB_CLASS, style: style };
    tabProps[PART_ATTR] = TAB_PART;
    tabProps[ARIA_LABEL] = text(model[ACCESSIBLE_NAME]);
    tabProps[NAME_ATTR] = first === undefined ? undefined : text(first[NAME]);
    if (first === undefined) {
      return element(DIV_TAG, tabProps, null);
    }
    return element(DIV_TAG, tabProps, drawChildren(model, first[NAME], hand));
  }

  function checkFields(model) {
    DECLARED_FIELDS.forEach(function (field) {
      if (!owns(model, field)) {
        alertFaults.push(fault(null, field, MISSING_FAULT, null));
        return;
      }
      if (model[field] === null && NULLABLE.indexOf(field) === NONE_AT) {
        alertFaults.push(fault(null, field, NULL_FAULT, null));
      }
    });
  }

  // A wrong type is named only against a value the surface publishes twice.
  function checkPeers(model) {
    PEERED.forEach(function (one) {
      var peer = one.bag === null ? model[one.key] : objectField(model, one.bag)[one.key];
      if (peer === undefined || peer === null || !owns(model, one.field)) {
        return;
      }
      if (model[one.field] === null) {
        return;
      }
      if (kindOf(model[one.field]) !== kindOf(peer)) {
        alertFaults.push(
          fault(null, one.field, WRONG_TYPE_FAULT, kindOf(model[one.field]))
        );
      }
    });
  }

  function checkSheet(where, field, sheet) {
    declarations(sheet).forEach(function (one) {
      if (qtColour(one.value) !== undefined) {
        alertFaults.push(fault(where, field, QT_COLOUR_FAULT, one.property));
      }
    });
  }

  function checkSheets(model) {
    nodes(model).forEach(function (node) {
      if (owns(node, STYLE_SHEET)) {
        checkSheet(NODE_AT + String(node[NAME]), STYLE_SHEET, node[STYLE_SHEET]);
      }
    });
    Object.keys(objectField(model, STYLES)).forEach(function (name) {
      checkSheet(STYLES, name, objectField(model, STYLES)[name]);
    });
    Object.keys(objectField(model, CELL_COLORS)).forEach(function (name) {
      checkSheet(CELL_COLORS, name, COLOR + COLON + objectField(model, CELL_COLORS)[name]);
    });
  }

  // Qt renders a label's text as markup, so a tag reaching one is named.
  function checkMarkup(model) {
    if (model[TEXT_FORMAT] !== AUTO_TEXT) {
      return;
    }
    BOUND.forEach(function (one) {
      if (markupIn(model[one.text])) {
        alertFaults.push(fault(NODE_AT + one.node, one.text, MARKUP_FAULT, AUTO_TEXT));
      }
    });
  }

  function checkTree(model) {
    var named = listField(model, WIDGET_NAMES);
    var actions = objectField(model, ACTIONS);
    nodes(model).forEach(function (node) {
      if (named.indexOf(node[NAME]) === NONE_AT) {
        alertFaults.push(fault(NODE_AT + String(node[NAME]), NAME, UNSLOTTED_FAULT, null));
      }
      if (!owns(node, ACTION)) {
        return;
      }
      var run = Object.keys(actions).filter(function (one) {
        return actions[one] === node[ACTION];
      });
      if (!run.length) {
        alertFaults.push(
          fault(NODE_AT + String(node[NAME]), ACTION, UNSLOTTED_FAULT, node[ACTION])
        );
      }
    });
    if (nodes(model).length !== named.length) {
      alertFaults.push(fault(null, WIDGETS, DISAGREES_FAULT, named.length));
    }
  }

  function checkSplitter(model) {
    var panes = childrenOf(model, splitterName(model)).length;
    if (listField(model, SPLITTER_SIZES).length < panes) {
      alertFaults.push(
        fault(null, SPLITTER_SIZES, SHORT_LIST_FAULT, listField(model, SPLITTER_SIZES).length)
      );
    }
  }

  function splitterName(model) {
    var found = EMPTY;
    nodes(model).forEach(function (node) {
      if (owns(node, ORIENTATION)) {
        found = node[NAME];
      }
    });
    return found;
  }

  function checkRows(model) {
    TABLES.forEach(function (slot) {
      var node = nodeNamed(model, slot.node);
      var wide = node === undefined ? ZERO : node[COLUMN_COUNT];
      var rows = listField(model, slot.rows);
      rows.forEach(function (row, at) {
        if (!Array.isArray(row)) {
          alertFaults.push(fault(ROW_AT + slot.node, String(at), NOT_AN_OBJECT_FAULT, kindOf(row)));
          return;
        }
        if (row.length !== wide) {
          alertFaults.push(fault(ROW_AT + slot.node, String(at), DISAGREES_FAULT, row.length));
        }
        checkCells(model, slot.node, at, row);
      });
    });
    var limit = model[HISTORY_LIMIT];
    var history = listField(model, HISTORY_ROWS).length;
    if (typeof limit === "number" && history > limit) {
      alertFaults.push(fault(null, HISTORY_ROWS, OVER_LIMIT_FAULT, history));
    }
  }

  function checkCells(model, where, at, row) {
    var blank = objectField(model, CELL_COLORS)[NONE_KEY];
    var word = model[ALIGNMENT];
    row.forEach(function (cell, column) {
      if (!isPlainObject(cell)) {
        alertFaults.push(
          fault(ROW_AT + where + PATH_SPLIT + String(at), String(column), NOT_AN_OBJECT_FAULT, kindOf(cell))
        );
        return;
      }
      var place = ROW_AT + where + PATH_SPLIT + String(at);
      if (blank !== undefined && cell[COLOR] !== null && kindOf(cell[COLOR]) !== kindOf(blank)) {
        alertFaults.push(fault(place, COLOR, WRONG_TYPE_FAULT, kindOf(cell[COLOR])));
      }
      if (word !== undefined && cell[ALIGNMENT] !== null && kindOf(cell[ALIGNMENT]) !== kindOf(word)) {
        alertFaults.push(fault(place, ALIGNMENT, WRONG_TYPE_FAULT, kindOf(cell[ALIGNMENT])));
      }
    });
  }

  function heldFieldCount() {
    return DECLARED_FIELDS.filter(function (field) {
      return held !== null && owns(held.model, field);
    }).length;
  }

  // Every cell one table promised, counted from its rows and its width.
  function promisedCells(model, rowsField, countField) {
    var wide = model[countField];
    if (typeof wide !== "number") {
      return ZERO;
    }
    return listField(model, rowsField).length * wide;
  }

  function drawnCells(model, rowsField) {
    var counted = ZERO;
    listField(model, rowsField).forEach(function (row) {
      counted = counted + (Array.isArray(row) ? row.length : ZERO);
    });
    return counted;
  }

  function report() {
    var model = held.model;
    return {
      declared: {
        fields: DECLARED_FIELDS.length,
        nodes: listField(model, WIDGET_NAMES).length,
        rules_columns: model[RULES_COLUMN_COUNT],
        history_columns: model[HISTORY_COLUMN_COUNT],
        rules_cells: promisedCells(model, RULES_ROWS, RULES_COLUMN_COUNT),
        history_cells: promisedCells(model, HISTORY_ROWS, HISTORY_COLUMN_COUNT)
      },
      held: {
        fields: heldFieldCount(),
        nodes: nodes(model).length,
        rules_columns: listField(model, RULES_COLUMNS).length,
        history_columns: listField(model, HISTORY_COLUMNS).length,
        rules_cells: drawnCells(model, RULES_ROWS),
        history_cells: drawnCells(model, HISTORY_ROWS)
      },
      faults: alertFaults.slice()
    };
  }

  function setAlerts(model) {
    if (!isPlainObject(model)) {
      held = null;
      alertFaults = [fault(null, null, NOT_AN_OBJECT_FAULT, kindOf(model))];
      return { declared: null, held: null, faults: alertFaults.slice() };
    }
    held = { model: model };
    alertFaults = [];
    checkFields(model);
    checkPeers(model);
    checkSheets(model);
    checkMarkup(model);
    checkTree(model);
    checkSplitter(model);
    checkRows(model);
    return report();
  }

  // A failed ask is not remembered, so a later one reaches the bridge again.
  function loadAlerts(params) {
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
        setAlerts(model);
        return model;
      })
      .catch(function (err) {
        loadFault = err.message;
        asked = null;
        return null;
      });
    return asked;
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

  function declaredNames() {
    return DECLARED_FIELDS.slice();
  }

  function addressedNames() {
    var found = [];
    BOUND.forEach(function (one) {
      found.push(one.node);
    });
    TYPED.forEach(function (one) {
      found.push(one.node);
    });
    TABLES.forEach(function (one) {
      found.push(one.node);
    });
    return found;
  }

  function peeredNames() {
    return PEERED.map(function (one) {
      return one.field;
    });
  }

  function alignWords() {
    return Object.keys(ALIGN_WORDS);
  }

  function echoWords() {
    return Object.keys(ECHO_TYPES);
  }

  function editWords() {
    return EDIT_WORDS.slice();
  }

  function readingWords() {
    return {
      elide: ELIDE_RIGHT,
      scroll: SCROLL_AS_NEEDED,
      orientation: HORIZONTAL,
      format: AUTO_TEXT
    };
  }

  function node(name) {
    return held === null ? undefined : nodeNamed(held.model, name);
  }

  function rows(name) {
    return held === null ? [] : rowsFor(held.model, name).slice();
  }

  // Each history row's cell texts, in the order the surface published them.
  function rowTexts(name) {
    return rows(name).map(function (row) {
      return (Array.isArray(row) ? row : []).map(function (cell) {
        return isPlainObject(cell) ? cell[TEXT] : undefined;
      });
    });
  }

  // Every payload value's JavaScript type, by dotted path, null apart.
  function kinds() {
    var found = {};
    function walk(prefix, bag) {
      Object.keys(bag).forEach(function (name) {
        var path = prefix ? prefix + PATH_SPLIT + name : name;
        found[path] = kindOf(bag[name]);
        descend(path, bag[name]);
      });
    }
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
    if (held !== null) {
      walk(EMPTY, held.model);
    }
    return found;
  }

  function faults() {
    return alertFaults.slice();
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

  // `flushSync` makes the document current before `draw` returns.
  function draw(target, tree) {
    var root = rootFor(target);
    global.ReactDOM.flushSync(function () {
      root.render(tree);
    });
    return target;
  }

  function renderTab(target, model, onAction) {
    var payload = model;
    if (!isPlainObject(payload)) {
      payload = held === null ? null : held.model;
    }
    return draw(target, element(Tab, { model: payload, onAction: onAction }));
  }

  function forget() {
    held = null;
    alertFaults = [];
    loadFault = null;
    asked = null;
  }

  global.acervatorSetAlerts = setAlerts;
  global.acervatorLoadAlerts = loadAlerts;
  global.acervatorAlerts = {
    method: METHOD,
    Tab: Tab,
    Splitter: Splitter,
    Pane: Pane,
    GroupBox: GroupBox,
    FormRow: FormRow,
    StatusLabel: StatusLabel,
    LineEdit: LineEdit,
    Button: Button,
    Table: Table,
    Cell: Cell,
    Stretch: Stretch,
    RowBox: RowBox,
    field: field,
    bag: bag,
    list: list,
    node: node,
    rows: rows,
    rowTexts: rowTexts,
    declaredNames: declaredNames,
    addressedNames: addressedNames,
    peeredNames: peeredNames,
    alignWords: alignWords,
    echoWords: echoWords,
    editWords: editWords,
    readingWords: readingWords,
    declarations: declarations,
    stateRules: stateRules,
    styleOf: styleOf,
    stateStyle: stateStyle,
    qtColour: qtColour,
    keptSheet: keptSheet,
    markupIn: markupIn,
    variableFor: variableFor,
    variableInGroups: variableInGroups,
    colour: colour,
    length: length,
    kinds: kinds,
    faults: faults,
    loadError: loadError,
    isLoaded: isLoaded,
    renderTab: renderTab,
    forget: forget
  };
})(window);
