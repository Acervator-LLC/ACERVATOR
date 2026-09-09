// The Trading tab, as the Python surface serves it.
(function (global) {
  "use strict";

  var METHOD = "trading.tab";

  var TAB_TITLE = "tab_title";
  var CONTAINER = "container";
  var MAIN_SPLITTER = "main_splitter";
  var TOP_SPLITTER = "top_splitter";
  var BOTTOM_SPLITTER = "bottom_splitter";
  var LOG_SPLITTER = "log_splitter";
  var EQUITY_EXCHANGE_IDS = "equity_exchange_ids";
  var TRADING_STACK = "trading_stack";
  var LAYERS = "layers";
  var ALIAS_LAYER = "alias_layer";
  var CHART_PRESENT = "chart_present";
  var ACTIVITY_PANE = "activity_pane";
  var API_PANE = "api_pane";
  var WATCHDOG = "watchdog";
  var API_LOG_LISTENER = "api_log_listener";
  var ACTIONS = "actions";

  var DECLARED_FIELDS = [
    ACTIONS,
    ACTIVITY_PANE,
    ALIAS_LAYER,
    API_LOG_LISTENER,
    API_PANE,
    BOTTOM_SPLITTER,
    CHART_PRESENT,
    CONTAINER,
    EQUITY_EXCHANGE_IDS,
    LAYERS,
    LOG_SPLITTER,
    MAIN_SPLITTER,
    TAB_TITLE,
    TOP_SPLITTER,
    TRADING_STACK,
    WATCHDOG
  ];

  var SPLITTER_SLOTS = [MAIN_SPLITTER, TOP_SPLITTER, BOTTOM_SPLITTER, LOG_SPLITTER];

  var ORIENTATION = "orientation";
  var HANDLE_WIDTH = "handle_width_px";
  var CHILDREN_COLLAPSIBLE = "children_collapsible";
  var CHILDREN = "children";
  var SIZES = "sizes_px";
  var MARGINS = "margins_px";
  var SPACING = "spacing_px";
  var LAYOUT = "layout";
  var OUTER_LAYOUT = "outer_layout";
  var HEADER_ROW = "header_row";
  var HEADER_ROW_ORDER = "header_row_order";
  var PAGE_LAYOUT = "page_layout";

  var PAGES = "pages";
  var CURRENT_INDEX = "current_index";

  var KEY = "key";
  var LABEL = "label";
  var ACCENT = "accent";
  var ADD_BUTTON = "add_button";
  var PLACEHOLDER = "placeholder";
  var EXCHANGE_TABS = "exchange_tabs";
  var CURRENT_EXCHANGE = "current_exchange";
  var PLACEHOLDER_SHOWN = "placeholder_shown";
  var TEXT = "text";
  var TOOLTIP = "tooltip";
  var MINIMUM_WIDTH = "minimum_width_px";
  var MINIMUM_SIZE = "minimum_size_px";
  var CORNER_WIDGET = "corner_widget";
  var STYLE_SHEET = "style_sheet";
  var ALIGN = "align";
  var ORDER = "order";
  var CARD = "card";
  var TITLE = "title";
  var HINT = "hint";
  var TAB_TITLE_FIELD = "tab_title";

  var PAUSE_BUTTON = "pause_button";
  var PAUSE_BUFFER = "pause_buffer";
  var STATUS_LOG = "status_log";
  var LOG_VIEW = "log_view";
  var CHECKABLE = "checkable";
  var CHECKED = "checked";
  var BACKGROUND = "background";
  var COLOR = "color";
  var BORDER = "border";
  var BORDER_RADIUS = "border_radius_px";
  var PADDING = "padding_px";
  var FONT_SIZE = "font_size_px";
  var HOVER_BACKGROUND = "hover_background";
  var PAUSED = "paused";
  var BUFFERED = "buffered";
  var CAP = "cap";
  var READ_ONLY = "read_only";
  var WRAP = "wrap";
  var MAX_BLOCKS = "max_blocks";
  var BLOCKS = "blocks";
  var BLOCK_COUNT = "block_count";
  var IS_EMPTY = "is_empty";
  var TAB_INDEX = "tab_index";
  var MAXIMUM_HEIGHT = "maximum_height_px";
  var NOTIFY_RELAY = "notify_relay";

  var ADD_ACTION = "layer.add_button.clicked";
  var PLACEHOLDER_ADD_ACTION = "layer.placeholder_add_button.clicked";
  var ACTIVITY_TOGGLE_ACTION = "activity_pause_button.toggled";
  var API_TOGGLE_ACTION = "api_pause_button.toggled";

  var MISSING_FAULT = "missing";
  var NULL_FAULT = "null";
  var NOT_AN_OBJECT_FAULT = "not-an-object";
  var WRONG_TYPE_FAULT = "wrong-type";
  var QT_COLOUR_FAULT = "qt-colour";
  var DISAGREES_FAULT = "disagrees";
  var SHORT_LIST_FAULT = "short-list";
  var UNSLOTTED_FAULT = "unslotted";

  var NO_BRIDGE = "the preload bridge is not present";

  var LAYER_AT = "layer:";
  var SPLITTER_AT = "splitter:";
  var PANE_AT = "pane:";
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

  // Only these token groups carry a value a CSS length may borrow.
  var LENGTH_GROUPS = ["spacing", "radii", "target_sizes", "table_columns", "focus"];
  // Only this token group carries a value a font size may borrow.
  var FONT_GROUPS = ["type_scale"];

  var ROW = "row";
  var COLUMN = "column";
  var FLEX = "flex";
  var FLEX_NONE = "none";
  var HIDDEN = "hidden";
  var AUTO = "auto";
  // The share of its host a tab takes, which is all of it.
  var FULL = "100%";
  var PRE = "pre";
  var PRE_WRAP = "pre-wrap";
  var CENTER = "center";
  var HORIZONTAL = "horizontal";
  var COL_RESIZE = "col-resize";
  var ROW_RESIZE = "row-resize";
  var BUTTON_TYPE = "button";
  var DIV_TAG = "div";
  var SPAN_TAG = "span";
  var BUTTON_TAG = "button";

  var TAB_CLASS = "acervator-trading-tab";
  var SPLITTER_CLASS = "acervator-trading-splitter";
  var HANDLE_CLASS = "acervator-trading-handle";
  var LAYER_CLASS = "acervator-trading-layer";
  var PANE_CLASS = "acervator-trading-pane";
  var LOG_CLASS = "acervator-trading-api-log";

  var TAB_PART = "tab";
  var SPLITTER_PART = "splitter";
  var PANE_PART = "pane";
  var HANDLE_PART = "handle";
  var STACK_PART = "stack";
  var PAGE_PART = "page";
  var TAB_WIDGET_PART = "tab-widget";
  var TAB_BAR_PART = "tab-bar";
  var TAB_BUTTON_PART = "tab-button";
  var TAB_BODY_PART = "tab-body";
  var ADD_BUTTON_PART = "add-button";
  var PLACEHOLDER_PART = "placeholder";
  var CARD_PART = "placeholder-card";
  var TITLE_PART = "placeholder-title";
  var PLACEHOLDER_ADD_PART = "placeholder-add";
  var HINT_PART = "placeholder-hint";
  var EXCHANGE_PANE_PART = "exchange-pane";
  var EXCHANGE_TAB_BUTTON_PART = "exchange-tab-button";
  var INDICATOR_PART = "indicator-panel";
  var HEADER_ROW_PART = "header-row";
  var PANE_LABEL_PART = "pane-label";
  var STRETCH_PART = "stretch";
  var PAUSE_BUTTON_PART = "pause-button";
  var STATUS_LOG_PART = "status-log";
  var API_LOG_PART = "api-log";
  var API_BLOCK_PART = "api-block";
  var API_PLACEHOLDER_PART = "api-placeholder";

  var STATUS_LOG_MODULE = "status_log";
  var INDICATOR_MODULE = "indicator_panel";
  var EXCHANGE_MODULE = "exchange_tab";
  var LOAD_LOG = "acervatorLoadLog";
  var LOAD_INDICATOR = "acervatorLoadIndicatorPanel";
  var LOAD_EXCHANGE = "acervatorLoadExchangeTab";
  var EXCHANGE_API = "acervatorExchangeTab";
  var EXCHANGE_ID_PARAM = "exchange_id";
  var EXCHANGE_NAME_PARAM = "exchange_name";
  var EXCHANGE_PARAM = "exchange";
  var ACTIVITY_PAUSED_PARAM = "activity_paused";
  var API_PAUSED_PARAM = "api_paused";
  var LOG_API = "acervatorLog";

  var PART_ATTR = "data-part";
  var CHILD_ATTR = "data-child-module";
  var SLOT_ATTR = "data-slot";
  var KEY_ATTR = "data-key";
  var ACTION_ATTR = "data-action";
  var INDEX_ATTR = "data-index";
  var ORIENTATION_ATTR = "data-orientation";
  var COLLAPSIBLE_ATTR = "data-collapsible";
  var LAYER_ATTR = "data-layer";
  var CURRENT_ATTR = "data-current";
  var EXCHANGE_ATTR = "data-exchange";
  var HOVERED_ATTR = "data-hovered";
  var CHECKED_ATTR = "data-checked";
  var BLOCKS_ATTR = "data-block-count";
  var MAX_BLOCKS_ATTR = "data-max-blocks";
  var WRAP_ATTR = "data-wrap";
  var READ_ONLY_ATTR = "data-read-only";
  var PAUSED_ATTR = "data-paused";
  var BUFFERED_ATTR = "data-buffered";
  var CAP_ATTR = "data-cap";
  var ACCENT_ATTR = "data-accent";
  var TABS_ATTR = "data-exchange-tabs";
  var CHART_ATTR = "data-chart-present";
  var DECLARED_PANES_ATTR = "data-declared-panes";
  var HELD_PANES_ATTR = "data-held-panes";
  var ARIA_LABEL = "aria-label";
  var ARIA_PRESSED = "aria-pressed";
  var ARIA_READONLY = "aria-readonly";
  var ARIA_ORIENTATION = "aria-orientation";
  var SEPARATOR_ROLE = "separator";

  var SELECT_OPEN = "[";
  var SELECT_IS = "=\"";
  var SELECT_CLOSE = "\"]";

  var MOUSE_MOVE = "mousemove";
  var MOUSE_UP = "mouseup";

  var HOVER_STATE = "hover";
  var CHECKED_STATE = "checked";

  // The step from one pane to the one the handle between them moves.
  var STEP = Number(true);
  var ZERO = Number(EMPTY);

  var held = null;
  var tradingFaults = [];
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

  // A tooltip, on the surface's own terms: an empty one stays off.
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

  // `shared_widgets.js` owns the one-carrier rule that names a token.
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
    return scaled(value, LENGTH_GROUPS);
  }

  function fontSize(value) {
    return scaled(value, FONT_GROUPS);
  }

  // A colour painted through the one token that carries it.
  function colour(value) {
    var name = variableFor(value);
    if (name === undefined) {
      return text(value);
    }
    return VAR_OPEN + name + VAR_SPLIT + String(value) + VAR_CLOSE;
  }

  // `header_strip.js` owns the sheet parser and the camel-case rule.
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

  // Whether one value counts its alpha in bytes, as Qt does and CSS
  // does not.
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

  // The surface publishes a margin in left, top, right, bottom order.
  var PADDING_SIDES = ["paddingLeft", "paddingTop", "paddingRight", "paddingBottom"];

  function marginStyle(layout, field) {
    var style = {};
    var margins = listField(layout, field);
    PADDING_SIDES.forEach(function (side, at) {
      if (at < margins.length) {
        style[side] = length(margins[at]);
      }
    });
    return style;
  }

  function boxStyle(layout, direction) {
    var style = marginStyle(layout, MARGINS);
    style.display = FLEX;
    style.flexDirection = direction;
    if (owns(layout, SPACING)) {
      style.gap = length(layout[SPACING]);
    }
    return style;
  }

  function sizeStyle(bag, field) {
    var style = {};
    var sizes = listField(bag, field).slice();
    if (sizes.length) {
      style.minWidth = length(sizes.shift());
    }
    if (sizes.length) {
      style.minHeight = length(sizes.shift());
    }
    return style;
  }

  function centred(style, word) {
    if (word === CENTER) {
      style.alignItems = CENTER;
      style.justifyContent = CENTER;
      style.textAlign = CENTER;
    }
    return style;
  }

  function element() {
    return global.React.createElement.apply(null, arguments);
  }

  function hooks() {
    return global.React;
  }

  function isHorizontal(model) {
    return model[ORIENTATION] === HORIZONTAL;
  }

  function Handle(props) {
    var model = props.model;
    var across = isHorizontal(model);
    var style = { flex: FLEX_NONE, cursor: across ? COL_RESIZE : ROW_RESIZE };
    if (across) {
      style.width = length(model[HANDLE_WIDTH]);
    } else {
      style.height = length(model[HANDLE_WIDTH]);
    }
    var handleProps = {
      className: HANDLE_CLASS,
      style: style,
      role: SEPARATOR_ROLE,
      onMouseDown: props.onGrab
    };
    handleProps[PART_ATTR] = HANDLE_PART;
    handleProps[INDEX_ATTR] = String(props.at);
    handleProps[ARIA_ORIENTATION] = text(model[ORIENTATION]);
    return element(DIV_TAG, handleProps, null);
  }

  // A splitter draws one pane per child, a draggable handle between two.
  function Splitter(props) {
    var model = isPlainObject(props.model) ? props.model : {};
    var across = isHorizontal(model);
    var state = hooks().useState(listField(model, SIZES));
    var sizes = state.shift();
    var setSizes = state.shift();
    var panes = hooks().useRef([]);

    function grab(at) {
      return function (event) {
        var first = panes.current[at];
        var next = panes.current[at + STEP];
        if (!first || !next) {
          return;
        }
        event.preventDefault();
        var startAt = across ? event.clientX : event.clientY;
        var firstBox = first.getBoundingClientRect();
        var nextBox = next.getBoundingClientRect();
        var firstSize = across ? firstBox.width : firstBox.height;
        var nextSize = across ? nextBox.width : nextBox.height;
        var lowest = model[CHILDREN_COLLAPSIBLE] === false ? model[HANDLE_WIDTH] : ZERO;

        function move(moved) {
          var now = across ? moved.clientX : moved.clientY;
          var shift = now - startAt;
          var taken = Math.min(Math.max(shift, lowest - firstSize), nextSize - lowest);
          var drawn = sizes.slice();
          drawn[at] = firstSize + taken;
          drawn[at + STEP] = nextSize - taken;
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
    var splitterProps = { className: SPLITTER_CLASS, style: style };
    splitterProps[PART_ATTR] = SPLITTER_PART;
    splitterProps[SLOT_ATTR] = props.slot;
    splitterProps[ORIENTATION_ATTR] = text(model[ORIENTATION]);
    splitterProps[COLLAPSIBLE_ATTR] = text(model[CHILDREN_COLLAPSIBLE]);
    splitterProps[DECLARED_PANES_ATTR] = String(listField(model, CHILDREN).length);
    splitterProps[HELD_PANES_ATTR] = String(props.panes.length);

    var drawn = [];
    props.panes.forEach(function (child, at) {
      if (drawn.length) {
        drawn.push(
          element(Handle, {
            key: HANDLE_PART + String(at),
            at: at - STEP,
            model: model,
            onGrab: grab(at - STEP)
          })
        );
      }
      var paneStyle = { display: FLEX, flexDirection: COLUMN, overflow: HIDDEN };
      paneStyle.flex = String(at < sizes.length ? sizes[at] : EMPTY);
      var paneProps = {
        key: PANE_PART + String(at),
        className: PANE_CLASS,
        style: paneStyle,
        ref: keep(at)
      };
      paneProps[PART_ATTR] = PANE_PART;
      paneProps[INDEX_ATTR] = String(at);
      paneProps[SLOT_ATTR] = child.slot;
      drawn.push(element(DIV_TAG, paneProps, child.node));
    });
    return element(DIV_TAG, splitterProps, drawn);
  }

  // One request to the tab's own method, whose answer replaces the held
  // model and repaints every host this module has drawn into.
  function askTrading(params) {
    if (!global.acervator || typeof global.acervator.call !== "function") {
      loadFault = NO_BRIDGE;
      return Promise.resolve(null);
    }
    return global.acervator
      .call(METHOD, params)
      .then(function (model) {
        loadFault = null;
        setTrading(model);
        redraw();
        return model;
      })
      .catch(function (err) {
        loadFault = err.message;
        return null;
      });
  }

  // `_add_exchange` ends in `_sync_exchange_tabs`, which re-reads the
  // configured exchanges; the answer carries whatever was added.
  function addExchangeAsked() {
    return askTrading({});
  }

  // Qt's toggle pauses the pane as well as flipping the caption.
  function pauseToggled(slot, checked) {
    var wanted = checked !== true;
    var params = {};
    params[slot === ACTIVITY_PANE ? ACTIVITY_PAUSED_PARAM : API_PAUSED_PARAM] = wanted;
    var api = global[LOG_API];
    if (slot === ACTIVITY_PANE && api && typeof api.setPaused === "function") {
      api.setPaused(wanted);
    }
    return askTrading(params);
  }

  function AddButton(props) {
    var model = objectField(props.layer, ADD_BUTTON);
    var style = { minWidth: length(model[MINIMUM_WIDTH]) };
    var buttonProps = {
      className: LAYER_CLASS,
      style: style,
      type: BUTTON_TYPE,
      title: label(model[TOOLTIP]),
      onClick: addExchangeAsked
    };
    buttonProps[PART_ATTR] = ADD_BUTTON_PART;
    buttonProps[KEY_ATTR] = text(props.layer[KEY]);
    buttonProps[ACTION_ATTR] = text(props.actions[ADD_ACTION]);
    buttonProps[SLOT_ATTR] = text(model[CORNER_WIDGET]);
    return element(BUTTON_TAG, buttonProps, text(model[TEXT]));
  }

  function PlaceholderTitle(props) {
    var model = objectField(props.placeholder, TITLE);
    var titleProps = { className: LAYER_CLASS, style: styleOf(model[STYLE_SHEET]) };
    centred(titleProps.style, model[ALIGN]);
    titleProps[PART_ATTR] = TITLE_PART;
    titleProps[KEY_ATTR] = text(props.layerKey);
    return element(DIV_TAG, titleProps, text(model[TEXT]));
  }

  function PlaceholderAdd(props) {
    var model = objectField(props.placeholder, ADD_BUTTON);
    var style = styleOf(model[STYLE_SHEET]);
    var least = sizeStyle(model, MINIMUM_SIZE);
    Object.keys(least).forEach(function (name) {
      style[name] = least[name];
    });
    centred(style, model[ALIGN]);
    var buttonProps = {
      className: LAYER_CLASS,
      style: style,
      type: BUTTON_TYPE,
      onClick: addExchangeAsked
    };
    buttonProps[PART_ATTR] = PLACEHOLDER_ADD_PART;
    buttonProps[KEY_ATTR] = text(props.layerKey);
    buttonProps[ACTION_ATTR] = text(props.actions[PLACEHOLDER_ADD_ACTION]);
    return element(BUTTON_TAG, buttonProps, text(model[TEXT]));
  }

  function PlaceholderHint(props) {
    var model = objectField(props.placeholder, HINT);
    var hintProps = { className: LAYER_CLASS, style: styleOf(model[STYLE_SHEET]) };
    centred(hintProps.style, model[ALIGN]);
    hintProps[PART_ATTR] = HINT_PART;
    hintProps[KEY_ATTR] = text(props.layerKey);
    return element(DIV_TAG, hintProps, text(model[TEXT]));
  }

  function placeholderChild(model, name, layerKey, actions) {
    if (name === TITLE) {
      return element(PlaceholderTitle, {
        key: name,
        placeholder: model,
        layerKey: layerKey
      });
    }
    if (name === ADD_BUTTON) {
      return element(PlaceholderAdd, {
        key: name,
        placeholder: model,
        layerKey: layerKey,
        actions: actions
      });
    }
    if (name === HINT) {
      return element(PlaceholderHint, {
        key: name,
        placeholder: model,
        layerKey: layerKey
      });
    }
    return null;
  }

  // The empty-state card, centred inside the page the tab widget shows.
  function Placeholder(props) {
    var model = objectField(props.layer, PLACEHOLDER);
    var card = objectField(model, CARD);
    var outer = boxStyle(objectField(model, OUTER_LAYOUT), COLUMN);
    outer.flex = AUTO;
    centred(outer, model[ALIGN]);
    var outerProps = { className: LAYER_CLASS, style: outer };
    outerProps[PART_ATTR] = PLACEHOLDER_PART;
    outerProps[KEY_ATTR] = text(props.layer[KEY]);

    var cardStyle = styleOf(card[STYLE_SHEET]);
    var inner = boxStyle(objectField(card, LAYOUT), COLUMN);
    Object.keys(inner).forEach(function (name) {
      cardStyle[name] = inner[name];
    });
    var least = sizeStyle(card, MINIMUM_SIZE);
    Object.keys(least).forEach(function (name) {
      cardStyle[name] = least[name];
    });
    centred(cardStyle, model[ALIGN]);
    if (owns(model, SPACING)) {
      cardStyle.gap = length(model[SPACING]);
    }
    var cardProps = { className: LAYER_CLASS, style: cardStyle };
    cardProps[PART_ATTR] = CARD_PART;
    cardProps[KEY_ATTR] = text(props.layer[KEY]);
    cardProps[ACCENT_ATTR] = text(props.layer[ACCENT]);

    var drawn = listField(model, ORDER).map(function (name) {
      return placeholderChild(model, name, props.layer[KEY], props.actions);
    });
    return element(
      DIV_TAG,
      outerProps,
      element(DIV_TAG, cardProps, drawn)
    );
  }

  // Clicking a tab moves the layer's tab widget to that exchange.
  function exchangeChosen(exchangeId) {
    if (!global.acervator || typeof global.acervator.call !== "function") {
      loadFault = NO_BRIDGE;
      return Promise.resolve(null);
    }
    var params = {};
    params[EXCHANGE_PARAM] = exchangeId;
    return global.acervator
      .call(METHOD, params)
      .then(function (model) {
        loadFault = null;
        setTrading(model);
        redraw();
        return model;
      })
      .catch(function (err) {
        loadFault = err.message;
        return null;
      });
  }

  function ExchangeTabButton(props) {
    var buttonProps = {
      className: LAYER_CLASS,
      style: { flex: FLEX_NONE },
      type: BUTTON_TYPE,
      onClick: function () {
        exchangeChosen(props.exchangeId);
      }
    };
    buttonProps[PART_ATTR] = EXCHANGE_TAB_BUTTON_PART;
    buttonProps[LAYER_ATTR] = props.layerKey;
    buttonProps[EXCHANGE_ATTR] = props.exchangeId;
    buttonProps[CURRENT_ATTR] = text(props.current);
    buttonProps[ARIA_LABEL] = label(props.caption);
    return element(BUTTON_TAG, buttonProps, text(props.caption));
  }

  // `exchange_tab.js` draws its own screen into this space, so React
  // never gives it a child.
  function ExchangePane(props) {
    var paneProps = { style: { display: FLEX, flexDirection: COLUMN, flex: AUTO } };
    paneProps[PART_ATTR] = EXCHANGE_PANE_PART;
    paneProps[LAYER_ATTR] = props.layerKey;
    paneProps[EXCHANGE_ATTR] = props.exchangeId;
    return element(DIV_TAG, paneProps, null);
  }

  // One layer page: a tab bar carrying the corner add button, and the
  // body of the tab on show.
  function LayerPage(props) {
    var layer = props.layer;
    var placeholder = objectField(layer, PLACEHOLDER);
    var pageStyle = boxStyle(objectField(layer, PAGE_LAYOUT), COLUMN);
    pageStyle.flex = AUTO;
    pageStyle.overflow = HIDDEN;
    var pageProps = {
      className: LAYER_CLASS,
      style: pageStyle,
      hidden: props.current !== true
    };
    pageProps[PART_ATTR] = PAGE_PART;
    pageProps[LAYER_ATTR] = text(layer[KEY]);
    pageProps[KEY_ATTR] = text(layer[KEY]);
    pageProps[CURRENT_ATTR] = text(props.current);

    var barProps = { style: { display: FLEX, flexDirection: ROW } };
    barProps[PART_ATTR] = TAB_BAR_PART;
    barProps[LAYER_ATTR] = text(layer[KEY]);

    var tabs = objectField(layer, EXCHANGE_TABS);
    var named = Object.keys(tabs);
    var onShow = text(layer[CURRENT_EXCHANGE]);
    var empty = layer[PLACEHOLDER_SHOWN] !== false;

    var tabProps = { style: { flex: FLEX_NONE } };
    tabProps[PART_ATTR] = TAB_BUTTON_PART;
    tabProps[LAYER_ATTR] = text(layer[KEY]);
    tabProps[ARIA_LABEL] = label(placeholder[TAB_TITLE_FIELD]);

    var spacerProps = { style: { flex: AUTO } };
    spacerProps[PART_ATTR] = STRETCH_PART;
    spacerProps[LAYER_ATTR] = text(layer[KEY]);

    var bodyProps = { style: { flex: AUTO, overflow: AUTO } };
    bodyProps[PART_ATTR] = TAB_BODY_PART;
    bodyProps[LAYER_ATTR] = text(layer[KEY]);
    bodyProps[TABS_ATTR] = text(Object.keys(objectField(layer, EXCHANGE_TABS)).length);

    var widgetProps = { style: { display: FLEX, flexDirection: COLUMN, flex: AUTO } };
    widgetProps[PART_ATTR] = TAB_WIDGET_PART;
    widgetProps[LAYER_ATTR] = text(layer[KEY]);

    var barTabs = empty
      ? [element(SPAN_TAG, tabProps, text(placeholder[TAB_TITLE_FIELD]))]
      : named.map(function (one) {
          return element(ExchangeTabButton, {
            key: one,
            layerKey: text(layer[KEY]),
            exchangeId: one,
            caption: text(tabs[one]),
            current: one === onShow
          });
        });

    var body = empty
      ? element(Placeholder, { layer: layer, actions: props.actions })
      : element(ExchangePane, { layerKey: text(layer[KEY]), exchangeId: onShow });

    return element(
      DIV_TAG,
      pageProps,
      element(
        DIV_TAG,
        widgetProps,
        element(
          DIV_TAG,
          barProps,
          barTabs,
          element(DIV_TAG, spacerProps, null),
          element(AddButton, { layer: layer, actions: props.actions })
        ),
        element(DIV_TAG, bodyProps, body)
      )
    );
  }

  function TradingStack(props) {
    var model = objectField(props.model, TRADING_STACK);
    var pages = listField(model, PAGES);
    var stackProps = {
      style: { display: FLEX, flexDirection: COLUMN, flex: AUTO, overflow: HIDDEN }
    };
    stackProps[PART_ATTR] = STACK_PART;
    stackProps[SLOT_ATTR] = TRADING_STACK;
    stackProps[INDEX_ATTR] = text(model[CURRENT_INDEX]);
    stackProps[DECLARED_PANES_ATTR] = String(pages.length);
    var layers = listField(props.model, LAYERS);
    stackProps[HELD_PANES_ATTR] = String(layers.length);
    var drawn = layers.map(function (layer, at) {
      return element(LayerPage, {
        key: text(isPlainObject(layer) ? layer[KEY] : at) || String(at),
        layer: isPlainObject(layer) ? layer : {},
        current: at === model[CURRENT_INDEX],
        actions: objectField(props.model, ACTIONS)
      });
    });
    return element(DIV_TAG, stackProps, drawn);
  }

  // The panel Qt draws beside the stack, kept as a named empty host.
  function IndicatorPanel() {
    var panelProps = { style: { flex: AUTO, overflow: AUTO } };
    panelProps[PART_ATTR] = INDICATOR_PART;
    panelProps[SLOT_ATTR] = INDICATOR_PART;
    return element(DIV_TAG, panelProps, null);
  }

  function PauseButton(props) {
    var model = isPlainObject(props.model) ? props.model : {};
    var state = hooks().useState(false);
    var hovered = state.shift();
    var setHovered = state.shift();
    var style = styleOf(model[STYLE_SHEET]);
    if (model[CHECKED] === true) {
      var checkedStyle = stateStyle(model[STYLE_SHEET], CHECKED_STATE);
      Object.keys(checkedStyle).forEach(function (name) {
        style[name] = checkedStyle[name];
      });
    }
    if (hovered === true) {
      var hoverStyle = stateStyle(model[STYLE_SHEET], HOVER_STATE);
      Object.keys(hoverStyle).forEach(function (name) {
        style[name] = hoverStyle[name];
      });
    }
    var buttonProps = {
      className: PANE_CLASS,
      style: style,
      type: BUTTON_TYPE,
      title: label(model[TOOLTIP]),
      onClick: function () {
        pauseToggled(props.slot, model[CHECKED] === true);
      },
      onMouseOver: function () {
        setHovered(true);
      },
      onMouseOut: function () {
        setHovered(false);
      }
    };
    buttonProps[PART_ATTR] = PAUSE_BUTTON_PART;
    buttonProps[SLOT_ATTR] = props.slot;
    buttonProps[ACTION_ATTR] = text(props.action);
    buttonProps[CHECKED_ATTR] = text(model[CHECKED]);
    buttonProps[HOVERED_ATTR] = text(hovered);
    buttonProps[ARIA_PRESSED] = text(model[CHECKABLE] === true ? model[CHECKED] : null);
    return element(BUTTON_TAG, buttonProps, text(model[TEXT]));
  }

  function PaneLabel(props) {
    var model = objectField(props.pane, LABEL);
    var labelProps = { className: PANE_CLASS, style: styleOf(model[STYLE_SHEET]) };
    labelProps[PART_ATTR] = PANE_LABEL_PART;
    labelProps[SLOT_ATTR] = props.slot;
    return element(DIV_TAG, labelProps, text(model[TEXT]));
  }

  function headerChild(pane, name, slot, action) {
    if (name === LABEL) {
      return element(PaneLabel, { key: name, pane: pane, slot: slot });
    }
    if (name === PAUSE_BUTTON) {
      return element(PauseButton, {
        key: name,
        model: pane[PAUSE_BUTTON],
        slot: slot,
        action: action
      });
    }
    var spacerProps = { key: name, style: { flex: AUTO } };
    spacerProps[PART_ATTR] = STRETCH_PART;
    spacerProps[SLOT_ATTR] = slot;
    return element(DIV_TAG, spacerProps, null);
  }

  function HeaderRow(props) {
    var pane = props.pane;
    var rowProps = {
      style: boxStyle(objectField(pane, HEADER_ROW), ROW)
    };
    rowProps.style.alignItems = CENTER;
    rowProps[PART_ATTR] = HEADER_ROW_PART;
    rowProps[SLOT_ATTR] = props.slot;
    var drawn = listField(pane, HEADER_ROW_ORDER).map(function (name) {
      return headerChild(pane, name, props.slot, props.action);
    });
    return element(DIV_TAG, rowProps, drawn);
  }

  // The host `status_log.js` draws its own lines into.
  function StatusLogSlot(props) {
    var model = objectField(props.pane, STATUS_LOG);
    var slotProps = {
      style: { flex: AUTO, overflow: AUTO, maxHeight: length(model[MAXIMUM_HEIGHT]) }
    };
    slotProps[PART_ATTR] = STATUS_LOG_PART;
    slotProps[SLOT_ATTR] = STATUS_LOG;
    slotProps[ACTION_ATTR] = text(model[NOTIFY_RELAY]);
    return element(DIV_TAG, slotProps, null);
  }

  // The API log view follows its newest block only while it is already
  // scrolled to the bottom.
  function ApiLogView(props) {
    var model = objectField(props.pane, LOG_VIEW);
    var node = hooks().useRef(null);
    var following = hooks().useRef(true);
    hooks().useLayoutEffect(function () {
      var view = node.current;
      if (view && following.current === true) {
        view.scrollTop = view.scrollHeight;
      }
    });

    function watch(event) {
      var view = event.target;
      following.current =
        Math.ceil(view.scrollTop) + view.clientHeight >= view.scrollHeight;
    }

    var viewProps = {
      className: LOG_CLASS,
      style: {
        flex: AUTO,
        overflow: AUTO,
        whiteSpace: model[WRAP] === true ? PRE_WRAP : PRE
      },
      ref: node,
      onScroll: watch,
      title: label(model[TOOLTIP]),
      tabIndex: model[TAB_INDEX]
    };
    viewProps[PART_ATTR] = API_LOG_PART;
    viewProps[SLOT_ATTR] = LOG_VIEW;
    viewProps[READ_ONLY_ATTR] = text(model[READ_ONLY]);
    viewProps[ARIA_READONLY] = text(model[READ_ONLY]);
    viewProps[WRAP_ATTR] = text(model[WRAP]);
    viewProps[MAX_BLOCKS_ATTR] = text(model[MAX_BLOCKS]);
    viewProps[BLOCKS_ATTR] = text(model[BLOCK_COUNT]);

    if (model[IS_EMPTY] === true) {
      var emptyProps = {};
      emptyProps[PART_ATTR] = API_PLACEHOLDER_PART;
      emptyProps[SLOT_ATTR] = LOG_VIEW;
      return element(
        DIV_TAG,
        viewProps,
        element(DIV_TAG, emptyProps, text(model[PLACEHOLDER]))
      );
    }
    var drawn = listField(model, BLOCKS).map(function (line, at) {
      var lineProps = { key: String(at) };
      lineProps[PART_ATTR] = API_BLOCK_PART;
      lineProps[INDEX_ATTR] = String(at);
      return element(DIV_TAG, lineProps, text(line));
    });
    return element(DIV_TAG, viewProps, drawn);
  }

  function ActivityPane(props) {
    var pane = objectField(props.model, ACTIVITY_PANE);
    var paneProps = {
      className: PANE_CLASS,
      style: boxStyle(objectField(pane, LAYOUT), COLUMN)
    };
    paneProps.style.flex = AUTO;
    paneProps.style.overflow = HIDDEN;
    paneProps[PART_ATTR] = PANE_AT + ACTIVITY_PANE;
    paneProps[SLOT_ATTR] = ACTIVITY_PANE;
    return element(
      DIV_TAG,
      paneProps,
      element(HeaderRow, {
        pane: pane,
        slot: ACTIVITY_PANE,
        action: objectField(props.model, ACTIONS)[ACTIVITY_TOGGLE_ACTION]
      }),
      element(StatusLogSlot, { pane: pane })
    );
  }

  function ApiPane(props) {
    var pane = objectField(props.model, API_PANE);
    var buffer = objectField(pane, PAUSE_BUFFER);
    var paneProps = {
      className: PANE_CLASS,
      style: boxStyle(objectField(pane, LAYOUT), COLUMN)
    };
    paneProps.style.flex = AUTO;
    paneProps.style.overflow = HIDDEN;
    paneProps[PART_ATTR] = PANE_AT + API_PANE;
    paneProps[SLOT_ATTR] = API_PANE;
    paneProps[PAUSED_ATTR] = text(buffer[PAUSED]);
    paneProps[BUFFERED_ATTR] = text(buffer[BUFFERED]);
    paneProps[CAP_ATTR] = text(buffer[CAP]);
    return element(
      DIV_TAG,
      paneProps,
      element(HeaderRow, {
        pane: pane,
        slot: API_PANE,
        action: objectField(props.model, ACTIONS)[API_TOGGLE_ACTION]
      }),
      element(ApiLogView, { pane: pane })
    );
  }

  function splitterOf(model, slot) {
    return objectField(model, slot);
  }

  // A splitter keeps its dragged sizes until the surface names new ones.
  function splitterKey(model, slot) {
    return listField(objectField(model, slot), SIZES).join(COMMA);
  }

  function logSplitterNode(model) {
    return element(Splitter, {
      key: LOG_SPLITTER + splitterKey(model, LOG_SPLITTER),
      slot: LOG_SPLITTER,
      model: splitterOf(model, LOG_SPLITTER),
      panes: [
        { slot: ACTIVITY_PANE, node: element(ActivityPane, { model: model }) },
        { slot: API_PANE, node: element(ApiPane, { model: model }) }
      ]
    });
  }

  function bottomSplitterNode(model) {
    return element(Splitter, {
      key: BOTTOM_SPLITTER + splitterKey(model, BOTTOM_SPLITTER),
      slot: BOTTOM_SPLITTER,
      model: splitterOf(model, BOTTOM_SPLITTER),
      panes: [{ slot: LOG_SPLITTER, node: logSplitterNode(model) }]
    });
  }

  function topSplitterNode(model) {
    return element(Splitter, {
      key: TOP_SPLITTER + splitterKey(model, TOP_SPLITTER),
      slot: TOP_SPLITTER,
      model: splitterOf(model, TOP_SPLITTER),
      panes: [
        { slot: TRADING_STACK, node: element(TradingStack, { model: model }) },
        { slot: INDICATOR_PART, node: element(IndicatorPanel, null) }
      ]
    });
  }

  // `Tab` draws nothing for a payload that is not an object.
  function Tab(props) {
    if (!isPlainObject(props.model)) {
      return null;
    }
    var model = props.model;
    var container = objectField(model, CONTAINER);
    var tabProps = {
      id: props.id,
      className: TAB_CLASS,
      style: boxStyle(container, COLUMN)
    };
    tabProps.style.overflow = HIDDEN;
    tabProps.style.height = FULL;
    tabProps[PART_ATTR] = TAB_PART;
    tabProps[ARIA_LABEL] = label(model[TAB_TITLE]);
    tabProps[LAYER_ATTR] = text(model[ALIAS_LAYER]);
    tabProps[CHART_ATTR] = text(model[CHART_PRESENT]);
    tabProps[ACTION_ATTR] = text(model[API_LOG_LISTENER]);
    return element(
      DIV_TAG,
      tabProps,
      element(Splitter, {
        key: MAIN_SPLITTER,
        slot: MAIN_SPLITTER,
        model: splitterOf(model, MAIN_SPLITTER),
        panes: [
          { slot: TOP_SPLITTER, node: topSplitterNode(model) },
          { slot: BOTTOM_SPLITTER, node: bottomSplitterNode(model) }
        ]
      })
    );
  }

  function checkFields(model) {
    DECLARED_FIELDS.forEach(function (field) {
      if (!owns(model, field)) {
        tradingFaults.push(fault(null, field, MISSING_FAULT, null));
        return;
      }
      if (model[field] === null) {
        tradingFaults.push(fault(null, field, NULL_FAULT, null));
      }
    });
  }

  // A wrong type is named only against a bag the surface publishes twice.
  function checkAgainstPeer(where, bag, peer, fields) {
    fields.forEach(function (field) {
      if (!owns(peer, field) || peer[field] === null) {
        return;
      }
      var wanted = kindOf(peer[field]);
      if (!owns(bag, field)) {
        tradingFaults.push(fault(where, field, MISSING_FAULT, null));
        return;
      }
      if (bag[field] === null) {
        tradingFaults.push(fault(where, field, NULL_FAULT, null));
        return;
      }
      if (kindOf(bag[field]) !== wanted) {
        tradingFaults.push(fault(where, field, WRONG_TYPE_FAULT, kindOf(bag[field])));
      }
    });
  }

  var SPLITTER_FIELDS = [
    ORIENTATION,
    HANDLE_WIDTH,
    CHILDREN_COLLAPSIBLE,
    CHILDREN,
    SIZES
  ];

  var LAYER_FIELDS = [KEY, LABEL, ACCENT, PAGE_LAYOUT, ADD_BUTTON, PLACEHOLDER];

  var BUTTON_FIELDS = [
    TEXT,
    CHECKABLE,
    CHECKED,
    TOOLTIP,
    BACKGROUND,
    COLOR,
    BORDER,
    BORDER_RADIUS,
    PADDING,
    FONT_SIZE,
    HOVER_BACKGROUND,
    STYLE_SHEET
  ];

  function checkSplitters(model) {
    var first = objectField(model, MAIN_SPLITTER);
    SPLITTER_SLOTS.forEach(function (slot) {
      var splitter = objectField(model, slot);
      checkAgainstPeer(SPLITTER_AT + slot, splitter, first, SPLITTER_FIELDS);
      var children = listField(splitter, CHILDREN);
      var sizes = listField(splitter, SIZES);
      if (sizes.length < children.length) {
        tradingFaults.push(
          fault(SPLITTER_AT + slot, SIZES, SHORT_LIST_FAULT, sizes.length)
        );
      }
    });
  }

  function checkLayers(model) {
    var layers = listField(model, LAYERS);
    var pages = listField(objectField(model, TRADING_STACK), PAGES);
    var first = isPlainObject(layers.slice().shift()) ? layers.slice().shift() : {};
    layers.forEach(function (layer, at) {
      if (!isPlainObject(layer)) {
        tradingFaults.push(
          fault(LAYER_AT + String(at), null, NOT_AN_OBJECT_FAULT, kindOf(layer))
        );
        return;
      }
      var where = LAYER_AT + String(layer[KEY]);
      checkAgainstPeer(where, layer, first, LAYER_FIELDS);
      var slotted = pages.filter(function (page) {
        return page === layer[KEY];
      });
      if (!slotted.length) {
        tradingFaults.push(fault(where, KEY, UNSLOTTED_FAULT, null));
      }
      checkSheets(where, layer);
    });
    if (pages.length !== layers.length) {
      tradingFaults.push(fault(TRADING_STACK, PAGES, DISAGREES_FAULT, layers.length));
    }
  }

  function checkSheet(where, field, sheet) {
    declarations(sheet).forEach(function (one) {
      if (qtColour(one.value) !== undefined) {
        tradingFaults.push(fault(where, field, QT_COLOUR_FAULT, one.property));
      }
    });
  }

  function checkSheets(where, layer) {
    var placeholder = objectField(layer, PLACEHOLDER);
    checkSheet(where, CARD, objectField(placeholder, CARD)[STYLE_SHEET]);
    checkSheet(where, TITLE, objectField(placeholder, TITLE)[STYLE_SHEET]);
    checkSheet(where, ADD_BUTTON, objectField(placeholder, ADD_BUTTON)[STYLE_SHEET]);
    checkSheet(where, HINT, objectField(placeholder, HINT)[STYLE_SHEET]);
  }

  // The style sheet and the loose fields paint one button, so each
  // holds the other.
  function checkButtonSheet(where, button) {
    var painted = {};
    declarations(button[STYLE_SHEET]).forEach(function (one) {
      painted[one.property] = one.value;
    });
    if (!Object.keys(painted).length) {
      return;
    }
    var pairs = [
      { field: BACKGROUND, property: BACKGROUND },
      { field: COLOR, property: COLOR },
      { field: BORDER, property: BORDER }
    ];
    pairs.forEach(function (one) {
      if (!owns(button, one.field) || !owns(painted, one.property)) {
        return;
      }
      if (String(button[one.field]) !== String(painted[one.property])) {
        tradingFaults.push(
          fault(where, one.field, DISAGREES_FAULT, painted[one.property])
        );
      }
    });
  }

  function checkPanes(model) {
    var activity = objectField(model, ACTIVITY_PANE);
    var api = objectField(model, API_PANE);
    var first = objectField(activity, PAUSE_BUTTON);
    var second = objectField(api, PAUSE_BUTTON);
    checkAgainstPeer(PANE_AT + API_PANE, second, first, BUTTON_FIELDS);
    checkButtonSheet(PANE_AT + ACTIVITY_PANE, first);
    checkButtonSheet(PANE_AT + API_PANE, second);
    var buffer = objectField(api, PAUSE_BUFFER);
    if (owns(buffer, PAUSED) && owns(second, CHECKED)) {
      if (buffer[PAUSED] !== second[CHECKED]) {
        tradingFaults.push(
          fault(PANE_AT + API_PANE, CHECKED, DISAGREES_FAULT, buffer[PAUSED])
        );
      }
    }
    checkLogView(objectField(api, LOG_VIEW));
  }

  // The view publishes its blocks three ways, so each holds the others.
  function checkLogView(view) {
    var blocks = listField(view, BLOCKS);
    if (owns(view, BLOCK_COUNT) && blocks.length !== view[BLOCK_COUNT]) {
      tradingFaults.push(
        fault(LOG_VIEW, BLOCK_COUNT, DISAGREES_FAULT, blocks.length)
      );
    }
    if (owns(view, TEXT) && blocks.join(NEWLINE) !== view[TEXT]) {
      tradingFaults.push(fault(LOG_VIEW, TEXT, DISAGREES_FAULT, blocks.length));
    }
  }

  function checkAlias(model) {
    var pages = listField(objectField(model, TRADING_STACK), PAGES);
    if (!owns(model, ALIAS_LAYER) || !pages.length) {
      return;
    }
    var named = pages.filter(function (page) {
      return page === model[ALIAS_LAYER];
    });
    if (!named.length) {
      tradingFaults.push(fault(null, ALIAS_LAYER, UNSLOTTED_FAULT, model[ALIAS_LAYER]));
    }
  }

  function heldFieldCount() {
    return DECLARED_FIELDS.filter(function (field) {
      return held !== null && owns(held.model, field);
    }).length;
  }

  function declaredPaneCount(model) {
    var counted = SPLITTER_SLOTS.map(function (slot) {
      return listField(objectField(model, slot), CHILDREN).length;
    });
    var total = Number(EMPTY);
    counted.forEach(function (one) {
      total = total + one;
    });
    return total;
  }

  function report() {
    var model = held.model;
    return {
      declared: {
        fields: DECLARED_FIELDS.length,
        layers: listField(objectField(model, TRADING_STACK), PAGES).length,
        panes: declaredPaneCount(model),
        blocks: objectField(objectField(model, API_PANE), LOG_VIEW)[BLOCK_COUNT]
      },
      held: {
        fields: heldFieldCount(),
        layers: listField(model, LAYERS).length,
        panes: declaredPaneCount(model),
        blocks: listField(objectField(objectField(model, API_PANE), LOG_VIEW), BLOCKS)
          .length
      },
      faults: tradingFaults.slice()
    };
  }

  function setTrading(model) {
    if (!isPlainObject(model)) {
      held = null;
      tradingFaults = [fault(null, null, NOT_AN_OBJECT_FAULT, kindOf(model))];
      return { declared: null, held: null, faults: tradingFaults.slice() };
    }
    held = { model: model };
    tradingFaults = [];
    checkFields(model);
    checkSplitters(model);
    checkLayers(model);
    checkPanes(model);
    checkAlias(model);
    return report();
  }

  // A failed load is not remembered, so a later ask reaches the bridge.
  function loadTrading(params) {
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
        setTrading(model);
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

  function splitterNames() {
    return SPLITTER_SLOTS.slice();
  }

  function splitter(name) {
    var named = SPLITTER_SLOTS.filter(function (slot) {
      return slot === name;
    });
    return named.length ? bag(name) : undefined;
  }

  function container() {
    return bag(CONTAINER);
  }

  function stack() {
    return bag(TRADING_STACK);
  }

  function layers() {
    return list(LAYERS);
  }

  function layer(name) {
    var found;
    layers().forEach(function (one) {
      if (isPlainObject(one) && one[KEY] === name) {
        found = one;
      }
    });
    return found;
  }

  function equityExchangeIds() {
    return list(EQUITY_EXCHANGE_IDS);
  }

  function activityPane() {
    return bag(ACTIVITY_PANE);
  }

  function apiPane() {
    return bag(API_PANE);
  }

  function logView() {
    return held === null ? {} : copyOf(objectField(apiPane(), LOG_VIEW));
  }

  function pauseBuffer() {
    return held === null ? {} : copyOf(objectField(apiPane(), PAUSE_BUFFER));
  }

  function watchdog() {
    return bag(WATCHDOG);
  }

  function actions() {
    return bag(ACTIONS);
  }

  function action(name) {
    var found = actions();
    return owns(found, name) ? found[name] : undefined;
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
    return tradingFaults.slice();
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
    var drawn = draw(target, element(Tab, { model: payload }));
    mountChildren(target);
    return drawn;
  }

  // `status_log.js` draws its own lines into the slot this tab keeps. The
  // panel host does the drawing, so a module that registers no panel is
  // named on the slot rather than leaving it blank.
  function renderActivityLog(target, model) {
    var host = global.acervatorPanelHost;
    var slot = target.querySelector(
      SELECT_OPEN + PART_ATTR + SELECT_IS + STATUS_LOG_PART + SELECT_CLOSE
    );
    if (!host || slot === null) {
      return null;
    }
    slot.setAttribute(CHILD_ATTR, STATUS_LOG_MODULE);
    return host.mount(STATUS_LOG_MODULE, slot, model) ? slot : null;
  }

  // `indicator_panel.js` draws its own votes into the slot this tab keeps,
  // through the panel host on the same terms as the Activity Log.
  function renderIndicatorPanel(target, model) {
    var host = global.acervatorPanelHost;
    var slot = target.querySelector(
      SELECT_OPEN + PART_ATTR + SELECT_IS + INDICATOR_PART + SELECT_CLOSE
    );
    if (!host || slot === null) {
      return null;
    }
    slot.setAttribute(CHILD_ATTR, INDICATOR_MODULE);
    return host.mount(INDICATOR_MODULE, slot, model) ? slot : null;
  }

  // The layers whose tab widget has an exchange page on show.
  function shownExchanges() {
    var model = held === null ? null : held.model;
    return listField(model, LAYERS)
      .filter(function (layer) {
        return isPlainObject(layer) && layer[PLACEHOLDER_SHOWN] === false;
      })
      .map(function (layer) {
        var tabs = objectField(layer, EXCHANGE_TABS);
        var one = text(layer[CURRENT_EXCHANGE]);
        return { exchangeId: one, caption: text(tabs[one]) };
      })
      .filter(function (one) {
        return one.exchangeId !== EMPTY;
      });
  }

  // `exchange_tab.js` draws one exchange's screen into the space the
  // layer keeps for the tab on show.
  function renderExchangePane(target, shown) {
    var api = global[EXCHANGE_API];
    var slot = target.querySelector(
      SELECT_OPEN +
        PART_ATTR +
        SELECT_IS +
        EXCHANGE_PANE_PART +
        SELECT_CLOSE +
        SELECT_OPEN +
        EXCHANGE_ATTR +
        SELECT_IS +
        shown.exchangeId +
        SELECT_CLOSE
    );
    if (!api || typeof api.renderTab !== "function" || slot === null) {
      return null;
    }
    slot.setAttribute(CHILD_ATTR, EXCHANGE_MODULE);
    return api.renderTab(slot, shown.model);
  }

  function askExchange(shown) {
    var loader = global[LOAD_EXCHANGE];
    if (typeof loader !== "function") {
      return Promise.resolve(null);
    }
    var params = {};
    params[EXCHANGE_ID_PARAM] = shown.exchangeId;
    params[EXCHANGE_NAME_PARAM] = shown.caption;
    return Promise.resolve(loader(params));
  }

  function mountExchanges(target) {
    var asked = shownExchanges().map(function (shown) {
      return askExchange(shown).then(function (model) {
        shown.model = model;
        return renderExchangePane(target, shown) === null ? null : EXCHANGE_MODULE;
      });
    });
    return Promise.all(asked);
  }

  // Qt builds the voting panel and the activity log inside this tab, so each
  // one is asked for its own view model and drawn into the slot kept for it.
  function mountChildren(target) {
    var children = [
      { module: STATUS_LOG_MODULE, loader: LOAD_LOG, draw: renderActivityLog },
      { module: INDICATOR_MODULE, loader: LOAD_INDICATOR, draw: renderIndicatorPanel }
    ];
    var asked = children.map(function (child) {
      var loader = global[child.loader];
      var wait =
        typeof loader === "function" ? loader({}) : Promise.resolve(null);
      return Promise.resolve(wait).then(function (model) {
        return child.draw(target, model) === null ? null : child.module;
      });
    });
    asked.push(
      mountExchanges(target).then(function (names) {
        var drawn = names.filter(function (one) {
          return one !== null;
        });
        return drawn.length ? drawn[ZERO] : null;
      })
    );
    return Promise.all(asked).then(function (drawn) {
      return drawn.filter(function (name) {
        return name !== null;
      });
    });
  }

  // Every host this module has drawn into, re-drawn from the held model.
  function redraw() {
    roots.forEach(function (pair) {
      renderTab(pair.node, held === null ? null : held.model);
    });
    return roots.length;
  }

  function forget() {
    held = null;
    tradingFaults = [];
    loadFault = null;
    asked = null;
  }

  // The shell draws this tab by its module name; the host reads that name
  // off the script tag running now, so it is written down nowhere.
  if (global.acervatorPanelHost) {
    global.acervatorPanelHost.register({
      method: METHOD,
      render: renderTab,
      load: loadTrading,
      loadError: loadError
    });
  }

  global.acervatorSetTrading = setTrading;
  global.acervatorLoadTrading = loadTrading;
  global.acervatorTrading = {
    method: METHOD,
    Tab: Tab,
    Splitter: Splitter,
    TradingStack: TradingStack,
    LayerPage: LayerPage,
    Placeholder: Placeholder,
    AddButton: AddButton,
    ActivityPane: ActivityPane,
    ApiPane: ApiPane,
    PauseButton: PauseButton,
    ApiLogView: ApiLogView,
    IndicatorPanel: IndicatorPanel,
    ExchangeTabButton: ExchangeTabButton,
    ExchangePane: ExchangePane,
    field: field,
    declaredNames: declaredNames,
    splitterNames: splitterNames,
    splitter: splitter,
    container: container,
    stack: stack,
    layers: layers,
    layer: layer,
    equityExchangeIds: equityExchangeIds,
    activityPane: activityPane,
    apiPane: apiPane,
    logView: logView,
    pauseBuffer: pauseBuffer,
    watchdog: watchdog,
    actions: actions,
    action: action,
    declarations: declarations,
    stateRules: stateRules,
    styleOf: styleOf,
    stateStyle: stateStyle,
    qtColour: qtColour,
    keptSheet: keptSheet,
    variableFor: variableFor,
    variableInGroups: variableInGroups,
    colour: colour,
    length: length,
    fontSize: fontSize,
    kinds: kinds,
    faults: faults,
    loadError: loadError,
    isLoaded: isLoaded,
    renderTab: renderTab,
    renderActivityLog: renderActivityLog,
    renderIndicatorPanel: renderIndicatorPanel,
    renderExchangePane: renderExchangePane,
    mountChildren: mountChildren,
    mountExchanges: mountExchanges,
    shownExchanges: shownExchanges,
    exchangeChosen: exchangeChosen,
    exchangeParam: EXCHANGE_PARAM,
    askTrading: askTrading,
    addExchangeAsked: addExchangeAsked,
    pauseToggled: pauseToggled,
    redraw: redraw,
    forget: forget
  };
})(window);
