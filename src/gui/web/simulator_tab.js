// The Simulator tab as the Python surface serves it, in one global function.
(function (global) {
  "use strict";

  var METHOD = "simulator_tab.state";

  // Every section simulator_tab_surface publishes, answered by field().
  var DECLARED_FIELDS = [
    "call_names", "calls", "chrome", "defaults", "dialogs", "dialogs_shown",
    "error_types", "focus", "identity", "log", "log_levels", "modes",
    "mounts", "pages", "pickers", "pins", "refusals", "state_keys",
    "streams", "table", "text", "warnings", "wiring"
  ];

  var CHROME = "chrome";
  var IDENTITY = "identity";
  var TEXT = "text";
  var MODES = "modes";
  var PICKERS = "pickers";
  var LOG = "log";
  var TABLE = "table";
  var WIRING = "wiring";
  var FOCUS = "focus";
  var MOUNTS = "mounts";

  var ACCESSIBLE_NAME = "accessible_name";
  var OBJECT_NAME = "object_name";
  var SECTION_LABEL_STYLE = "section_label_style";

  var OUTER_MARGINS = "outer_margins";
  var OUTER_SPACING = "outer_spacing";
  var QT_UNSET_SPACING = "qt_unset_spacing";
  var QT_NESTED_MARGINS = "qt_nested_margins";
  var SPLITTER_MINIMUM = "splitter_minimum";
  var STACK_STRETCH = "stack_stretch";
  var FLEET_PANEL_STRETCH = "fleet_panel_stretch";
  var INDICATOR_CONTAINER_STRETCH = "indicator_container_stretch";
  var SCROLL_STRETCH = "scroll_stretch";
  var CONTENT_MARGINS = "content_margins";
  var CONTENT_SPACING = "content_spacing";
  var FLEET_PAGE_MARGINS = "fleet_page_margins";
  var FLEET_PAGE_SPACING = "fleet_page_spacing";
  var BOT_AREA_MARGINS = "bot_area_margins";
  var BOT_AREA_SPACING = "bot_area_spacing";
  var ACTIVE_BOT_ROW_MARGINS = "active_bot_row_margins";
  var MODE_ROW_MARGINS = "mode_row_margins";
  var CHART_PICK_ROW_MARGINS = "chart_pick_row_margins";
  var INDICATOR_WRAP_MARGINS = "indicator_wrap_margins";
  var INDICATOR_STYLE = "indicator_style";
  var INDICATOR_OBJECT_NAME = "indicator_object_name";
  var INDICATOR_INNER_MARGINS = "indicator_inner_margins";
  var INDICATOR_INNER_SPACING = "indicator_inner_spacing";
  var SCROLL_MINIMUM_HEIGHT = "scroll_minimum_height";
  var TITLED_MARGINS = "titled_margins";
  var TITLED_SPACING = "titled_spacing";
  var TITLED_HEAD_MARGINS = "titled_head_margins";
  var ACTIVITY_WRAP_MARGINS = "activity_wrap_margins";
  var ACTIVITY_WRAP_SPACING = "activity_wrap_spacing";
  var GATE_WRAP_MARGINS = "gate_wrap_margins";
  var GATE_WRAP_SPACING = "gate_wrap_spacing";
  var GATE_HOST_MARGINS = "gate_host_margins";

  var MAIN_SPLITTER = "main_splitter";
  var TOP_SPLITTER = "top_splitter";
  var LOG_SPLITTER = "log_splitter";
  var INDICATOR_SPLITTER = "indicator_splitter";
  var SIZES_TAIL = "_sizes";
  var HANDLE_TAIL = "_handle_width";
  var ORIENTATION_TAIL = "_orientation";
  var COLLAPSIBLE_TAIL = "_collapsible";
  var VERTICAL = "vertical";

  var MODE_LABEL = "mode_label";
  var MODE_LABEL_STYLE = "mode_label_style";
  var MODE_HINT_STYLE = "mode_hint_style";
  var ACTIVE_BOT_LABEL = "active_bot_label";
  var ACTIVE_BOT_LABEL_STYLE = "active_bot_label_style";
  var CHART_PICK_LABEL = "chart_pick_label";
  var CHART_PICK_LABEL_STYLE = "chart_pick_label_style";
  var CHART_TITLE = "chart_title";
  var VOTING_TITLE = "voting_title";
  var EXPAND = "expand";
  var EXPAND_STYLE = "expand_style";
  var EXPAND_TOOLTIPS = "expand_tooltips";
  var SIM_LOG_TITLE = "sim_log_title";
  var PAUSE_STYLE = "pause_style";
  var LOG_STYLE = "log_style";
  var LOG_READ_ONLY = "log_read_only";
  var LABEL_WORD_WRAP = "label_word_wrap";
  var LABEL_SELECTABLE = "label_selectable";
  var LOG_SELECTABLE = "log_selectable";
  var LOG_WRAPS_AT_WIDTH = "log_wraps_at_width";
  var GATE_TITLE = "gate_title";
  var GATE_UNAVAILABLE = "gate_unavailable";
  var GATE_UNAVAILABLE_STYLE = "gate_unavailable_style";
  var FLEET_PANEL_UNAVAILABLE = "fleet_panel_unavailable";
  var NUCLEAR_PANEL_UNAVAILABLE = "nuclear_panel_unavailable";

  var ROWS = "rows";
  var ITEMS = "items";
  var ITEM_TOOLTIPS = "item_tooltips";
  var INDEX = "index";
  var SELECTED = "selected";
  var HINT_TEXT = "hint_text";
  var STACK_INDEX = "stack_index";
  var STACK_COUNT = "stack_count";
  var PAGE_TOTAL = "page_total";
  var FLEET_PAGE_INDEX = "fleet_page_index";
  var NUCLEAR_PAGE_INDEX = "nuclear_page_index";
  var NUCLEAR_KEY = "nuclear_key";
  var SELECTOR_MIN_WIDTH = "selector_min_width";
  var SELECTOR_TOOLTIP = "selector_tooltip";
  var MINIMUM_WIDTH = "minimum_width";
  var TOOLTIP = "tooltip";
  var ACTIVE = "active";
  var CHART = "chart";

  var LINES = "lines";
  var PANE_TEXT = "text";
  var ACTIVITY_PAUSED = "activity_paused";
  var PAUSE_BUTTON_TEXT = "pause_button_text";
  var MOUNTED = "mounted";

  var ACTIONS = "actions";
  var GATE_PANEL_SET = "gate_panel_set";
  var FLEET_PANEL_SET = "fleet_panel_set";
  var NUCLEAR_PANEL_SET = "nuclear_panel_set";
  var POLICIES = "policies";
  var ORDER = "order";

  var MODE_ACTION = "mode_selector.currentIndexChanged";
  var CHART_ACTION = "chart_bot_picker.currentIndexChanged";
  var PAUSE_ACTION = "activity_pause_button.toggled";
  var CHART_EXPAND_ACTION = "chart_expand_button.clicked";
  var VOTING_EXPAND_ACTION = "voting_expand_button.clicked";

  var MODE_PARAM = "mode";
  var CHART_PARAM = "chart_bot";
  var PAUSE_PARAM = "pause";
  var ACTION_PARAM = "action";

  var MISSING_FAULT = "missing";
  var NULL_FAULT = "null";
  var NOT_AN_OBJECT_FAULT = "not-an-object";
  var WRONG_TYPE_FAULT = "wrong-type";
  var QT_COLOUR_FAULT = "qt-colour";
  var DISAGREES_FAULT = "disagrees";
  var UNPLACED_FAULT = "unplaced";
  var NO_SHEET_SOURCE_FAULT = "no-sheet-source";

  var NO_BRIDGE = "the preload bridge is not present";

  var PATH_SPLIT = ".";
  var EMPTY = "";
  var GAP = " ";
  var NEWLINE = "\n";
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

  // Qt reads an eight-digit hex colour alpha first; CSS reads it last.
  var HEX_ARGB = "AARRGGBB";
  // Qt counts an rgba alpha in bytes; CSS counts it as a fraction.
  var RGBA_OPEN = "rgba(";

  // A gap borrows only from spacing, because a radius means something else.
  var SPACE_GROUPS = ["spacing"];
  // A drawn width borrows only from the two groups that measure widths.
  var WIDTH_GROUPS = ["target_sizes", "table_columns"];

  var ROW = "row";
  var COLUMN = "column";
  var FLEX = "flex";
  var FLEX_NONE = "none";
  var HIDDEN = "hidden";
  var AUTO = "auto";
  var NOWRAP = "nowrap";
  var PRE_WRAP = "pre-wrap";
  var NONE = "none";
  var CENTER = "center";
  var TEXT_SELECT = "text";
  var BUTTON_TYPE = "button";
  var DIV_TAG = "div";
  var SPAN_TAG = "span";
  var BUTTON_TAG = "button";
  var SELECT_TAG = "select";
  var OPTION_TAG = "option";
  var TEXTAREA_TAG = "textarea";
  var COLUMN_CURSOR = "row-resize";
  var ROW_CURSOR = "col-resize";
  var MOUSE_MOVE = "mousemove";
  var MOUSE_UP = "mouseup";

  var TAB_CLASS = "acervator-sim-box";
  var CELL_CLASS = "acervator-sim-cell";
  var INPUT_CLASS = "acervator-sim-input";

  var TAB_PART = "sim-tab";
  var SPLITTER_PANE_PART = "splitter-pane";
  var SPLITTER_HANDLE_PART = "splitter-handle";
  var MAIN_SPLITTER_PART = "main-splitter";
  var TOP_SPLITTER_PART = "top-splitter";
  var LOG_SPLITTER_PART = "log-splitter";
  var INDICATOR_SPLITTER_PART = "indicator-splitter";
  var CONTENT_PART = "content";
  var MODE_ROW_PART = "mode-row";
  var MODE_LABEL_PART = "mode-label";
  var MODE_SELECTOR_PART = "mode-selector";
  var MODE_HINT_PART = "mode-hint";
  var STRETCH_PART = "stretch";
  var STACK_PART = "stack";
  var FLEET_PAGE_PART = "fleet-page";
  var NUCLEAR_PAGE_PART = "nuclear-page";
  var BOT_AREA_PART = "bot-area";
  var ACTIVE_BOT_ROW_PART = "active-bot-row";
  var ACTIVE_BOT_LABEL_PART = "active-bot-label";
  var ACTIVE_BOT_PICKER_PART = "active-bot-picker";
  var INDICATOR_WRAP_PART = "indicator-wrap";
  var INDICATOR_CONTAINER_PART = "indicator-container";
  var TITLED_BOX_PART = "titled-box";
  var TITLED_HEAD_PART = "titled-head";
  var SECTION_LABEL_PART = "section-label";
  var EXPAND_BUTTON_PART = "expand-button";
  var CHART_PICK_ROW_PART = "chart-pick-row";
  var CHART_PICK_LABEL_PART = "chart-pick-label";
  var CHART_BOT_PICKER_PART = "chart-bot-picker";
  var SCROLL_PART = "scroll";
  var ACTIVITY_WRAP_PART = "activity-wrap";
  var LOG_HEADER_PART = "log-header";
  var PAUSE_BUTTON_PART = "pause-button";
  var LOG_PANE_PART = "log-pane";
  var GATE_WRAP_PART = "gate-wrap";
  var GATE_HEADER_PART = "gate-header";
  var GATE_HOST_PART = "gate-host";
  var GATE_UNAVAILABLE_PART = "gate-unavailable";
  var FLEET_UNAVAILABLE_PART = "fleet-unavailable";
  var NUCLEAR_UNAVAILABLE_PART = "nuclear-unavailable";

  var STAT_STRIP_MOUNT = "sim-stat-strip";
  var BOT_TABLE_MOUNT = "bot-status-table";
  var FLEET_REPLAY_MOUNT = "fleet-replay";
  var NUCLEAR_MOUNT = "nuclear-mode";
  var PRICE_CHART_MOUNT = "sim-price-chart";
  var VOTING_PANEL_MOUNT = "indicator-voting-panel";
  var GATE_PANEL_MOUNT = "gate-status-panel";

  var DRAWN_MOUNTS = [
    STAT_STRIP_MOUNT,
    BOT_TABLE_MOUNT,
    FLEET_REPLAY_MOUNT,
    NUCLEAR_MOUNT,
    PRICE_CHART_MOUNT,
    VOTING_PANEL_MOUNT,
    GATE_PANEL_MOUNT
  ];

  var PART_ATTR = "data-part";
  var SLOT_ATTR = "data-slot";
  var KEY_ATTR = "data-key";
  var ACTION_ATTR = "data-action";
  var INDEX_ATTR = "data-index";
  var CURRENT_ATTR = "data-current";
  var HOVERED_ATTR = "data-hovered";
  var CHECKED_ATTR = "data-checked";
  var COUNT_ATTR = "data-count";
  var ORIENTATION_ATTR = "data-orientation";
  var ARIA_LABEL = "aria-label";

  var HOVER_STATE = "hover";
  var CHECKED_STATE = "checked";

  var ZERO = Number(EMPTY);
  var STEP = Number(true);

  var held = null;
  var simFaults = [];
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

  // An empty tooltip stays off, so label writes no title attribute.
  function label(value) {
    return typeof value === "string" && value.length ? value : undefined;
  }

  function afterFirst(value, splitter) {
    var parts = String(value).split(splitter);
    parts.shift();
    return parts;
  }

  function carries(value, splitter) {
    return Boolean(afterFirst(value, splitter).length);
  }

  // variableFor asks acervatorWidgets for the one token carrying a value.
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
  function scaled(value, groups) {
    if (value === null || value === undefined) {
      return undefined;
    }
    var name = variableInGroups(value, groups);
    if (name === undefined) {
      return String(value) + PX;
    }
    return (
      CALC_OPEN + VAR_OPEN + name + VAR_SPLIT + String(value) + VAR_CLOSE + PX_FACTOR
    );
  }

  function length(value) {
    return scaled(value, SPACE_GROUPS);
  }

  function widthOf(value) {
    return scaled(value, WIDTH_GROUPS);
  }

  // declarations asks acervatorHeader to read one Qt sheet.
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

  // The style a named Qt state paints, `:hover` and `:checked` alike.
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

  function merged(base, extra) {
    Object.keys(extra).forEach(function (name) {
      base[name] = extra[name];
    });
    return base;
  }

  // The surface publishes a margin in left, top, right, bottom order.
  var PADDING_SIDES = ["paddingLeft", "paddingTop", "paddingRight", "paddingBottom"];

  function marginStyle(margins) {
    var style = {};
    var sides = Array.isArray(margins) ? margins : [];
    PADDING_SIDES.forEach(function (side, at) {
      if (at < sides.length) {
        style[side] = length(sides[at]);
      }
    });
    return style;
  }

  function boxStyle(margins, gap, direction) {
    var style = marginStyle(margins);
    style.display = FLEX;
    style.flexDirection = direction;
    style.gap = length(gap);
    return style;
  }

  function chrome(model, name) {
    return objectField(model, CHROME)[name];
  }

  function words(model, name) {
    return objectField(model, TEXT)[name];
  }

  function unsetSpacing(model) {
    return chrome(model, QT_UNSET_SPACING);
  }

  function nestedMargins(model) {
    return chrome(model, QT_NESTED_MARGINS);
  }

  // A Qt label clips its text and refuses a drag selection.
  function labelStyle(model, sheet) {
    var style = styleOf(sheet);
    style.userSelect = words(model, LABEL_SELECTABLE) === true ? TEXT_SELECT : NONE;
    style.whiteSpace = words(model, LABEL_WORD_WRAP) === true ? PRE_WRAP : NOWRAP;
    style.overflow = HIDDEN;
    style.flex = FLEX_NONE;
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
    var sent = copyOf(params);
    sent[ACTION_PARAM] = name;
    return global.acervator.call(METHOD, sent);
  }

  function actionName(model, name) {
    var found = objectField(objectField(model, WIRING), ACTIONS);
    return owns(found, name) ? name : undefined;
  }

  function Stretch(props) {
    var spacerProps = { style: { flex: AUTO } };
    spacerProps[PART_ATTR] = STRETCH_PART;
    spacerProps[SLOT_ATTR] = props.slot;
    return element(DIV_TAG, spacerProps, null);
  }

  // Mount marks an empty host another unit fills with its own screen.
  function Mount(props) {
    var mountProps = { style: { display: FLEX, flexDirection: COLUMN } };
    if (props.grow !== undefined) {
      mountProps.style.flexGrow = props.grow;
      mountProps.style.flexBasis = ZERO;
      mountProps.style.overflow = HIDDEN;
    } else {
      mountProps.style.flex = FLEX_NONE;
    }
    mountProps[PART_ATTR] = props.slot;
    mountProps[SLOT_ATTR] = props.slot;
    return element(DIV_TAG, mountProps, null);
  }

  function Caption(props) {
    var style = labelStyle(props.model, props.sheet);
    var captionProps = { className: CELL_CLASS, style: style };
    captionProps[PART_ATTR] = props.part;
    captionProps[KEY_ATTR] = props.slot;
    return element(SPAN_TAG, captionProps, text(props.text));
  }

  function HoverButton(props) {
    var state = hooks().useState(false);
    var hovered = state.shift();
    var setHovered = state.shift();
    var style = styleOf(props.sheet);
    style.flex = FLEX_NONE;
    style.whiteSpace = NOWRAP;
    if (props.checked === true) {
      merged(style, stateStyle(props.sheet, CHECKED_STATE));
    }
    if (hovered === true) {
      merged(style, stateStyle(props.sheet, HOVER_STATE));
    }
    var buttonProps = {
      className: INPUT_CLASS,
      style: style,
      type: BUTTON_TYPE,
      title: label(props.tooltip),
      onMouseOver: function () {
        setHovered(true);
      },
      onMouseOut: function () {
        setHovered(false);
      },
      onClick: props.onPress
    };
    buttonProps[PART_ATTR] = props.part;
    buttonProps[SLOT_ATTR] = props.slot;
    buttonProps[ACTION_ATTR] = text(props.action);
    buttonProps[HOVERED_ATTR] = text(hovered);
    buttonProps[CHECKED_ATTR] = text(props.checked);
    buttonProps[ARIA_LABEL] = label(props.tooltip);
    return element(BUTTON_TAG, buttonProps, text(props.text));
  }

  // Qt keeps a dropdown by row, so the option value is the row number.
  function Picker(props) {
    var state = hooks().useState(props.index);
    var at = state.shift();
    var setAt = state.shift();
    var style = { flex: FLEX_NONE, minWidth: widthOf(props.minimumWidth) };
    var shown = text(at);
    var pickerProps = {
      className: INPUT_CLASS,
      style: style,
      title: label(props.tooltip),
      value: shown === undefined ? EMPTY : shown,
      onChange: function (event) {
        var picked = Number(event.target.value);
        setAt(picked);
        if (typeof props.onPick === "function") {
          props.onPick(picked);
        }
      }
    };
    pickerProps[PART_ATTR] = props.part;
    pickerProps[INDEX_ATTR] = text(at);
    pickerProps[ACTION_ATTR] = text(props.action);
    pickerProps[COUNT_ATTR] = String(props.items.length);
    pickerProps[ARIA_LABEL] = label(props.tooltip);
    var drawn = props.items.map(function (pair, order) {
      var one = Array.isArray(pair) ? pair.slice() : [];
      var caption = one.shift();
      var value = one.shift();
      var optionProps = {
        key: String(order),
        value: String(order),
        title: label(props.tooltips[order])
      };
      optionProps[INDEX_ATTR] = String(order);
      optionProps[KEY_ATTR] = text(value);
      return element(OPTION_TAG, optionProps, text(caption));
    });
    return element(SELECT_TAG, pickerProps, drawn);
  }

  function pickerData(items, at) {
    var pair = at < items.length && at >= ZERO ? items[at] : undefined;
    var one = Array.isArray(pair) ? pair.slice() : [];
    one.shift();
    return one.shift();
  }

  // Splitter drags in pixels, so no pane is ever divided into a ratio.
  function Splitter(props) {
    var state = hooks().useState(null);
    var moved = state.shift();
    var setMoved = state.shift();
    var sizes = moved === null ? props.sizes : moved;
    var vertical = props.orientation === VERTICAL;
    var style = {
      display: FLEX,
      flexDirection: vertical ? COLUMN : ROW,
      flex: AUTO,
      overflow: HIDDEN,
      minWidth: ZERO,
      minHeight: ZERO
    };
    var splitProps = { className: TAB_CLASS, style: style };
    splitProps[PART_ATTR] = props.part;
    splitProps[ORIENTATION_ATTR] = text(props.orientation);

    function grow(at) {
      var wanted = Number(sizes[at]);
      return wanted === wanted ? wanted : ZERO;
    }

    function paneStyle(at) {
      return {
        display: FLEX,
        flexDirection: COLUMN,
        flexGrow: grow(at),
        flexBasis: ZERO,
        overflow: HIDDEN,
        minWidth: ZERO,
        minHeight: ZERO
      };
    }

    function pane(at, child) {
      var paneProps = { key: String(at), className: TAB_CLASS, style: paneStyle(at) };
      paneProps[PART_ATTR] = SPLITTER_PANE_PART;
      paneProps[SLOT_ATTR] = props.part;
      paneProps[INDEX_ATTR] = String(at);
      return element(DIV_TAG, paneProps, child);
    }

    function onDown(event) {
      var box = event.currentTarget.parentNode;
      if (!box || !global.document) {
        return;
      }
      var panes = box.children;
      var first = vertical ? panes[ZERO].clientHeight : panes[ZERO].clientWidth;
      var last = vertical
        ? panes[STEP + STEP].clientHeight
        : panes[STEP + STEP].clientWidth;
      var whole = first + last;
      var start = vertical ? event.clientY : event.clientX;
      var least = Number(props.minimum);
      function onMove(step) {
        var now = vertical ? step.clientY : step.clientX;
        var wanted = first + (now - start);
        if (wanted < least) {
          wanted = least;
        }
        if (whole - wanted < least) {
          wanted = whole - least;
        }
        setMoved([wanted, whole - wanted]);
      }
      function onUp() {
        global.document.removeEventListener(MOUSE_MOVE, onMove);
        global.document.removeEventListener(MOUSE_UP, onUp);
      }
      global.document.addEventListener(MOUSE_MOVE, onMove);
      global.document.addEventListener(MOUSE_UP, onUp);
    }

    var handleStyle = {
      flex: FLEX_NONE,
      cursor: vertical ? COLUMN_CURSOR : ROW_CURSOR
    };
    if (vertical) {
      handleStyle.height = length(props.handle);
    } else {
      handleStyle.width = length(props.handle);
    }
    var handleProps = { key: SPLITTER_HANDLE_PART, style: handleStyle };
    handleProps[PART_ATTR] = SPLITTER_HANDLE_PART;
    handleProps[SLOT_ATTR] = props.part;
    handleProps.onMouseDown = onDown;

    return element(
      DIV_TAG,
      splitProps,
      pane(ZERO, props.first),
      element(DIV_TAG, handleProps, null),
      pane(STEP, props.last)
    );
  }

  function splitterProps(model, name, part, first, last) {
    return {
      part: part,
      sizes: listField(objectField(model, CHROME), name + SIZES_TAIL),
      handle: chrome(model, name + HANDLE_TAIL),
      orientation: chrome(model, name + ORIENTATION_TAIL),
      minimum: chrome(model, SPLITTER_MINIMUM),
      first: first,
      last: last
    };
  }

  function ModeRow(props) {
    var model = props.model;
    var picked = objectField(model, MODES);
    var style = boxStyle(chrome(model, MODE_ROW_MARGINS), unsetSpacing(model), ROW);
    style.alignItems = CENTER;
    style.flex = FLEX_NONE;
    var rowProps = { className: TAB_CLASS, style: style };
    rowProps[PART_ATTR] = MODE_ROW_PART;
    var items = listField(picked, ITEMS);
    return element(
      DIV_TAG,
      rowProps,
      element(Caption, {
        key: MODE_LABEL_PART,
        part: MODE_LABEL_PART,
        slot: MODE_LABEL,
        model: model,
        sheet: words(model, MODE_LABEL_STYLE),
        text: words(model, MODE_LABEL)
      }),
      element(Picker, {
        key: MODE_SELECTOR_PART,
        part: MODE_SELECTOR_PART,
        items: items,
        tooltips: listField(picked, ITEM_TOOLTIPS),
        index: picked[INDEX],
        minimumWidth: picked[SELECTOR_MIN_WIDTH],
        tooltip: picked[SELECTOR_TOOLTIP],
        action: actionName(model, MODE_ACTION),
        onPick: function (at) {
          var params = {};
          params[MODE_PARAM] = pickerData(items, at);
          dispatch(MODE_ACTION, params);
        }
      }),
      element(Caption, {
        key: MODE_HINT_PART,
        part: MODE_HINT_PART,
        slot: HINT_TEXT,
        model: model,
        sheet: words(model, MODE_HINT_STYLE),
        text: picked[HINT_TEXT]
      }),
      element(Stretch, { key: STRETCH_PART, slot: MODE_ROW_PART })
    );
  }

  function ActiveBotRow(props) {
    var model = props.model;
    var picked = objectField(objectField(model, PICKERS), ACTIVE);
    var style = boxStyle(
      chrome(model, ACTIVE_BOT_ROW_MARGINS),
      unsetSpacing(model),
      ROW
    );
    style.alignItems = CENTER;
    style.flex = FLEX_NONE;
    var rowProps = { className: TAB_CLASS, style: style };
    rowProps[PART_ATTR] = ACTIVE_BOT_ROW_PART;
    return element(
      DIV_TAG,
      rowProps,
      element(Caption, {
        key: ACTIVE_BOT_LABEL_PART,
        part: ACTIVE_BOT_LABEL_PART,
        slot: ACTIVE_BOT_LABEL,
        model: model,
        sheet: words(model, ACTIVE_BOT_LABEL_STYLE),
        text: words(model, ACTIVE_BOT_LABEL)
      }),
      element(Picker, {
        key: ACTIVE_BOT_PICKER_PART,
        part: ACTIVE_BOT_PICKER_PART,
        items: listField(picked, ITEMS),
        tooltips: [],
        index: picked[INDEX],
        minimumWidth: picked[MINIMUM_WIDTH],
        tooltip: picked[TOOLTIP],
        action: undefined,
        onPick: undefined
      }),
      element(Stretch, { key: STRETCH_PART, slot: ACTIVE_BOT_ROW_PART })
    );
  }

  function ChartPickRow(props) {
    var model = props.model;
    var picked = objectField(objectField(model, PICKERS), CHART);
    var items = listField(picked, ITEMS);
    var style = boxStyle(
      chrome(model, CHART_PICK_ROW_MARGINS),
      unsetSpacing(model),
      ROW
    );
    style.alignItems = CENTER;
    style.flex = FLEX_NONE;
    var rowProps = { className: TAB_CLASS, style: style };
    rowProps[PART_ATTR] = CHART_PICK_ROW_PART;
    return element(
      DIV_TAG,
      rowProps,
      element(Caption, {
        key: CHART_PICK_LABEL_PART,
        part: CHART_PICK_LABEL_PART,
        slot: CHART_PICK_LABEL,
        model: model,
        sheet: words(model, CHART_PICK_LABEL_STYLE),
        text: words(model, CHART_PICK_LABEL)
      }),
      element(Picker, {
        key: CHART_BOT_PICKER_PART,
        part: CHART_BOT_PICKER_PART,
        items: items,
        tooltips: [],
        index: picked[INDEX],
        minimumWidth: picked[MINIMUM_WIDTH],
        tooltip: picked[TOOLTIP],
        action: actionName(model, CHART_ACTION),
        onPick: function (at) {
          var params = {};
          params[CHART_PARAM] = pickerData(items, at);
          dispatch(CHART_ACTION, params);
        }
      }),
      element(Stretch, { key: STRETCH_PART, slot: CHART_PICK_ROW_PART })
    );
  }

  function BotArea(props) {
    var model = props.model;
    var style = boxStyle(
      chrome(model, BOT_AREA_MARGINS),
      chrome(model, BOT_AREA_SPACING),
      COLUMN
    );
    style.flex = FLEX_NONE;
    var areaProps = { className: TAB_CLASS, style: style };
    areaProps[PART_ATTR] = BOT_AREA_PART;
    var drawn = [element(ActiveBotRow, { key: ACTIVE_BOT_ROW_PART, model: model })];
    if (objectField(model, TABLE)[MOUNTED] === true) {
      drawn.push(element(Mount, { key: BOT_TABLE_MOUNT, slot: BOT_TABLE_MOUNT }));
    }
    return element(DIV_TAG, areaProps, drawn);
  }

  function FleetPage(props) {
    var model = props.model;
    var style = boxStyle(
      chrome(model, FLEET_PAGE_MARGINS),
      chrome(model, FLEET_PAGE_SPACING),
      COLUMN
    );
    style.flex = AUTO;
    style.overflow = HIDDEN;
    var pageProps = {
      className: TAB_CLASS,
      style: style,
      hidden: props.current !== true
    };
    pageProps[PART_ATTR] = FLEET_PAGE_PART;
    pageProps[CURRENT_ATTR] = text(props.current);
    var wired = objectField(model, WIRING)[FLEET_PANEL_SET] === true;
    var panel = wired
      ? element(Mount, {
          key: FLEET_REPLAY_MOUNT,
          slot: FLEET_REPLAY_MOUNT,
          grow: chrome(model, FLEET_PANEL_STRETCH)
        })
      : element(Caption, {
          key: FLEET_UNAVAILABLE_PART,
          part: FLEET_UNAVAILABLE_PART,
          slot: FLEET_PANEL_UNAVAILABLE,
          model: model,
          sheet: undefined,
          text: words(model, FLEET_PANEL_UNAVAILABLE)
        });
    return element(
      DIV_TAG,
      pageProps,
      element(BotArea, { key: BOT_AREA_PART, model: model }),
      panel
    );
  }

  function NuclearPage(props) {
    var model = props.model;
    var style = { display: FLEX, flexDirection: COLUMN, flex: AUTO };
    style.overflow = HIDDEN;
    var pageProps = {
      className: TAB_CLASS,
      style: style,
      hidden: props.current !== true
    };
    pageProps[PART_ATTR] = NUCLEAR_PAGE_PART;
    pageProps[CURRENT_ATTR] = text(props.current);
    var wired = objectField(model, WIRING)[NUCLEAR_PANEL_SET] === true;
    var panel = wired
      ? element(Mount, {
          key: NUCLEAR_MOUNT,
          slot: NUCLEAR_MOUNT,
          grow: chrome(model, STACK_STRETCH)
        })
      : element(Caption, {
          key: NUCLEAR_UNAVAILABLE_PART,
          part: NUCLEAR_UNAVAILABLE_PART,
          slot: NUCLEAR_PANEL_UNAVAILABLE,
          model: model,
          sheet: undefined,
          text: words(model, NUCLEAR_PANEL_UNAVAILABLE)
        });
    return element(DIV_TAG, pageProps, panel);
  }

  function Stack(props) {
    var model = props.model;
    var picked = objectField(model, MODES);
    var at = picked[STACK_INDEX];
    var style = { display: FLEX, flexDirection: COLUMN };
    style.flexGrow = chrome(model, STACK_STRETCH);
    style.flexBasis = ZERO;
    style.overflow = HIDDEN;
    var stackProps = { className: TAB_CLASS, style: style };
    stackProps[PART_ATTR] = STACK_PART;
    stackProps[INDEX_ATTR] = text(at);
    stackProps[COUNT_ATTR] = text(picked[STACK_COUNT]);
    return element(
      DIV_TAG,
      stackProps,
      element(FleetPage, {
        key: FLEET_PAGE_PART,
        model: model,
        current: at === picked[FLEET_PAGE_INDEX]
      }),
      element(NuclearPage, {
        key: NUCLEAR_PAGE_PART,
        model: model,
        current: at === picked[NUCLEAR_PAGE_INDEX]
      })
    );
  }

  function Content(props) {
    var model = props.model;
    var style = boxStyle(
      chrome(model, CONTENT_MARGINS),
      chrome(model, CONTENT_SPACING),
      COLUMN
    );
    style.flex = AUTO;
    style.overflow = HIDDEN;
    var contentProps = { className: TAB_CLASS, style: style };
    contentProps[PART_ATTR] = CONTENT_PART;
    return element(
      DIV_TAG,
      contentProps,
      element(ModeRow, { key: MODE_ROW_PART, model: model }),
      element(Stack, { key: STACK_PART, model: model })
    );
  }

  function TitledBox(props) {
    var model = props.model;
    var style = boxStyle(
      chrome(model, TITLED_MARGINS),
      chrome(model, TITLED_SPACING),
      COLUMN
    );
    style.flex = AUTO;
    style.overflow = HIDDEN;
    var boxProps = { className: TAB_CLASS, style: style };
    boxProps[PART_ATTR] = TITLED_BOX_PART;
    boxProps[KEY_ATTR] = text(props.title);

    var headStyle = boxStyle(nestedMargins(model), unsetSpacing(model), ROW);
    headStyle.alignItems = CENTER;
    headStyle.flex = FLEX_NONE;
    var headProps = { key: TITLED_HEAD_PART, className: TAB_CLASS, style: headStyle };
    headProps[PART_ATTR] = TITLED_HEAD_PART;

    var scrollStyle = {
      display: FLEX,
      flexDirection: COLUMN,
      flexGrow: chrome(model, SCROLL_STRETCH),
      flexBasis: ZERO,
      overflowY: AUTO,
      overflowX: HIDDEN,
      minHeight: length(chrome(model, SCROLL_MINIMUM_HEIGHT))
    };
    var scrollProps = { key: SCROLL_PART, className: TAB_CLASS, style: scrollStyle };
    scrollProps[PART_ATTR] = SCROLL_PART;
    scrollProps[SLOT_ATTR] = props.slot;

    var head = element(
      DIV_TAG,
      headProps,
      element(Caption, {
        key: SECTION_LABEL_PART,
        part: SECTION_LABEL_PART,
        slot: props.title,
        model: model,
        sheet: objectField(model, IDENTITY)[SECTION_LABEL_STYLE],
        text: props.title
      }),
      element(Stretch, { key: STRETCH_PART, slot: TITLED_HEAD_PART }),
      element(HoverButton, {
        key: EXPAND_BUTTON_PART,
        part: EXPAND_BUTTON_PART,
        slot: props.slot,
        sheet: words(model, EXPAND_STYLE),
        text: words(model, EXPAND),
        tooltip: props.tooltip,
        checked: undefined,
        action: actionName(model, props.action),
        onPress: function () {
          dispatch(props.action, {});
        }
      })
    );

    var drawn = [head];
    if (props.picker === true) {
      drawn.push(element(ChartPickRow, { key: CHART_PICK_ROW_PART, model: model }));
    }
    drawn.push(
      element(DIV_TAG, scrollProps, element(Mount, { key: props.slot, slot: props.slot }))
    );
    return element(DIV_TAG, boxProps, drawn);
  }

  function IndicatorWrap(props) {
    var model = props.model;
    var style = boxStyle(
      chrome(model, INDICATOR_WRAP_MARGINS),
      unsetSpacing(model),
      COLUMN
    );
    style.flex = AUTO;
    style.overflow = HIDDEN;
    var wrapProps = { className: TAB_CLASS, style: style };
    wrapProps[PART_ATTR] = INDICATOR_WRAP_PART;

    var innerStyle = styleOf(chrome(model, INDICATOR_STYLE));
    merged(
      innerStyle,
      boxStyle(
        chrome(model, INDICATOR_INNER_MARGINS),
        chrome(model, INDICATOR_INNER_SPACING),
        COLUMN
      )
    );
    innerStyle.flexGrow = chrome(model, INDICATOR_CONTAINER_STRETCH);
    innerStyle.flexBasis = ZERO;
    innerStyle.overflow = HIDDEN;
    var innerProps = {
      key: INDICATOR_CONTAINER_PART,
      className: TAB_CLASS,
      style: innerStyle
    };
    innerProps[PART_ATTR] = INDICATOR_CONTAINER_PART;
    innerProps[KEY_ATTR] = text(chrome(model, INDICATOR_OBJECT_NAME));

    var tooltips = listField(objectField(model, TEXT), EXPAND_TOOLTIPS);
    var chartBox = element(TitledBox, {
      key: PRICE_CHART_MOUNT,
      model: model,
      title: words(model, CHART_TITLE),
      tooltip: tooltips[ZERO],
      slot: PRICE_CHART_MOUNT,
      action: CHART_EXPAND_ACTION,
      picker: true
    });
    var votingBox = element(TitledBox, {
      key: VOTING_PANEL_MOUNT,
      model: model,
      title: words(model, VOTING_TITLE),
      tooltip: tooltips[STEP],
      slot: VOTING_PANEL_MOUNT,
      action: VOTING_EXPAND_ACTION,
      picker: false
    });

    return element(
      DIV_TAG,
      wrapProps,
      element(
        DIV_TAG,
        innerProps,
        element(
          Splitter,
          splitterProps(
            model,
            INDICATOR_SPLITTER,
            INDICATOR_SPLITTER_PART,
            chartBox,
            votingBox
          )
        )
      )
    );
  }

  function LogPane(props) {
    var model = props.model;
    var pane = objectField(model, LOG);
    var style = styleOf(words(model, LOG_STYLE));
    style.flex = AUTO;
    style.minHeight = ZERO;
    style.resize = NONE;
    style.overflowY = AUTO;
    style.userSelect = words(model, LOG_SELECTABLE) === true ? TEXT_SELECT : NONE;
    style.whiteSpace = words(model, LOG_WRAPS_AT_WIDTH) === true ? PRE_WRAP : NOWRAP;
    var paneProps = {
      className: INPUT_CLASS,
      style: style,
      readOnly: words(model, LOG_READ_ONLY) === true,
      value: text(pane[PANE_TEXT]),
      onChange: function () {
        return null;
      }
    };
    paneProps[PART_ATTR] = LOG_PANE_PART;
    paneProps[COUNT_ATTR] = String(listField(pane, LINES).length);
    return element(TEXTAREA_TAG, paneProps, null);
  }

  function ActivityBox(props) {
    var model = props.model;
    var pane = objectField(model, LOG);
    var style = boxStyle(
      chrome(model, ACTIVITY_WRAP_MARGINS),
      chrome(model, ACTIVITY_WRAP_SPACING),
      COLUMN
    );
    style.flex = AUTO;
    style.overflow = HIDDEN;
    var wrapProps = { className: TAB_CLASS, style: style };
    wrapProps[PART_ATTR] = ACTIVITY_WRAP_PART;

    var headStyle = boxStyle(nestedMargins(model), unsetSpacing(model), ROW);
    headStyle.alignItems = CENTER;
    headStyle.flex = FLEX_NONE;
    var headProps = { key: LOG_HEADER_PART, className: TAB_CLASS, style: headStyle };
    headProps[PART_ATTR] = LOG_HEADER_PART;

    var paused = pane[ACTIVITY_PAUSED] === true;
    return element(
      DIV_TAG,
      wrapProps,
      element(
        DIV_TAG,
        headProps,
        element(Caption, {
          key: SECTION_LABEL_PART,
          part: SECTION_LABEL_PART,
          slot: SIM_LOG_TITLE,
          model: model,
          sheet: objectField(model, IDENTITY)[SECTION_LABEL_STYLE],
          text: words(model, SIM_LOG_TITLE)
        }),
        element(Stretch, { key: STRETCH_PART, slot: LOG_HEADER_PART }),
        element(HoverButton, {
          key: PAUSE_BUTTON_PART,
          part: PAUSE_BUTTON_PART,
          slot: LOG_PANE_PART,
          sheet: words(model, PAUSE_STYLE),
          text: pane[PAUSE_BUTTON_TEXT],
          tooltip: undefined,
          checked: paused,
          action: actionName(model, PAUSE_ACTION),
          onPress: function () {
            var params = {};
            params[PAUSE_PARAM] = !paused;
            dispatch(PAUSE_ACTION, params);
          }
        })
      ),
      element(LogPane, { key: LOG_PANE_PART, model: model })
    );
  }

  function StatusBox(props) {
    var model = props.model;
    var style = boxStyle(
      chrome(model, GATE_WRAP_MARGINS),
      chrome(model, GATE_WRAP_SPACING),
      COLUMN
    );
    style.flex = AUTO;
    style.overflow = HIDDEN;
    var wrapProps = { className: TAB_CLASS, style: style };
    wrapProps[PART_ATTR] = GATE_WRAP_PART;

    var headStyle = boxStyle(nestedMargins(model), unsetSpacing(model), ROW);
    headStyle.alignItems = CENTER;
    headStyle.flex = FLEX_NONE;
    var headProps = { key: GATE_HEADER_PART, className: TAB_CLASS, style: headStyle };
    headProps[PART_ATTR] = GATE_HEADER_PART;

    var hostStyle = boxStyle(
      chrome(model, GATE_HOST_MARGINS),
      unsetSpacing(model),
      COLUMN
    );
    hostStyle.flex = AUTO;
    hostStyle.overflow = HIDDEN;
    var hostProps = { key: GATE_HOST_PART, className: TAB_CLASS, style: hostStyle };
    hostProps[PART_ATTR] = GATE_HOST_PART;

    var wired = objectField(model, WIRING)[GATE_PANEL_SET] === true;
    var inside = wired
      ? [element(Mount, { key: GATE_PANEL_MOUNT, slot: GATE_PANEL_MOUNT })]
      : [
          element(Caption, {
            key: GATE_UNAVAILABLE_PART,
            part: GATE_UNAVAILABLE_PART,
            slot: GATE_UNAVAILABLE,
            model: model,
            sheet: words(model, GATE_UNAVAILABLE_STYLE),
            text: words(model, GATE_UNAVAILABLE)
          }),
          element(Stretch, { key: STRETCH_PART, slot: GATE_HOST_PART })
        ];

    return element(
      DIV_TAG,
      wrapProps,
      element(
        DIV_TAG,
        headProps,
        element(Caption, {
          key: SECTION_LABEL_PART,
          part: SECTION_LABEL_PART,
          slot: GATE_TITLE,
          model: model,
          sheet: objectField(model, IDENTITY)[SECTION_LABEL_STYLE],
          text: words(model, GATE_TITLE)
        }),
        element(Stretch, { key: STRETCH_PART, slot: GATE_HEADER_PART })
      ),
      element(DIV_TAG, hostProps, inside)
    );
  }

  function Tab(props) {
    var model = isPlainObject(props.model) ? props.model : {};
    var style = boxStyle(
      chrome(model, OUTER_MARGINS),
      chrome(model, OUTER_SPACING),
      COLUMN
    );
    style.overflow = HIDDEN;
    style.flex = AUTO;
    var tabProps = { className: TAB_CLASS, style: style };
    tabProps[PART_ATTR] = TAB_PART;
    tabProps[KEY_ATTR] = text(objectField(model, IDENTITY)[OBJECT_NAME]);
    tabProps[ARIA_LABEL] = label(objectField(model, IDENTITY)[ACCESSIBLE_NAME]);

    var topSplit = element(
      Splitter,
      splitterProps(
        model,
        TOP_SPLITTER,
        TOP_SPLITTER_PART,
        element(Content, { key: CONTENT_PART, model: model }),
        element(IndicatorWrap, { key: INDICATOR_WRAP_PART, model: model })
      )
    );
    var logSplit = element(
      Splitter,
      splitterProps(
        model,
        LOG_SPLITTER,
        LOG_SPLITTER_PART,
        element(ActivityBox, { key: ACTIVITY_WRAP_PART, model: model }),
        element(StatusBox, { key: GATE_WRAP_PART, model: model })
      )
    );

    return element(
      DIV_TAG,
      tabProps,
      element(Mount, { key: STAT_STRIP_MOUNT, slot: STAT_STRIP_MOUNT }),
      element(
        Splitter,
        splitterProps(model, MAIN_SPLITTER, MAIN_SPLITTER_PART, topSplit, logSplit)
      )
    );
  }

  function checkFields(model) {
    DECLARED_FIELDS.forEach(function (name) {
      if (!owns(model, name)) {
        simFaults.push(fault(null, name, MISSING_FAULT, null));
        return;
      }
      if (model[name] === null) {
        simFaults.push(fault(null, name, NULL_FAULT, null));
      }
    });
  }

  var SHEET_FIELDS = [
    MODE_LABEL_STYLE,
    MODE_HINT_STYLE,
    ACTIVE_BOT_LABEL_STYLE,
    CHART_PICK_LABEL_STYLE,
    EXPAND_STYLE,
    PAUSE_STYLE,
    LOG_STYLE,
    GATE_UNAVAILABLE_STYLE
  ];

  // Every sheet the tab paints, named by the field it arrived in.
  function sheetsOf(model) {
    var painted = objectField(model, TEXT);
    var found = [
      {
        where: SECTION_LABEL_STYLE,
        sheet: objectField(model, IDENTITY)[SECTION_LABEL_STYLE]
      },
      { where: INDICATOR_STYLE, sheet: chrome(model, INDICATOR_STYLE) }
    ];
    SHEET_FIELDS.forEach(function (name) {
      found.push({ where: name, sheet: painted[name] });
    });
    return found;
  }

  function checkColours(model) {
    sheetsOf(model).forEach(function (one) {
      declarations(one.sheet).forEach(function (declared) {
        var why = qtColour(declared.value);
        if (why !== undefined) {
          simFaults.push(fault(one.where, declared.property, QT_COLOUR_FAULT, why));
        }
      });
    });
  }

  function checkPicker(name, picked) {
    var items = listField(picked, ITEMS);
    var at = picked[INDEX];
    if (typeof at === "number" && at >= ZERO && at >= items.length) {
      simFaults.push(fault(name, INDEX, UNPLACED_FAULT, at));
    }
    items.forEach(function (pair, order) {
      if (!Array.isArray(pair)) {
        simFaults.push(fault(name, ITEMS, WRONG_TYPE_FAULT, kindOf(pair)));
        return;
      }
      var caption = pair.slice().shift();
      if (caption !== undefined && typeof caption === "object") {
        simFaults.push(
          fault(
            name,
            ITEMS,
            caption === null ? NULL_FAULT : WRONG_TYPE_FAULT,
            order
          )
        );
      }
    });
  }

  function checkPickers(model) {
    var pickers = objectField(model, PICKERS);
    checkPicker(MODES, objectField(model, MODES));
    checkPicker(ACTIVE, objectField(pickers, ACTIVE));
    checkPicker(CHART, objectField(pickers, CHART));
  }

  // The stack shows the page the selected mode routes to, and no other.
  function checkStack(model) {
    var picked = objectField(model, MODES);
    var wanted =
      picked[SELECTED] === picked[NUCLEAR_KEY]
        ? picked[NUCLEAR_PAGE_INDEX]
        : picked[FLEET_PAGE_INDEX];
    if (owns(picked, STACK_INDEX) && picked[STACK_INDEX] !== wanted) {
      simFaults.push(fault(MODES, STACK_INDEX, DISAGREES_FAULT, wanted));
    }
    if (owns(picked, STACK_COUNT) && picked[STACK_COUNT] !== picked[PAGE_TOTAL]) {
      simFaults.push(fault(MODES, STACK_COUNT, DISAGREES_FAULT, picked[PAGE_TOTAL]));
    }
  }

  function paneLines(model) {
    var written = objectField(model, LOG)[PANE_TEXT];
    if (typeof written !== "string" || !written.length) {
      return [];
    }
    return written.split(NEWLINE);
  }

  function checkLog(model) {
    var pane = objectField(model, LOG);
    var lines = listField(pane, LINES);
    if (owns(pane, PANE_TEXT) && paneLines(model).length !== lines.length) {
      simFaults.push(fault(LOG, PANE_TEXT, DISAGREES_FAULT, lines.length));
    }
    lines.forEach(function (one, at) {
      if (typeof one !== "string") {
        simFaults.push(
          fault(LOG, LINES, one === null ? NULL_FAULT : WRONG_TYPE_FAULT, at)
        );
      }
    });
  }

  // Every mount the surface names is one this tab draws, and no other.
  function checkMounts(model) {
    listField(model, MOUNTS).forEach(function (name) {
      var matched = DRAWN_MOUNTS.filter(function (one) {
        return one === String(name);
      });
      if (!matched.length) {
        simFaults.push(fault(MOUNTS, MOUNTS, UNPLACED_FAULT, name));
      }
    });
    DRAWN_MOUNTS.forEach(function (name) {
      var matched = listField(model, MOUNTS).filter(function (one) {
        return String(one) === name;
      });
      if (!matched.length) {
        simFaults.push(fault(MOUNTS, MOUNTS, MISSING_FAULT, name));
      }
    });
  }

  function checkSources() {
    if (!hasSheetSource()) {
      simFaults.push(fault(null, TEXT, NO_SHEET_SOURCE_FAULT, null));
    }
  }

  function heldFieldCount() {
    return DECLARED_FIELDS.filter(function (name) {
      return held !== null && owns(held.model, name);
    }).length;
  }

  function itemCount(bag) {
    return listField(bag, ITEMS).length;
  }

  function drawnMountCount(model) {
    var wired = objectField(model, WIRING);
    var absent = [];
    if (objectField(model, TABLE)[MOUNTED] !== true) {
      absent.push(BOT_TABLE_MOUNT);
    }
    if (wired[FLEET_PANEL_SET] !== true) {
      absent.push(FLEET_REPLAY_MOUNT);
    }
    if (wired[NUCLEAR_PANEL_SET] !== true) {
      absent.push(NUCLEAR_MOUNT);
    }
    if (wired[GATE_PANEL_SET] !== true) {
      absent.push(GATE_PANEL_MOUNT);
    }
    return DRAWN_MOUNTS.length - absent.length;
  }

  function report() {
    var model = held.model;
    var pickers = objectField(model, PICKERS);
    return {
      declared: {
        fields: DECLARED_FIELDS.length,
        modes: listField(objectField(model, MODES), ROWS).length,
        active_items: itemCount(objectField(pickers, ACTIVE)),
        chart_items: itemCount(objectField(pickers, CHART)),
        log_lines: listField(objectField(model, LOG), LINES).length,
        mounts: listField(model, MOUNTS).length,
        pages: objectField(model, MODES)[PAGE_TOTAL]
      },
      held: {
        fields: heldFieldCount(),
        modes: itemCount(objectField(model, MODES)),
        active_items: itemCount(objectField(pickers, ACTIVE)),
        chart_items: itemCount(objectField(pickers, CHART)),
        log_lines: paneLines(model).length,
        mounts: drawnMountCount(model),
        pages: STEP + STEP
      },
      faults: simFaults.slice()
    };
  }

  function setSimulatorTab(model) {
    dispatched = [];
    if (!isPlainObject(model)) {
      held = null;
      simFaults = [fault(null, null, NOT_AN_OBJECT_FAULT, kindOf(model))];
      return { declared: null, held: null, faults: simFaults.slice() };
    }
    held = { model: model };
    simFaults = [];
    checkFields(model);
    checkColours(model);
    checkPickers(model);
    checkStack(model);
    checkLog(model);
    checkMounts(model);
    checkSources();
    return report();
  }

  // A failed load is not remembered, so a later ask reaches the bridge.
  function loadSimulatorTab(params) {
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
        setSimulatorTab(model);
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

  function mountNames() {
    return DRAWN_MOUNTS.slice();
  }

  function pickerOf(name) {
    if (name === MODES) {
      return bag(MODES);
    }
    return copyOf(objectField(bag(PICKERS), name));
  }

  function itemsOf(name) {
    return listField(pickerOf(name), ITEMS).slice();
  }

  function logLines() {
    return paneLines(held === null ? {} : held.model);
  }

  function actions() {
    return copyOf(objectField(bag(WIRING), ACTIONS));
  }

  function focusOrder() {
    return listField(bag(FOCUS), ORDER).slice();
  }

  function focusPolicies() {
    return copyOf(objectField(bag(FOCUS), POLICIES));
  }

  function sent() {
    return dispatched.slice();
  }

  // Every payload value's JavaScript type, by dotted path, null apart.
  function kinds() {
    var found = {};
    function walk(prefix, node) {
      Object.keys(node).forEach(function (name) {
        var path = prefix ? prefix + PATH_SPLIT + name : name;
        found[path] = kindOf(node[name]);
        descend(path, node[name]);
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
    return simFaults.slice();
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
  function draw(target, node) {
    var root = rootFor(target);
    global.ReactDOM.flushSync(function () {
      root.render(node);
    });
    return target;
  }

  function renderTab(target, model) {
    var payload = model;
    if (!isPlainObject(payload)) {
      payload = held === null ? null : held.model;
    }
    return draw(target, element(Tab, { model: payload }));
  }

  function forget() {
    held = null;
    simFaults = [];
    loadFault = null;
    asked = null;
    dispatched = [];
  }

  // The shell draws this tab by its module name; the host reads that name
  // off the script tag running now, so it is written down nowhere.
  if (global.acervatorPanelHost) {
    global.acervatorPanelHost.register({
      render: renderTab,
      load: loadSimulatorTab,
      loadError: loadError
    });
  }

  global.acervatorSetSimulatorTab = setSimulatorTab;
  global.acervatorLoadSimulatorTab = loadSimulatorTab;
  global.acervatorSimulatorTab = {
    method: METHOD,
    Tab: Tab,
    Splitter: Splitter,
    Content: Content,
    ModeRow: ModeRow,
    Stack: Stack,
    FleetPage: FleetPage,
    NuclearPage: NuclearPage,
    BotArea: BotArea,
    ActiveBotRow: ActiveBotRow,
    IndicatorWrap: IndicatorWrap,
    TitledBox: TitledBox,
    ChartPickRow: ChartPickRow,
    ActivityBox: ActivityBox,
    LogPane: LogPane,
    StatusBox: StatusBox,
    HoverButton: HoverButton,
    Picker: Picker,
    Mount: Mount,
    field: field,
    declaredNames: declaredNames,
    mountNames: mountNames,
    pickerOf: pickerOf,
    itemsOf: itemsOf,
    logLines: logLines,
    actions: actions,
    focusOrder: focusOrder,
    focusPolicies: focusPolicies,
    sent: sent,
    declarations: declarations,
    stateRules: stateRules,
    styleOf: styleOf,
    stateStyle: stateStyle,
    qtColour: qtColour,
    keptSheet: keptSheet,
    variableFor: variableFor,
    variableInGroups: variableInGroups,
    length: length,
    widthOf: widthOf,
    spaceGroups: function () {
      return SPACE_GROUPS.slice();
    },
    widthGroups: function () {
      return WIDTH_GROUPS.slice();
    },
    kinds: kinds,
    faults: faults,
    loadError: loadError,
    isLoaded: isLoaded,
    renderTab: renderTab,
    forget: forget
  };
})(window);
