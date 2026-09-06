// The Asset Charts tab, as the Python surface serves it to the global page.
(function (global) {
  "use strict";

  var METHOD = "trade_charts_tab.state";

  var ACCESSIBLE_NAME = "accessible_name";
  var CONTAINER = "container";
  var SCROLL = "scroll";
  var CONTENT = "content";
  var PANEL_ORDER = "panel_order";
  var PANEL_COUNT = "panel_count";
  var PANELS = "panels";
  var DROPPED = "dropped";
  var TRADE_LOG = "trade_log";
  var LOGS = "logs";
  var SIGNALS = "signals";
  var SIGNAL_NAMES = "signal_names";
  var THROTTLED_SIGNALS = "throttled_signals";
  var PANEL_DEFAULTS = "panel_defaults";
  var NUCLEAR_DEFAULTS = "nuclear_defaults";
  var FETCH = "fetch";
  var FILTERS = "filters";
  var OUTCOMES = "outcomes";
  var FORMATS = "formats";
  var FLOOR_FORMAT_SWITCH = "floor_format_switch";
  var EMPTY_SOURCE = "empty_source";
  var BOT_ID_LOG_LENGTH = "bot_id_log_length";
  var CANDLE_CLOSE_INDEX = "candle_close_index";
  var KEYS = "keys";
  var ATTRIBUTES = "attributes";
  var DEFAULTS = "defaults";
  var SIGNAL_SETTINGS = "signal_settings";
  var ACTIONS = "actions";
  var TIMERS = "timers";
  var TIMER_DELAYS = "timer_delays_ms";
  var BUS_TOPICS = "bus_topics";
  var CALL_NAMES = "call_names";
  var CALLS = "calls";

  var DECLARED_FIELDS = [
    ACCESSIBLE_NAME,
    ACTIONS,
    ATTRIBUTES,
    BOT_ID_LOG_LENGTH,
    BUS_TOPICS,
    CALLS,
    CALL_NAMES,
    CANDLE_CLOSE_INDEX,
    CONTAINER,
    CONTENT,
    DEFAULTS,
    DROPPED,
    EMPTY_SOURCE,
    FETCH,
    FILTERS,
    FLOOR_FORMAT_SWITCH,
    FORMATS,
    KEYS,
    LOGS,
    NUCLEAR_DEFAULTS,
    OUTCOMES,
    PANELS,
    PANEL_COUNT,
    PANEL_DEFAULTS,
    PANEL_ORDER,
    SCROLL,
    SIGNALS,
    SIGNAL_NAMES,
    SIGNAL_SETTINGS,
    THROTTLED_SIGNALS,
    TIMERS,
    TIMER_DELAYS,
    TRADE_LOG
  ];

  var MARGINS = "margins_px";
  var SPACING = "spacing_px";
  var WIDGET_RESIZABLE = "widget_resizable";
  var HORIZONTAL_POLICY = "horizontal_policy";
  var HORIZONTAL_POLICY_VALUE = "horizontal_policy_value";
  var STRETCH_ADDED = "stretch_added";
  var STRETCH_SLOTS = "stretch_slots";
  var LAYOUT_SLOTS = "layout_slots";

  var SYMBOL = "symbol";
  var EXCHANGE_ID = "exchange_id";
  var LAST_FETCH = "last_fetch";
  var SYNTHETIC = "synthetic";
  var PANEL = "panel";

  var BUILT_WITH = "built_with";
  var LABEL = "label";
  var TIMEFRAME = "timeframe";
  var CHART_TIMEFRAME = "chart_timeframe";
  var CANDLES = "candles";
  var CANDLE_COUNT = "candle_count";
  var ERROR_TEXT = "error_text";
  var SOURCE = "source";
  var MARKERS = "markers";
  var FLOORS = "floors";
  var TB_ANCHOR = "tb_anchor";
  var TB_CEILING = "tb_ceiling";
  var ARMED = "armed";
  var MINIMUM_HEIGHT = "minimum_height_px";
  var MAXIMUM_HEIGHT = "maximum_height_px";
  var CHART_REPAINTS = "chart_repaints";
  var PANEL_REPAINTS = "panel_repaints";
  var PARENT_CLEARED = "parent_cleared";
  var DELETED = "deleted";
  var TIMEFRAME_CONNECTED = "timeframe_connected";

  var COMBO_TIMEFRAME = "combo_timeframe";
  var TIMEFRAME_OPTIONS = "timeframe_options";

  var TIMEFRAME_ACTION = "panel.chart.timeframe_changed";
  var TIMEFRAME_CHANGE_PARAM = "timeframe_change";

  var MISSING_FAULT = "missing";
  var NULL_FAULT = "null";
  var NOT_AN_OBJECT_FAULT = "not-an-object";
  var WRONG_TYPE_FAULT = "wrong-type";
  var QT_COLOUR_FAULT = "qt-colour";
  var DISAGREES_FAULT = "disagrees";
  var UNMOUNTED_FAULT = "unmounted";
  var UNORDERED_FAULT = "unordered";
  var REPEATED_FAULT = "repeated";
  var UNLISTED_FAULT = "unlisted";
  var NOT_FINITE_FAULT = "not-finite";

  var NO_BRIDGE = "the preload bridge is not present";

  var PANEL_AT = "panel:";
  var PATH_SPLIT = ".";
  var EMPTY = "";
  var GAP = " ";
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
  // The factor that turns a unitless design token into a CSS length.
  var PX_FACTOR = " * 1px)";

  // Qt reads an eight-digit hex colour alpha first, CSS reads it last.
  var HEX_ARGB = "AARRGGBB";
  // Qt counts an rgba alpha in bytes, CSS counts it as a fraction.
  var RGBA_OPEN = "rgba(";

  // Only these token groups mean a length, so only they may name one.
  var LENGTH_GROUPS = ["spacing"];

  var FLEX = "flex";
  var COLUMN = "column";
  var ROW = "row";
  var AUTO = "auto";
  var HIDDEN = "hidden";
  var FLEX_NONE = "none";
  var NOWRAP = "nowrap";
  var ELLIPSIS = "ellipsis";
  var SELECT_NONE = "none";
  var FULL = "100%";
  var CENTER = "center";
  var DIV_TAG = "div";
  var SPAN_TAG = "span";
  var SELECT_TAG = "select";
  var OPTION_TAG = "option";

  // The one scrollbar policy the surface publishes, as CSS spells it.
  var OVERFLOW_BY_POLICY = { ScrollBarAlwaysOff: HIDDEN };

  var TAB_CLASS = "acervator-charts-tab";
  var PANEL_CLASS = "acervator-charts-panel";
  var CHART_CLASS = "acervator-charts-mount";

  var TAB_PART = "tab";
  var SCROLL_PART = "scroll";
  var CONTENT_PART = "content";
  var PANEL_PART = "chart-panel";
  var HEADER_PART = "panel-header";
  var TOOLBAR_PART = "panel-toolbar";
  var TIMEFRAME_PART = "timeframe";
  var SOURCE_PART = "panel-source";
  var CHART_PART = "chart-mount";
  var ERROR_PART = "panel-error";
  var STRETCH_PART = "stretch";
  var EMPTY_PART = "empty-column";

  // `native_chart.js` draws the candles into the host this tab keeps.
  var CHART_SLOT = "native_chart";

  var PART_ATTR = "data-part";
  var SLOT_ATTR = "data-slot";
  var BOT_ATTR = "data-bot";
  var INDEX_ATTR = "data-index";
  var SYMBOL_ATTR = "data-symbol";
  var EXCHANGE_ATTR = "data-exchange";
  var FETCHED_ATTR = "data-last-fetch";
  var SYNTHETIC_ATTR = "data-synthetic";
  var CANDLES_ATTR = "data-candle-count";
  var MARKERS_ATTR = "data-marker-count";
  var FLOORS_ATTR = "data-floor-count";
  var ANCHOR_ATTR = "data-tb-anchor";
  var CEILING_ATTR = "data-tb-ceiling";
  var ARMED_ATTR = "data-armed";
  var DELETED_ATTR = "data-deleted";
  var CONNECTED_ATTR = "data-timeframe-connected";
  var CHART_TF_ATTR = "data-chart-timeframe";
  var RESIZABLE_ATTR = "data-resizable";
  var POLICY_ATTR = "data-horizontal-policy";
  var SLOTS_ATTR = "data-layout-slots";
  var MOUNTED_ATTR = "data-mounted";
  var DECLARED_ATTR = "data-declared-panels";
  var STRETCH_ATTR = "data-stretch-added";
  var ACTION_ATTR = "data-action";
  var ARIA_LABEL = "aria-label";

  var CHANGE_EVENT = "change";

  var ZERO = Number(EMPTY);
  var ONE = Number(true);

  var held = null;
  var chartFaults = [];
  var loadFault = null;
  var asked = null;
  var roots = [];
  var lastTarget = null;

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

  // An empty label stays off rather than naming the element with nothing.
  function label(value) {
    return typeof value === "string" && value.length ? value : undefined;
  }

  // A number Infinity and NaN both fail, with no library call.
  function isFinite(value) {
    return typeof value === "number" && value - value === ZERO;
  }

  function afterFirst(value, splitter) {
    var parts = String(value).split(splitter);
    parts.shift();
    return parts;
  }

  function carries(value, splitter) {
    return Boolean(afterFirst(value, splitter).length);
  }

  // acervatorWidgets owns the one-carrier rule that names a variable.
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

  // A margin or a gap, which the spacing tokens are allowed to name.
  function spacing(value) {
    return scaled(value, LENGTH_GROUPS);
  }

  // A panel height, which no token group means, so it stays a plain length.
  function height(value) {
    if (value === null || value === undefined) {
      return undefined;
    }
    return String(value) + PX;
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
    if (typeof value !== "string") {
      return undefined;
    }
    if (hexWord(value).length === HEX_ARGB.length) {
      return HEX_ARGB;
    }
    if (byteAlpha(value)) {
      return RGBA_OPEN;
    }
    return undefined;
  }

  function element() {
    return global.React.createElement.apply(null, arguments);
  }

  // The surface publishes a margin in left, top, right, bottom order.
  var PADDING_SIDES = ["paddingLeft", "paddingTop", "paddingRight", "paddingBottom"];

  function marginStyle(layout) {
    var style = {};
    var margins = listField(layout, MARGINS);
    PADDING_SIDES.forEach(function (side, at) {
      if (at < margins.length) {
        style[side] = spacing(margins[at]);
      }
    });
    return style;
  }

  function boxStyle(layout, direction) {
    var style = marginStyle(layout);
    style.display = FLEX;
    style.flexDirection = direction;
    if (owns(layout, SPACING)) {
      style.gap = spacing(layout[SPACING]);
    }
    return style;
  }

  function panelsOf(model) {
    return objectField(model, PANELS);
  }

  // The bots the column really mounts, which is the order minus the unknown.
  function mountedOrder(model) {
    var panels = panelsOf(model);
    var seen = {};
    return listField(model, PANEL_ORDER).filter(function (botId) {
      var name = String(botId);
      if (!isPlainObject(panels[name]) || owns(seen, name)) {
        return false;
      }
      seen[name] = true;
      return true;
    });
  }

  function timeframeOptionList(model) {
    return listField(objectField(model, PANEL_DEFAULTS), TIMEFRAME_OPTIONS);
  }

  // A chosen timeframe re-arms this panel's fetch through the surface.
  function timeframeChosen(botId, chosen) {
    if (!global.acervator || typeof global.acervator.call !== "function") {
      loadFault = NO_BRIDGE;
      return Promise.resolve(null);
    }
    var params = {};
    params[TIMEFRAME_CHANGE_PARAM] = [botId, chosen];
    return global.acervator
      .call(METHOD, params)
      .then(function (model) {
        loadFault = null;
        setCharts(model);
        redraw();
        return model;
      })
      .catch(function (err) {
        loadFault = err.message;
        return null;
      });
  }

  function TimeframeControl(props) {
    var style = { flex: FLEX_NONE };
    var selectProps = {
      style: style,
      value: text(props.timeframe),
      onChange: function (event) {
        timeframeChosen(props.botId, event.target.value);
      }
    };
    selectProps[PART_ATTR] = TIMEFRAME_PART;
    selectProps[BOT_ATTR] = text(props.botId);
    selectProps[ACTION_ATTR] = text(props.action);
    selectProps[ARIA_LABEL] = label(props.botId);
    var drawn = props.options.map(function (one) {
      return element(OPTION_TAG, { key: String(one), value: text(one) }, text(one));
    });
    return element(SELECT_TAG, selectProps, drawn);
  }

  // Qt paints the header with the chart, so nothing here may be selected.
  function PanelHeader(props) {
    var style = {
      flex: FLEX_NONE,
      overflow: HIDDEN,
      whiteSpace: NOWRAP,
      textOverflow: ELLIPSIS,
      userSelect: SELECT_NONE
    };
    var headerProps = { style: style };
    headerProps[PART_ATTR] = HEADER_PART;
    headerProps[BOT_ATTR] = text(props.botId);
    return element(DIV_TAG, headerProps, text(props.panel[LABEL]));
  }

  function PanelSource(props) {
    var style = {
      flex: FLEX_NONE,
      overflow: HIDDEN,
      whiteSpace: NOWRAP,
      textOverflow: ELLIPSIS,
      userSelect: SELECT_NONE
    };
    var sourceProps = { style: style };
    sourceProps[PART_ATTR] = SOURCE_PART;
    sourceProps[BOT_ATTR] = text(props.botId);
    return element(SPAN_TAG, sourceProps, text(props.panel[SOURCE]));
  }

  // The host native_chart.js paints into, carrying the panel values the tab fed it.
  function ChartMount(props) {
    var panel = props.panel;
    var mountProps = { className: CHART_CLASS, style: { flex: AUTO, overflow: HIDDEN } };
    mountProps[PART_ATTR] = CHART_PART;
    mountProps[SLOT_ATTR] = CHART_SLOT;
    mountProps[BOT_ATTR] = text(props.botId);
    mountProps[SYMBOL_ATTR] = text(panel[BUILT_WITH]);
    mountProps[CHART_TF_ATTR] = text(panel[CHART_TIMEFRAME]);
    mountProps[CANDLES_ATTR] = text(panel[CANDLE_COUNT]);
    mountProps[MARKERS_ATTR] = text(listField(panel, MARKERS).length);
    mountProps[FLOORS_ATTR] = text(listField(panel, FLOORS).length);
    mountProps[ANCHOR_ATTR] = text(panel[TB_ANCHOR]);
    mountProps[CEILING_ATTR] = text(panel[TB_CEILING]);
    mountProps[ARMED_ATTR] = text(panel[ARMED] === null ? null : Boolean(panel[ARMED]));

    var errorText = panel[ERROR_TEXT];
    if (typeof errorText !== "string" || !errorText.length) {
      return element(DIV_TAG, mountProps, null);
    }
    var errorProps = { style: { userSelect: SELECT_NONE } };
    errorProps[PART_ATTR] = ERROR_PART;
    errorProps[BOT_ATTR] = text(props.botId);
    return element(DIV_TAG, mountProps, element(DIV_TAG, errorProps, errorText));
  }

  function Panel(props) {
    var info = props.info;
    var panel = objectField(info, PANEL);
    var style = { display: FLEX, flexDirection: COLUMN, flex: FLEX_NONE };
    style.minHeight = height(panel[MINIMUM_HEIGHT]);
    style.maxHeight = height(panel[MAXIMUM_HEIGHT]);
    var panelProps = { className: PANEL_CLASS, style: style };
    panelProps[PART_ATTR] = PANEL_PART;
    panelProps[BOT_ATTR] = text(props.botId);
    panelProps[INDEX_ATTR] = String(props.at);
    panelProps[SYMBOL_ATTR] = text(info[SYMBOL]);
    panelProps[EXCHANGE_ATTR] = text(info[EXCHANGE_ID]);
    panelProps[FETCHED_ATTR] = text(info[LAST_FETCH]);
    panelProps[SYNTHETIC_ATTR] = text(info[SYNTHETIC]);
    panelProps[DELETED_ATTR] = text(panel[DELETED]);
    panelProps[CONNECTED_ATTR] = text(panel[TIMEFRAME_CONNECTED]);

    var toolbarProps = {
      style: { display: FLEX, flexDirection: ROW, alignItems: CENTER, flex: FLEX_NONE }
    };
    toolbarProps[PART_ATTR] = TOOLBAR_PART;
    toolbarProps[BOT_ATTR] = text(props.botId);

    return element(
      DIV_TAG,
      panelProps,
      element(PanelHeader, { botId: props.botId, panel: panel }),
      element(
        DIV_TAG,
        toolbarProps,
        element(TimeframeControl, {
          botId: props.botId,
          timeframe: panel[TIMEFRAME],
          options: props.options,
          action: props.action
        }),
        element(PanelSource, { botId: props.botId, panel: panel })
      ),
      element(ChartMount, { botId: props.botId, panel: panel })
    );
  }

  // The column Qt scrolls: one panel per bot, then the trailing stretch.
  function Content(props) {
    var model = props.model;
    var content = objectField(model, CONTENT);
    var mounted = mountedOrder(model);
    var panels = panelsOf(model);
    var options = timeframeOptionList(model);
    var action = objectField(model, ACTIONS)[TIMEFRAME_ACTION];
    var contentProps = { style: boxStyle(content, COLUMN) };
    contentProps[PART_ATTR] = CONTENT_PART;
    contentProps[SLOTS_ATTR] = text(content[LAYOUT_SLOTS]);
    contentProps[MOUNTED_ATTR] = String(mounted.length);
    contentProps[DECLARED_ATTR] = text(model[PANEL_COUNT]);
    contentProps[STRETCH_ATTR] = text(content[STRETCH_ADDED]);

    var drawn = mounted.map(function (botId, at) {
      return element(Panel, {
        key: String(botId),
        botId: String(botId),
        at: at,
        info: objectField(panels, String(botId)),
        options: options,
        action: action
      });
    });
    if (content[STRETCH_ADDED] === true) {
      var stretchProps = { key: STRETCH_PART, style: { flex: AUTO } };
      stretchProps[PART_ATTR] = STRETCH_PART;
      drawn.push(element(DIV_TAG, stretchProps, null));
    }
    if (!mounted.length) {
      var emptyProps = { key: EMPTY_PART, style: { flex: FLEX_NONE } };
      emptyProps[PART_ATTR] = EMPTY_PART;
      drawn.push(element(DIV_TAG, emptyProps, null));
    }
    return element(DIV_TAG, contentProps, drawn);
  }

  // `Tab` draws nothing for a payload that is not an object.
  function Tab(props) {
    if (!isPlainObject(props.model)) {
      return null;
    }
    var model = props.model;
    var scroll = objectField(model, SCROLL);
    var tabProps = {
      id: props.id,
      className: TAB_CLASS,
      style: boxStyle(objectField(model, CONTAINER), COLUMN)
    };
    tabProps.style.overflow = HIDDEN;
    tabProps.style.height = FULL;
    tabProps[PART_ATTR] = TAB_PART;
    tabProps[ARIA_LABEL] = label(model[ACCESSIBLE_NAME]);

    var scrollStyle = { flex: AUTO };
    var policy = scroll[HORIZONTAL_POLICY];
    scrollStyle.overflowX = owns(OVERFLOW_BY_POLICY, policy)
      ? OVERFLOW_BY_POLICY[policy]
      : AUTO;
    scrollStyle.overflowY = AUTO;
    if (scroll[WIDGET_RESIZABLE] === true) {
      scrollStyle.display = FLEX;
      scrollStyle.flexDirection = COLUMN;
    }
    var scrollProps = { style: scrollStyle, tabIndex: ZERO };
    scrollProps[PART_ATTR] = SCROLL_PART;
    scrollProps[RESIZABLE_ATTR] = text(scroll[WIDGET_RESIZABLE]);
    scrollProps[POLICY_ATTR] = text(scroll[HORIZONTAL_POLICY]);

    return element(
      DIV_TAG,
      tabProps,
      element(DIV_TAG, scrollProps, element(Content, { model: model }))
    );
  }

  function checkFields(model) {
    DECLARED_FIELDS.forEach(function (field) {
      if (!owns(model, field)) {
        chartFaults.push(fault(null, field, MISSING_FAULT, null));
        return;
      }
      if (model[field] === null) {
        chartFaults.push(fault(null, field, NULL_FAULT, null));
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
        chartFaults.push(fault(where, field, MISSING_FAULT, null));
        return;
      }
      if (bag[field] === null) {
        chartFaults.push(fault(where, field, NULL_FAULT, null));
        return;
      }
      if (kindOf(bag[field]) !== wanted) {
        chartFaults.push(fault(where, field, WRONG_TYPE_FAULT, kindOf(bag[field])));
      }
    });
  }

  var INFO_FIELDS = [SYMBOL, EXCHANGE_ID, LAST_FETCH, PANEL];

  var PANEL_FIELDS = [
    BUILT_WITH,
    LABEL,
    TIMEFRAME,
    CHART_TIMEFRAME,
    CANDLES,
    CANDLE_COUNT,
    ERROR_TEXT,
    SOURCE,
    MARKERS,
    FLOORS,
    MINIMUM_HEIGHT,
    CHART_REPAINTS,
    PANEL_REPAINTS,
    PARENT_CLEARED,
    DELETED,
    TIMEFRAME_CONNECTED,
    CALLS
  ];

  var DEFAULT_FIELDS = [
    { field: TIMEFRAME, held: COMBO_TIMEFRAME },
    { field: CHART_TIMEFRAME, held: TIMEFRAME },
    { field: MINIMUM_HEIGHT, held: MINIMUM_HEIGHT }
  ];

  // A panel's type is held against the panel defaults, then against its peers.
  function checkPanelTypes(where, panel, peer, defaults) {
    checkAgainstPeer(where, panel, peer, PANEL_FIELDS);
    DEFAULT_FIELDS.forEach(function (pair) {
      if (!owns(defaults, pair.held) || defaults[pair.held] === null) {
        return;
      }
      if (!owns(panel, pair.field) || panel[pair.field] === null) {
        return;
      }
      if (kindOf(panel[pair.field]) !== kindOf(defaults[pair.held])) {
        chartFaults.push(
          fault(where, pair.field, WRONG_TYPE_FAULT, kindOf(panel[pair.field]))
        );
      }
    });
  }

  function checkPanelCounts(where, panel) {
    var candles = listField(panel, CANDLES);
    if (owns(panel, CANDLE_COUNT) && candles.length !== panel[CANDLE_COUNT]) {
      chartFaults.push(fault(where, CANDLE_COUNT, DISAGREES_FAULT, candles.length));
    }
  }

  function checkTimeframe(where, panel, options) {
    if (!owns(panel, TIMEFRAME) || !options.length) {
      return;
    }
    var named = options.filter(function (one) {
      return String(one) === String(panel[TIMEFRAME]);
    });
    if (!named.length) {
      chartFaults.push(fault(where, TIMEFRAME, UNLISTED_FAULT, panel[TIMEFRAME]));
    }
  }

  // The first value every panel publishes for a field, taken across them all.
  function peerOf(bags, fields) {
    var peer = {};
    fields.forEach(function (field) {
      bags.forEach(function (bag) {
        if (owns(peer, field) || !owns(bag, field) || bag[field] === null) {
          return;
        }
        peer[field] = bag[field];
      });
    });
    return peer;
  }

  function checkPanels(model) {
    var panels = panelsOf(model);
    var order = listField(model, PANEL_ORDER);
    var options = timeframeOptionList(model);
    var defaults = objectField(model, PANEL_DEFAULTS);
    var names = Object.keys(panels);
    var bags = names.map(function (name) {
      return objectField(panels, name);
    });
    var first = peerOf(bags, INFO_FIELDS);
    var firstPanel = peerOf(
      bags.map(function (bag) {
        return objectField(bag, PANEL);
      }),
      PANEL_FIELDS
    );
    var seen = {};

    order.forEach(function (botId) {
      var name = String(botId);
      if (owns(seen, name)) {
        chartFaults.push(fault(PANEL_AT + name, PANEL_ORDER, REPEATED_FAULT, name));
        return;
      }
      seen[name] = true;
      if (!isPlainObject(panels[name])) {
        chartFaults.push(fault(PANEL_AT + name, PANEL_ORDER, UNMOUNTED_FAULT, null));
      }
    });
    names.forEach(function (name) {
      var where = PANEL_AT + name;
      if (!owns(seen, name)) {
        chartFaults.push(fault(where, PANELS, UNORDERED_FAULT, null));
      }
      var info = objectField(panels, name);
      checkAgainstPeer(where, info, first, INFO_FIELDS);
      var panel = objectField(info, PANEL);
      checkPanelTypes(where, panel, firstPanel, defaults);
      checkPanelCounts(where, panel);
      checkTimeframe(where, panel, options);
    });
    if (owns(model, PANEL_COUNT) && names.length !== model[PANEL_COUNT]) {
      chartFaults.push(fault(null, PANEL_COUNT, DISAGREES_FAULT, names.length));
    }
  }

  var LAYOUT_FIELDS = [MARGINS, SPACING];
  var DEFAULTS_FIELDS = [TIMEFRAME, MINIMUM_HEIGHT];

  // The two layout bags and the two default bags each hold the other's shape.
  function checkBags(model) {
    checkAgainstPeer(
      CONTENT,
      objectField(model, CONTENT),
      objectField(model, CONTAINER),
      LAYOUT_FIELDS
    );
    checkAgainstPeer(
      PANEL_DEFAULTS,
      objectField(model, PANEL_DEFAULTS),
      objectField(model, NUCLEAR_DEFAULTS),
      DEFAULTS_FIELDS
    );
  }

  function checkSlots(model) {
    var content = objectField(model, CONTENT);
    if (!owns(content, LAYOUT_SLOTS) || !owns(content, STRETCH_SLOTS)) {
      return;
    }
    var mounted = mountedOrder(model).length;
    if (content[LAYOUT_SLOTS] !== mounted + content[STRETCH_SLOTS]) {
      chartFaults.push(fault(CONTENT, LAYOUT_SLOTS, DISAGREES_FAULT, mounted));
    }
  }

  // Every value, by dotted path, so one walk serves the type and colour rules.
  function walkValues(node, prefix, step) {
    Object.keys(node).forEach(function (name) {
      var path = prefix ? prefix + PATH_SPLIT + name : name;
      var value = node[name];
      step(path, value);
      if (isPlainObject(value)) {
        walkValues(value, path, step);
        return;
      }
      if (Array.isArray(value)) {
        value.forEach(function (one, at) {
          var inner = path + PATH_SPLIT + String(at);
          step(inner, one);
          if (isPlainObject(one) || Array.isArray(one)) {
            walkValues(one, inner, step);
          }
        });
      }
    });
  }

  // A colour CSS reads differently, and a number `JSON.parse` refuses.
  function checkValues(model) {
    walkValues(model, EMPTY, function (path, value) {
      if (qtColour(value) !== undefined) {
        chartFaults.push(fault(path, null, QT_COLOUR_FAULT, qtColour(value)));
      }
      if (typeof value === "number" && !isFinite(value)) {
        chartFaults.push(fault(path, null, NOT_FINITE_FAULT, String(value)));
      }
    });
  }

  function report() {
    var model = held.model;
    var panels = panelsOf(model);
    return {
      declared: {
        fields: DECLARED_FIELDS.length,
        panels: model[PANEL_COUNT],
        slots: objectField(model, CONTENT)[LAYOUT_SLOTS],
        candles: declaredCandles(panels)
      },
      held: {
        fields: heldFieldCount(),
        panels: Object.keys(panels).length,
        slots: mountedOrder(model).length + objectField(model, CONTENT)[STRETCH_SLOTS],
        candles: heldCandles(panels)
      },
      faults: chartFaults.slice()
    };
  }

  function declaredCandles(panels) {
    var total = ZERO;
    Object.keys(panels).forEach(function (name) {
      var panel = objectField(objectField(panels, name), PANEL);
      total = total + (typeof panel[CANDLE_COUNT] === "number" ? panel[CANDLE_COUNT] : ZERO);
    });
    return total;
  }

  function heldCandles(panels) {
    var total = ZERO;
    Object.keys(panels).forEach(function (name) {
      var panel = objectField(objectField(panels, name), PANEL);
      total = total + listField(panel, CANDLES).length;
    });
    return total;
  }

  function heldFieldCount() {
    return DECLARED_FIELDS.filter(function (field) {
      return held !== null && owns(held.model, field);
    }).length;
  }

  function setCharts(model) {
    if (!isPlainObject(model)) {
      held = null;
      chartFaults = [fault(null, null, NOT_AN_OBJECT_FAULT, kindOf(model))];
      return { declared: null, held: null, faults: chartFaults.slice() };
    }
    held = { model: model };
    chartFaults = [];
    checkFields(model);
    checkBags(model);
    checkPanels(model);
    checkSlots(model);
    checkValues(model);
    return report();
  }

  // A failed load is not remembered, so a later ask reaches the bridge.
  function loadCharts(params) {
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
        setCharts(model);
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

  // The Qt policy names this module recognises, which are names and not values.
  function policyNames() {
    return Object.keys(OVERFLOW_BY_POLICY);
  }

  function panelIds() {
    return held === null ? [] : Object.keys(panelsOf(held.model));
  }

  function panelOrder() {
    return list(PANEL_ORDER);
  }

  function mountedIds() {
    return held === null ? [] : mountedOrder(held.model);
  }

  function panel(name) {
    if (held === null) {
      return undefined;
    }
    var panels = panelsOf(held.model);
    return owns(panels, name) ? copyOf(objectField(panels, name)) : undefined;
  }

  function container() {
    return bag(CONTAINER);
  }

  function scroll() {
    return bag(SCROLL);
  }

  function content() {
    return bag(CONTENT);
  }

  function panelDefaults() {
    return bag(PANEL_DEFAULTS);
  }

  function nuclearDefaults() {
    return bag(NUCLEAR_DEFAULTS);
  }

  function timeframeOptions() {
    return held === null ? [] : timeframeOptionList(held.model).slice();
  }

  function fetchSettings() {
    return bag(FETCH);
  }

  function filters() {
    return bag(FILTERS);
  }

  function formats() {
    return bag(FORMATS);
  }

  function keys() {
    return bag(KEYS);
  }

  function attributes() {
    return bag(ATTRIBUTES);
  }

  function defaults() {
    return bag(DEFAULTS);
  }

  function signalSettings() {
    return bag(SIGNAL_SETTINGS);
  }

  function signals() {
    return list(SIGNALS);
  }

  function signalNames() {
    return list(SIGNAL_NAMES);
  }

  function throttledSignals() {
    return list(THROTTLED_SIGNALS);
  }

  function outcomes() {
    return list(OUTCOMES);
  }

  function dropped() {
    return list(DROPPED);
  }

  function tradeLog() {
    return list(TRADE_LOG);
  }

  function logs() {
    return list(LOGS);
  }

  function callNames() {
    return list(CALL_NAMES);
  }

  function calls() {
    return list(CALLS);
  }

  function actions() {
    return bag(ACTIONS);
  }

  function action(name) {
    var found = actions();
    return owns(found, name) ? found[name] : undefined;
  }

  function timers() {
    return bag(TIMERS);
  }

  function timerDelays() {
    return list(TIMER_DELAYS);
  }

  function busTopics() {
    return list(BUS_TOPICS);
  }

  // Every payload value's JavaScript type, by dotted path, null apart.
  function kinds() {
    var found = {};
    if (held !== null) {
      walkValues(held.model, EMPTY, function (path, value) {
        found[path] = kindOf(value);
      });
    }
    return found;
  }

  function faults() {
    return chartFaults.slice();
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
    lastTarget = target;
    return draw(target, element(Tab, { model: payload }));
  }

  // The last target is drawn again after the surface answers a timeframe change.
  function redraw() {
    if (lastTarget === null) {
      return null;
    }
    return renderTab(lastTarget);
  }

  function forget() {
    held = null;
    chartFaults = [];
    loadFault = null;
    asked = null;
    lastTarget = null;
  }

  // The shell draws this tab by its module name; the host reads that name
  // off the script tag running now, so it is written down nowhere.
  if (global.acervatorPanelHost) {
    global.acervatorPanelHost.register({
      render: renderTab,
      load: loadCharts,
      loadError: loadError
    });
  }

  global.acervatorSetCharts = setCharts;
  global.acervatorLoadCharts = loadCharts;
  global.acervatorCharts = {
    method: METHOD,
    Tab: Tab,
    Content: Content,
    Panel: Panel,
    PanelHeader: PanelHeader,
    PanelSource: PanelSource,
    TimeframeControl: TimeframeControl,
    ChartMount: ChartMount,
    field: field,
    declaredNames: declaredNames,
    policyNames: policyNames,
    container: container,
    scroll: scroll,
    content: content,
    panelIds: panelIds,
    panelOrder: panelOrder,
    mountedIds: mountedIds,
    panel: panel,
    panelDefaults: panelDefaults,
    nuclearDefaults: nuclearDefaults,
    timeframeOptions: timeframeOptions,
    fetchSettings: fetchSettings,
    filters: filters,
    formats: formats,
    keys: keys,
    attributes: attributes,
    defaults: defaults,
    signalSettings: signalSettings,
    signals: signals,
    signalNames: signalNames,
    throttledSignals: throttledSignals,
    outcomes: outcomes,
    dropped: dropped,
    tradeLog: tradeLog,
    logs: logs,
    callNames: callNames,
    calls: calls,
    actions: actions,
    action: action,
    timers: timers,
    timerDelays: timerDelays,
    busTopics: busTopics,
    qtColour: qtColour,
    variableFor: variableFor,
    variableInGroups: variableInGroups,
    spacing: spacing,
    height: height,
    kinds: kinds,
    faults: faults,
    loadError: loadError,
    isLoaded: isLoaded,
    renderTab: renderTab,
    forget: forget
  };
})(window);
