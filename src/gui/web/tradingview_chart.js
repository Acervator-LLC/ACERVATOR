// The TradingView chart page, drawn from the payload the Python surface serves.
(function (global) {
  "use strict";

  var METHOD = "tradingview.chart";

  var ACCESSIBLE_NAME = "accessible_name";
  var ACTIONS = "actions";
  var ACTIVE = "active";
  var ACTIVE_TIMEFRAME = "active_timeframe";
  var BOLLINGER_SERIES = "bollinger_series";
  var BRIDGE_CALLBACK = "bridge_callback";
  var BRIDGE_OBJECT = "bridge_object";
  var BUS_TOPICS = "bus_topics";
  var BUTTONS = "buttons";
  var BUTTON_SKIN = "button_skin";
  var BUY_SIDE = "buy_side";
  var CALLS = "calls";
  var CALL_FORMATS = "call_formats";
  var CALL_ORDER = "call_order";
  var CANDLE_FIELDS = "candle_fields";
  var CANDLE_SERIES = "candle_series";
  var COLORS = "colors";
  var DEFAULT_SYMBOL = "default_symbol";
  var DEFAULT_THEME = "default_theme";
  var FALLBACK_THEME = "fallback_theme";
  var GRID_LEVEL_FIELDS = "grid_level_fields";
  var GRID_LINE_SKIN = "grid_line_skin";
  var HTML = "html";
  var LOGGER_NAME = "logger_name";
  var MARKER_FIELDS = "marker_fields";
  var MARKER_SKIN = "marker_skin";
  var MISSING_WEBENGINE_WARNING = "missing_webengine_warning";
  var PAGE = "page";
  var SCRIPT_URL = "script_url";
  var SELL_SIDE = "sell_side";
  var SKIN = "skin";
  var SYMBOL = "symbol";
  var SYMBOL_KEY = "symbol_key";
  var THEME = "theme";
  var THEMES = "themes";
  var THEME_KEYS = "theme_keys";
  var THEME_ORDER = "theme_order";
  var TIMERS = "timers";
  var TIMER_DELAYS = "timer_delays_ms";
  var TIME_SCALE = "time_scale";
  var TOOLBAR = "toolbar";
  var VOLUME_FIELD = "volume_field";
  var VOLUME_SERIES = "volume_series";
  var WATERMARK = "watermark";
  var WEB_VIEW = "web_view";

  var DECLARED_FIELDS = [
    ACCESSIBLE_NAME,
    ACTIONS,
    ACTIVE_TIMEFRAME,
    BOLLINGER_SERIES,
    BRIDGE_CALLBACK,
    BRIDGE_OBJECT,
    BUS_TOPICS,
    BUTTONS,
    BUTTON_SKIN,
    BUY_SIDE,
    CALLS,
    CALL_FORMATS,
    CALL_ORDER,
    CANDLE_FIELDS,
    CANDLE_SERIES,
    COLORS,
    DEFAULT_SYMBOL,
    DEFAULT_THEME,
    FALLBACK_THEME,
    GRID_LEVEL_FIELDS,
    GRID_LINE_SKIN,
    HTML,
    LOGGER_NAME,
    MARKER_FIELDS,
    MARKER_SKIN,
    MISSING_WEBENGINE_WARNING,
    PAGE,
    SCRIPT_URL,
    SELL_SIDE,
    SKIN,
    SYMBOL,
    SYMBOL_KEY,
    THEME,
    THEMES,
    THEME_KEYS,
    THEME_ORDER,
    TIMERS,
    TIMER_DELAYS,
    TIME_SCALE,
    TOOLBAR,
    VOLUME_FIELD,
    VOLUME_SERIES,
    WATERMARK,
    WEB_VIEW
  ];

  var LABEL = "label";
  var VALUE = "value";
  var ENABLED = "enabled";
  var CLASS_NAME = "class_name";
  var ACTIVE_CLASS_NAME = "active_class_name";
  var PADDING = "padding_px";
  var RADIUS = "radius_px";
  var FONT_SIZE = "font_size_px";
  var BORDER_WIDTH = "border_width_px";
  var CURSOR = "cursor";
  var HANDLER = "handler";

  var POSITION = "position";
  var TOP = "top_px";
  var RIGHT = "right_px";
  var Z_INDEX = "z_index";
  var DISPLAY = "display";
  var GAP = "gap_px";

  var VISIBLE = "visible";
  var FIELDS = "fields";

  var BG = "bg";
  var TEXT = "text";
  var BORDER = "border";
  var ACCENT = "accent";
  var BTN_BG = "btn_bg";

  var MISSING_FAULT = "missing";
  var NULL_FAULT = "null";
  var NOT_AN_OBJECT_FAULT = "not-an-object";
  var WRONG_TYPE_FAULT = "wrong-type";
  var QT_COLOUR_FAULT = "qt-colour";
  var DISAGREES_FAULT = "disagrees";
  var UNORDERED_FAULT = "unordered";
  var REPEATED_FAULT = "repeated";
  var UNLISTED_FAULT = "unlisted";
  var NOT_FINITE_FAULT = "not-finite";

  var NO_BRIDGE = "the preload bridge is not present";

  var THEME_AT = "theme:";
  var BUTTON_AT = "button:";
  var PATH_SPLIT = ".";
  var EMPTY = "";
  var SPACE = " ";
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

  // Only a spacing token means a margin, a gap or a padding.
  var SPACING_GROUPS = ["spacing"];
  // Only a radius token means a corner.
  var RADIUS_GROUPS = ["radii"];
  // Only a type token means a font size.
  var TYPE_GROUPS = ["type_scale"];
  // No token groups name a chart palette slot, so the theme table names it.
  var COLOUR_GROUPS = [];
  // No token group names a border width, so the surface number stands.
  var BORDER_GROUPS = [];

  var RELATIVE = "relative";
  var HIDDEN = "hidden";
  var SOLID = "solid";
  var BORDER_BOX = "border-box";
  var FULL = "100%";
  var NONE = "none";
  var CENTER = "center";
  var DIV_TAG = "div";
  var SPAN_TAG = "span";
  var BUTTON_TAG = "button";

  var CHART_CLASS = "acervator-tvchart";
  var TOOLBAR_CLASS = "acervator-tvchart-toolbar";
  var MOUNT_CLASS = "acervator-tvchart-mount";

  var CHART_PART = "chart";
  var TOOLBAR_PART = "toolbar-row";
  var BUTTON_PART = "timeframe-button";
  var MOUNT_PART = "chart-mount";
  var WATERMARK_PART = "watermark-text";

  // The series a charting library draws, which nothing in this page draws.
  var MOUNT_SLOT = "tradingview-series";

  var PART_ATTR = "data-part";
  var SLOT_ATTR = "data-slot";
  var VALUE_ATTR = "data-value";
  var ACTIVE_ATTR = "data-active";
  var ENABLED_ATTR = "data-enabled";
  var HANDLER_ATTR = "data-handler";
  var THEME_ATTR = "data-theme-name";
  var SYMBOL_ATTR = "data-symbol";
  var SERIES_ATTR = "data-series-count";
  var SLOPE_ATTR = "data-slope-count";
  var FED_ATTR = "data-fed-calls";
  var ARIA_LABEL = "aria-label";

  // The four edges CSS paints from one border declaration.
  var BORDER_EDGES = ["borderTop", "borderRight", "borderBottom", "borderLeft"];
  // The four corners CSS rounds from one radius declaration.
  var RADIUS_CORNERS = [
    "borderTopLeftRadius",
    "borderTopRightRadius",
    "borderBottomRightRadius",
    "borderBottomLeftRadius"
  ];

  var ZERO = Number(EMPTY);
  var ONE = Number(true);

  var held = null;
  var chartFaults = [];
  var loadFault = null;
  var asked = null;
  var roots = [];
  var lastTarget = null;
  var lastCall = null;

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

  function fault(where, name, kind, detail) {
    return { where: where, field: name, fault: kind, detail: detail };
  }

  // A missing value leaves the attribute off the element.
  function text(value) {
    return value === null || value === undefined ? undefined : String(value);
  }

  // An empty label stays off rather than naming the element with nothing.
  function label(value) {
    return typeof value === "string" && value.length ? value : undefined;
  }

  // Infinity and NaN both fail isFinite, with no library call.
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

  // The shared widgets module owns the one-carrier rule naming a variable.
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

  function spacing(value) {
    return scaled(value, SPACING_GROUPS);
  }

  function radius(value) {
    return scaled(value, RADIUS_GROUPS);
  }

  function typeSize(value) {
    return scaled(value, TYPE_GROUPS);
  }

  function borderWidth(value) {
    return scaled(value, BORDER_GROUPS);
  }

  // A chart colour, painted through a token only from a group meaning a slot.
  function paint(value) {
    if (value === null || value === undefined) {
      return undefined;
    }
    var name = variableInGroups(value, COLOUR_GROUPS);
    if (name === undefined) {
      return String(value);
    }
    return VAR_OPEN + name + VAR_SPLIT + String(value) + VAR_CLOSE;
  }

  // The first hex word of one value, empty when the value carries none.
  function hexWord(value) {
    var parts = afterFirst(value, HASH);
    if (!parts.length) {
      return EMPTY;
    }
    return String(parts.shift()).trim().split(SPACE).shift();
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

  // The surface spells the flex word once, on the toolbar it lays out.
  function flexWord(model) {
    return text(objectField(model, TOOLBAR)[DISPLAY]);
  }

  function colourBag(model) {
    return objectField(model, COLORS);
  }

  function symbolKey(model) {
    var name = isPlainObject(model) ? model[SYMBOL_KEY] : undefined;
    return typeof name === "string" ? name : SYMBOL;
  }

  // The nine page holes in the order the surface fills them, symbol last.
  function colourKeyList(model) {
    return listField(model, THEME_KEYS).concat([symbolKey(model)]);
  }

  // The buttons the toolbar really draws, which is the list minus a repeat.
  function drawnButtons(model) {
    var seen = {};
    return listField(model, BUTTONS).filter(function (one) {
      if (!isPlainObject(one)) {
        return false;
      }
      var name = String(one[VALUE]);
      if (owns(seen, name)) {
        return false;
      }
      seen[name] = true;
      return true;
    });
  }

  // A chosen timeframe asks the surface again and redraws what it answers.
  function timeframeChosen(value) {
    lastCall = null;
    if (!global.acervator || typeof global.acervator.call !== "function") {
      loadFault = NO_BRIDGE;
      return Promise.resolve(null);
    }
    var params = {};
    params[ACTIVE] = value;
    params[SYMBOL] = field(SYMBOL);
    params[THEME] = field(THEME);
    lastCall = { method: METHOD, params: params };
    return global.acervator
      .call(METHOD, params)
      .then(function (model) {
        loadFault = null;
        setChart(model);
        redraw();
        return model;
      })
      .catch(function (err) {
        loadFault = err.message;
        return null;
      });
  }

  function TimeframeButton(props) {
    var skin = props.skin;
    var colours = props.colours;
    var one = props.button;
    var live = one[ACTIVE] === true;
    var padding = Array.isArray(skin[PADDING]) ? skin[PADDING] : [];
    var style = {
      boxSizing: BORDER_BOX,
      cursor: text(skin[CURSOR]),
      borderStyle: SOLID,
      borderWidth: borderWidth(skin[BORDER_WIDTH]),
      borderColor: paint(live ? colours[ACCENT] : colours[BORDER]),
      borderRadius: radius(skin[RADIUS]),
      fontSize: typeSize(skin[FONT_SIZE]),
      background: paint(live ? colours[ACCENT] : colours[BTN_BG]),
      color: paint(live ? colours[BG] : colours[TEXT])
    };
    if (padding.length) {
      style.paddingTop = spacing(padding[ZERO]);
      style.paddingBottom = spacing(padding[ZERO]);
    }
    if (padding.length > ONE) {
      style.paddingLeft = spacing(padding[ONE]);
      style.paddingRight = spacing(padding[ONE]);
    }
    var buttonProps = {
      type: BUTTON_TAG,
      className: live ? skin[ACTIVE_CLASS_NAME] : skin[CLASS_NAME],
      style: style,
      disabled: one[ENABLED] === false,
      onClick: function () {
        timeframeChosen(one[VALUE]);
      }
    };
    buttonProps[PART_ATTR] = BUTTON_PART;
    buttonProps[VALUE_ATTR] = text(one[VALUE]);
    buttonProps[ACTIVE_ATTR] = String(live);
    buttonProps[ENABLED_ATTR] = text(one[ENABLED]);
    buttonProps[HANDLER_ATTR] = text(skin[HANDLER]);
    buttonProps[ARIA_LABEL] = label(one[LABEL]);
    return element(BUTTON_TAG, buttonProps, text(one[LABEL]));
  }

  // Qt lays the toolbar over the page, so this one lies over the chart.
  function Toolbar(props) {
    var bar = props.bar;
    var style = {
      boxSizing: BORDER_BOX,
      position: text(bar[POSITION]),
      top: spacing(bar[TOP]),
      right: spacing(bar[RIGHT]),
      zIndex: bar[Z_INDEX],
      display: text(bar[DISPLAY]),
      gap: spacing(bar[GAP])
    };
    var barProps = { className: TOOLBAR_CLASS, style: style };
    barProps[PART_ATTR] = TOOLBAR_PART;
    var drawn = props.buttons.map(function (one) {
      return element(TimeframeButton, {
        key: String(one[VALUE]),
        button: one,
        skin: props.skin,
        colours: props.colours
      });
    });
    return element(DIV_TAG, barProps, drawn);
  }

  // The watermark the chart draws behind its candles, off when not visible.
  function Watermark(props) {
    var mark = props.mark;
    if (mark[VISIBLE] !== true) {
      return null;
    }
    var style = {
      boxSizing: BORDER_BOX,
      fontSize: typeSize(mark[FONT_SIZE]),
      color: paint(props.colours[WATERMARK]),
      pointerEvents: NONE,
      userSelect: NONE
    };
    var markProps = { style: style };
    markProps[PART_ATTR] = WATERMARK_PART;
    markProps[SYMBOL_ATTR] = text(props.symbol);
    return element(SPAN_TAG, markProps, text(props.symbol));
  }

  // The mount where a charting library would draw the candle and volume series.
  function ChartMount(props) {
    var model = props.model;
    var holds = mountHolds(model);
    var style = {
      boxSizing: BORDER_BOX,
      display: flexWord(model),
      alignItems: CENTER,
      justifyContent: CENTER,
      flex: ONE,
      overflow: HIDDEN
    };
    var mountProps = { className: MOUNT_CLASS, style: style };
    mountProps[PART_ATTR] = MOUNT_PART;
    mountProps[SLOT_ATTR] = MOUNT_SLOT;
    mountProps[SERIES_ATTR] = String(holds.series.length);
    mountProps[SLOPE_ATTR] = String(holds.slopes);
    mountProps[FED_ATTR] = String(holds.fed);
    return element(
      DIV_TAG,
      mountProps,
      element(Watermark, {
        mark: objectField(model, WATERMARK),
        colours: colourBag(model),
        symbol: colourBag(model)[symbolKey(model)]
      })
    );
  }

  // `Chart` draws nothing for a payload that is not an object.
  function Chart(props) {
    if (!isPlainObject(props.model)) {
      return null;
    }
    var model = props.model;
    var colours = colourBag(model);
    var style = {
      boxSizing: BORDER_BOX,
      position: RELATIVE,
      display: flexWord(model),
      overflow: HIDDEN,
      height: FULL,
      width: FULL,
      background: paint(colours[BG]),
      color: paint(colours[TEXT])
    };
    var chartProps = { id: props.id, className: CHART_CLASS, style: style };
    chartProps[PART_ATTR] = CHART_PART;
    chartProps[THEME_ATTR] = text(model[THEME]);
    chartProps[ARIA_LABEL] = label(model[ACCESSIBLE_NAME]);
    return element(
      DIV_TAG,
      chartProps,
      element(Toolbar, {
        bar: objectField(model, TOOLBAR),
        skin: objectField(model, BUTTON_SKIN),
        colours: colours,
        buttons: drawnButtons(model)
      }),
      element(ChartMount, { model: model })
    );
  }

  function checkFields(model) {
    DECLARED_FIELDS.forEach(function (name) {
      if (!owns(model, name)) {
        chartFaults.push(fault(null, name, MISSING_FAULT, null));
        return;
      }
      if (model[name] === null) {
        chartFaults.push(fault(null, name, NULL_FAULT, null));
      }
    });
  }

  // A wrong type is named only against a bag the surface publishes twice.
  function checkAgainstPeer(where, bag, peer, names) {
    names.forEach(function (name) {
      if (!owns(peer, name) || peer[name] === null) {
        return;
      }
      if (!owns(bag, name)) {
        chartFaults.push(fault(where, name, MISSING_FAULT, null));
        return;
      }
      if (bag[name] === null) {
        chartFaults.push(fault(where, name, NULL_FAULT, null));
        return;
      }
      if (kindOf(bag[name]) !== kindOf(peer[name])) {
        chartFaults.push(fault(where, name, WRONG_TYPE_FAULT, kindOf(bag[name])));
      }
    });
  }

  // Every theme carries the same keys as the theme the surface falls back to.
  function checkThemes(model) {
    var themes = objectField(model, THEMES);
    var order = listField(model, THEME_ORDER);
    var keys = listField(model, THEME_KEYS);
    var peer = objectField(themes, model[FALLBACK_THEME]);
    var seen = {};
    order.forEach(function (name) {
      var spelled = String(name);
      if (owns(seen, spelled)) {
        chartFaults.push(
          fault(THEME_AT + spelled, THEME_ORDER, REPEATED_FAULT, spelled)
        );
        return;
      }
      seen[spelled] = true;
      if (!isPlainObject(themes[spelled])) {
        chartFaults.push(fault(THEME_AT + spelled, THEME_ORDER, MISSING_FAULT, null));
      }
    });
    Object.keys(themes).forEach(function (name) {
      if (!owns(seen, name)) {
        chartFaults.push(fault(THEME_AT + name, THEMES, UNORDERED_FAULT, null));
      }
      checkAgainstPeer(THEME_AT + name, objectField(themes, name), peer, keys);
    });
  }

  // The nine holes the page fills come from the theme the chart was built with.
  function checkColours(model) {
    var colours = colourBag(model);
    var themes = objectField(model, THEMES);
    var chosen = owns(themes, String(model[THEME]))
      ? objectField(themes, String(model[THEME]))
      : objectField(themes, String(model[FALLBACK_THEME]));
    colourKeyList(model).forEach(function (name) {
      if (!owns(colours, name)) {
        chartFaults.push(fault(COLORS, name, MISSING_FAULT, null));
        return;
      }
      if (owns(chosen, name) && chosen[name] !== colours[name]) {
        chartFaults.push(fault(COLORS, name, DISAGREES_FAULT, chosen[name]));
      }
    });
  }

  // One button carries the active timeframe and the others do not.
  function checkButtons(model) {
    var seen = {};
    var live = [];
    listField(model, BUTTONS).forEach(function (one) {
      if (!isPlainObject(one)) {
        chartFaults.push(fault(BUTTONS, null, NOT_AN_OBJECT_FAULT, kindOf(one)));
        return;
      }
      var spelled = String(one[VALUE]);
      if (owns(seen, spelled)) {
        chartFaults.push(
          fault(BUTTON_AT + spelled, BUTTONS, REPEATED_FAULT, spelled)
        );
      }
      seen[spelled] = true;
      if (one[ACTIVE] === true) {
        live.push(spelled);
      }
      var wanted = spelled === String(model[ACTIVE_TIMEFRAME]);
      if (one[ACTIVE] !== wanted) {
        chartFaults.push(
          fault(BUTTON_AT + spelled, ACTIVE, DISAGREES_FAULT, one[ACTIVE])
        );
      }
    });
    if (owns(model, ACTIVE_TIMEFRAME) && !owns(seen, String(model[ACTIVE_TIMEFRAME]))) {
      chartFaults.push(
        fault(null, ACTIVE_TIMEFRAME, UNLISTED_FAULT, model[ACTIVE_TIMEFRAME])
      );
    }
    if (live.length > ONE) {
      chartFaults.push(fault(null, ACTIVE, DISAGREES_FAULT, live.length));
    }
  }

  // The five calls the page answers are named once each, in one order.
  function checkCalls(model) {
    var formats = objectField(model, CALL_FORMATS);
    var order = listField(model, CALL_ORDER);
    var seen = {};
    order.forEach(function (name) {
      var spelled = String(name);
      if (owns(seen, spelled)) {
        chartFaults.push(fault(CALL_ORDER, spelled, REPEATED_FAULT, spelled));
        return;
      }
      seen[spelled] = true;
      if (!owns(formats, spelled)) {
        chartFaults.push(fault(CALL_ORDER, spelled, MISSING_FAULT, null));
      }
    });
    Object.keys(formats).forEach(function (name) {
      if (!owns(seen, name)) {
        chartFaults.push(fault(CALL_FORMATS, name, UNORDERED_FAULT, null));
      }
    });
  }

  // Every value, by dotted path, so one walk serves the colour and number rules.
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

  // A colour CSS reads differently, and a number no JSON payload can carry.
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

  // What CSS paints for one payload: fills, edges, corners, texts, no slope.
  function programme(model) {
    var drawn = drawnButtons(model).length;
    var mark = objectField(model, WATERMARK)[VISIBLE] === true ? ONE : ZERO;
    return {
      fills: drawn + ONE,
      axisLines: drawn * BORDER_EDGES.length,
      slopes: ZERO,
      curves: drawn * RADIUS_CORNERS.length,
      texts: drawn + mark
    };
  }

  // What the mount holds: the series no CSS rule can draw, and their slopes.
  function mountHolds(model) {
    var bands = listField(objectField(model, BOLLINGER_SERIES), FIELDS);
    var series = [CANDLE_SERIES, VOLUME_SERIES, MARKER_SKIN, GRID_LINE_SKIN].concat(
      bands.map(function (one) {
        return BOLLINGER_SERIES + PATH_SPLIT + String(one);
      })
    );
    return { series: series, slopes: bands.length, fed: listField(model, CALLS).length };
  }

  function report() {
    var model = held.model;
    var drawn = programme(model);
    return {
      declared: {
        fields: DECLARED_FIELDS.length,
        themes: listField(model, THEME_ORDER).length,
        colours: colourKeyList(model).length,
        buttons: listField(model, BUTTONS).length,
        calls: listField(model, CALL_ORDER).length
      },
      held: {
        fields: heldFieldCount(),
        themes: Object.keys(objectField(model, THEMES)).length,
        colours: Object.keys(colourBag(model)).length,
        buttons: drawnButtons(model).length,
        calls: Object.keys(objectField(model, CALL_FORMATS)).length
      },
      programme: drawn,
      faults: chartFaults.slice()
    };
  }

  function heldFieldCount() {
    return DECLARED_FIELDS.filter(function (name) {
      return held !== null && owns(held.model, name);
    }).length;
  }

  function setChart(model) {
    if (!isPlainObject(model)) {
      held = null;
      chartFaults = [fault(null, null, NOT_AN_OBJECT_FAULT, kindOf(model))];
      return {
        declared: null,
        held: null,
        programme: null,
        faults: chartFaults.slice()
      };
    }
    held = { model: model };
    chartFaults = [];
    checkFields(model);
    checkThemes(model);
    checkColours(model);
    checkButtons(model);
    checkCalls(model);
    checkValues(model);
    return report();
  }

  // A failed load is not remembered, so a later ask reaches the bridge.
  function loadChart(params) {
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
        setChart(model);
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

  function themes() {
    var found = {};
    Object.keys(objectField(held === null ? {} : held.model, THEMES)).forEach(
      function (name) {
        found[name] = copyOf(objectField(objectField(held.model, THEMES), name));
      }
    );
    return found;
  }

  function theme(name) {
    var table = objectField(held === null ? {} : held.model, THEMES);
    return owns(table, name) ? copyOf(objectField(table, name)) : undefined;
  }

  function colourKeys() {
    return held === null ? [] : colourKeyList(held.model);
  }

  function buttons() {
    return list(BUTTONS).map(function (one) {
      return isPlainObject(one) ? copyOf(one) : one;
    });
  }

  function buttonValues() {
    return held === null
      ? []
      : drawnButtons(held.model).map(function (one) {
          return one[VALUE];
        });
  }

  function drawnProgramme() {
    return held === null ? null : programme(held.model);
  }

  function mount() {
    return held === null ? null : mountHolds(held.model);
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

  function asking() {
    return lastCall;
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

  function renderChart(target, model) {
    var payload = model;
    if (!isPlainObject(payload)) {
      payload = held === null ? null : held.model;
    }
    lastTarget = target;
    return draw(target, element(Chart, { model: payload }));
  }

  // The last target is drawn again after the surface answers a chosen timeframe.
  function redraw() {
    if (lastTarget === null) {
      return null;
    }
    return renderChart(lastTarget);
  }

  function forget() {
    held = null;
    chartFaults = [];
    loadFault = null;
    asked = null;
    lastTarget = null;
    lastCall = null;
  }

  global.acervatorSetTradingViewChart = setChart;
  global.acervatorLoadTradingViewChart = loadChart;
  global.acervatorTradingViewChart = {
    method: METHOD,
    Chart: Chart,
    Toolbar: Toolbar,
    TimeframeButton: TimeframeButton,
    ChartMount: ChartMount,
    Watermark: Watermark,
    field: field,
    declaredNames: declaredNames,
    themes: themes,
    theme: theme,
    themeOrder: function () {
      return list(THEME_ORDER);
    },
    themeKeys: function () {
      return list(THEME_KEYS);
    },
    colours: function () {
      return bag(COLORS);
    },
    colourKeys: colourKeys,
    buttons: buttons,
    buttonValues: buttonValues,
    page: function () {
      return bag(PAGE);
    },
    webView: function () {
      return bag(WEB_VIEW);
    },
    toolbar: function () {
      return bag(TOOLBAR);
    },
    buttonSkin: function () {
      return bag(BUTTON_SKIN);
    },
    candleSeries: function () {
      return bag(CANDLE_SERIES);
    },
    volumeSeries: function () {
      return bag(VOLUME_SERIES);
    },
    bollingerSeries: function () {
      return bag(BOLLINGER_SERIES);
    },
    markerSkin: function () {
      return bag(MARKER_SKIN);
    },
    gridLineSkin: function () {
      return bag(GRID_LINE_SKIN);
    },
    watermark: function () {
      return bag(WATERMARK);
    },
    timeScale: function () {
      return bag(TIME_SCALE);
    },
    callFormats: function () {
      return bag(CALL_FORMATS);
    },
    callOrder: function () {
      return list(CALL_ORDER);
    },
    calls: function () {
      return list(CALLS);
    },
    candleFields: function () {
      return list(CANDLE_FIELDS);
    },
    markerFields: function () {
      return list(MARKER_FIELDS);
    },
    gridLevelFields: function () {
      return list(GRID_LEVEL_FIELDS);
    },
    actions: function () {
      return bag(ACTIONS);
    },
    timers: function () {
      return bag(TIMERS);
    },
    timerDelays: function () {
      return list(TIMER_DELAYS);
    },
    busTopics: function () {
      return list(BUS_TOPICS);
    },
    skin: function () {
      return bag(SKIN);
    },
    programme: drawnProgramme,
    mount: mount,
    qtColour: qtColour,
    variableFor: variableFor,
    variableInGroups: variableInGroups,
    spacing: spacing,
    radius: radius,
    typeSize: typeSize,
    borderWidth: borderWidth,
    paint: paint,
    kinds: kinds,
    faults: faults,
    loadError: loadError,
    asking: asking,
    isLoaded: isLoaded,
    renderChart: renderChart,
    forget: forget
  };
})(window);
