// The Asset Charts tab, as the Python surface serves it to the global page.
(function (global) {
  "use strict";

  var METHOD = "trade_charts_tab.state";

  var PREV_TEXT = "prev_text";
  var NEXT_TEXT = "next_text";
  var PREV_TOOLTIP = "prev_tooltip";
  var NEXT_TOOLTIP = "next_tooltip";
  var TICKER_TOOLTIP = "ticker_tooltip";
  var ARROW_WIDTH = "arrow_width_px";
  var ARROW_HEIGHT = "arrow_height_px";
  var TICKER_MIN_WIDTH = "ticker_min_width_px";
  var SELECTOR_ITEMS = "items";
  var SELECTOR_SHOWN = "shown";
  var POSITION_TEXT = "position_text";
  var STEPPING_ENABLED = "stepping_enabled";
  var STEP_PARAM = "step_by";
  var PICK_PARAM = "pick_at";
  var TOGGLE_PARAM = "toggle_list";

  var LIST_TEXT = "list_text";
  var LIST_MODE = "list_mode";
  var TOGGLE_TOOLTIP = "toggle_tooltip";
  var TOGGLE_WIDTH = "toggle_width_px";
  var TOGGLE_HEIGHT = "toggle_height_px";
  var SHOWING_ATA = "showing_ata";
  var ATA_EMPTY_HINT = "ata_empty_hint";
  var LISTS = "lists";


  var ACCESSIBLE_NAME = "accessible_name";
  var CONTAINER = "container";
  var CONTENT = "content";
  var ASSET_ORDER = "asset_order";
  var ASSET_COUNT = "asset_count";
  var ASSETS = "assets";
  var SELECTOR = "selector";
  var PANEL = "panel";
  var SHOWN_ID = "shown_id";
  var SHOWN_SYMBOL = "shown_symbol";
  var FOLLOWED = "followed";
  var DROPPED = "dropped";
  var TRADE_LOG = "trade_log";
  var LOGS = "logs";
  var SIGNALS = "signals";
  var SIGNAL_NAMES = "signal_names";
  var THROTTLED_SIGNALS = "throttled_signals";
  var PANEL_CHROME = "panel_chrome";
  var TOGGLES = "toggles";
  var LEGEND = "legend";
  var LEGEND_STYLES = "legend_styles";
  var TOGGLE_KEY = "key";
  var CHECKED = "checked";
  var COLOR = "color";
  var TOGGLE_GAP = "toggle_gap_px";
  var LEGEND_GAP = "legend_gap_px";
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
    FOLLOWED,
    FORMATS,
    KEYS,
    LISTS,
    LOGS,
    NUCLEAR_DEFAULTS,
    OUTCOMES,
    ASSETS,
    ASSET_COUNT,
    ASSET_ORDER,
    PANEL,
    PANEL_CHROME,
    PANEL_DEFAULTS,
    SELECTOR,
    SHOWN_ID,
    SHOWN_SYMBOL,
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
  var LAYOUT_SLOTS = "layout_slots";

  // The list-toggle row, the selector row, the chart panel and the toggle row.
  var LAYOUT_SLOT_COUNT = 4;

  var SYMBOL = "symbol";
  var EXCHANGE_ID = "exchange_id";
  var LAST_FETCH = "last_fetch";
  var SYNTHETIC = "synthetic";

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

  // The chart slot asks the tab for the image `native_chart.py` paints, at
  // the slot's own width and the page's device pixel ratio.
  var IMAGE_METHOD = "trade_charts_tab.image";
  var IMAGE_WIDTH_PARAM = "width";
  var IMAGE_HEIGHT_PARAM = "height";
  var IMAGE_RATIO_PARAM = "dpr";
  var TOGGLE_KEY_PARAM = "toggle_overlay";
  var TOGGLE_ON_PARAM = "toggle_on";
  var IMAGE_DATA_URI = "data_uri";
  var IMAGE_WIDTH = "width_px";
  var IMAGE_HEIGHT = "height_px";
  var IMAGE_NATURAL_HEIGHT = "natural_height_px";
  var IMAGE_RATIO = "device_pixel_ratio";
  var IMAGE_SHA = "sha256";
  var IMAGE_CANDLES = "candle_count";
  var PAINTER = "native_chart.py";

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

  var PANEL_AT = "asset:";
  var LEGEND_AT = "legend:";
  var TOOLBAR_GAP_KEY = "toolbar-gap";
  var TOGGLE_BOX_SUFFIX = ":box";
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
  var WRAP = "wrap";
  var ELLIPSIS = "ellipsis";
  var SELECT_NONE = "none";
  var FULL = "100%";
  var CENTER = "center";
  var DIV_TAG = "div";
  var SPAN_TAG = "span";
  var BUTTON_TAG = "button";
  var SELECT_TAG = "select";
  var OPTION_TAG = "option";
  var LABEL_TAG = "label";
  var INPUT_TAG = "input";
  var IMG_TAG = "img";
  var CHECKBOX_TYPE = "checkbox";
  var BLOCK = "block";

  var TAB_CLASS = "acervator-charts-tab";
  var PANEL_CLASS = "acervator-charts-panel";
  var CHART_CLASS = "acervator-charts-mount";

  var TAB_PART = "tab";
  var CONTENT_PART = "content";
  var SELECTOR_PART = "asset-selector";
  var LIST_ROW_PART = "chart-list-row";
  var LIST_TOGGLE_PART = "chart-list-toggle";
  var LIST_HINT_PART = "chart-list-hint";
  var PREV_PART = "asset-prev";
  var NEXT_PART = "asset-next";
  var TICKER_PART = "asset-ticker";
  var POSITION_PART = "asset-position";
  var PANEL_PART = "chart-panel";
  var HEADER_PART = "panel-header";
  var TOOLBAR_PART = "panel-toolbar";
  var TIMEFRAME_PART = "timeframe";
  var SOURCE_PART = "panel-source";
  var LEGEND_PART = "panel-legend";
  var TOGGLE_ROW_PART = "panel-toggle-row";
  var TOGGLE_PART = "panel-toggle";
  var CHART_PART = "chart-mount";
  var CHART_HOST_PART = "chart-host";
  var CHART_IMAGE_PART = "chart-image";
  var ERROR_PART = "panel-error";
  var EMPTY_PART = "empty-column";

  // The slot `native_chart.py` paints into, through the tab's image ask.
  var CHART_SLOT = "native_chart";

  var PART_ATTR = "data-part";
  var SLOT_ATTR = "data-slot";
  var BOT_ATTR = "data-bot";
  var SYMBOL_ATTR = "data-symbol";
  var TOGGLE_ATTR = "data-toggle";
  var PAINTER_ATTR = "data-painter";
  var IMAGE_WIDTH_ATTR = "data-width-px";
  var IMAGE_HEIGHT_ATTR = "data-height-px";
  var IMAGE_RATIO_ATTR = "data-dpr";
  var IMAGE_SHA_ATTR = "data-sha256";
  var FAULT_ATTR = "data-fault";

  var SELECT_OPEN = "[";
  var SELECT_IS = "=\"";
  var SELECT_CLOSE = "\"]";
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
  var LIST_ATTR = "data-list-mode";
  var LISTED_ATTR = "data-listed";
  var SLOTS_ATTR = "data-layout-slots";
  var MOUNTED_ATTR = "data-mounted";
  var DECLARED_ATTR = "data-declared-panels";
  var ACTION_ATTR = "data-action";
  var ARIA_LABEL = "aria-label";

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

  function assetsOf(model) {
    return objectField(model, ASSETS);
  }

  // The bots the ticker list really offers, which is the order minus the unknown.
  function knownOrder(model) {
    var assets = assetsOf(model);
    var seen = {};
    return listField(model, ASSET_ORDER).filter(function (botId) {
      var name = String(botId);
      if (!isPlainObject(assets[name]) || owns(seen, name)) {
        return false;
      }
      seen[name] = true;
      return true;
    });
  }

  // Moving the arrows or the ticker list asks the surface for the new asset.
  function assetChosen(param, value) {
    if (!global.acervator || typeof global.acervator.call !== "function") {
      loadFault = NO_BRIDGE;
      return Promise.resolve(null);
    }
    var params = {};
    params[param] = value;
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
    params[TIMEFRAME_CHANGE_PARAM] = chosen;
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

  // A toggled overlay reaches the painter through the surface, and the box
  // reads the painter's own state back off the answer.
  function overlayChosen(key, on) {
    if (!global.acervator || typeof global.acervator.call !== "function") {
      loadFault = NO_BRIDGE;
      return Promise.resolve(null);
    }
    var params = {};
    params[TOGGLE_KEY_PARAM] = key;
    params[TOGGLE_ON_PARAM] = Boolean(on);
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

  // acervatorHeader owns the Qt style sheet parsing that paints a legend entry.
  function legendStyle(chrome, at) {
    var api = global.acervatorHeader;
    var sheets = listField(chrome, LEGEND_STYLES);
    if (!api || typeof api.styleOf !== "function" || at >= sheets.length) {
      return {};
    }
    return api.styleOf(sheets[at]);
  }

  // The two position markers the chart pins to the price axis.
  function PanelLegend(props) {
    var chrome = props.chrome;
    var legendProps = {
      style: {
        display: FLEX,
        gap: height(chrome[LEGEND_GAP]),
        flex: FLEX_NONE
      }
    };
    legendProps[PART_ATTR] = LEGEND_PART;
    legendProps[BOT_ATTR] = text(props.botId);
    return element(
      DIV_TAG,
      legendProps,
      listField(chrome, LEGEND).map(function (one, at) {
        return element(
          SPAN_TAG,
          { key: LEGEND_AT + String(at), style: legendStyle(chrome, at) },
          text(one)
        );
      })
    );
  }

  // One check box per overlay the chart can draw, in the order it offers them.
  function PanelToggle(one) {
    var boxProps = {
      key: one[TOGGLE_KEY],
      style: { color: text(one[COLOR]), display: FLEX, alignItems: CENTER }
    };
    boxProps[PART_ATTR] = TOGGLE_PART;
    boxProps[TOGGLE_ATTR] = text(one[TOGGLE_KEY]);
    return element(
      LABEL_TAG,
      boxProps,
      element(INPUT_TAG, {
        key: one[TOGGLE_KEY] + TOGGLE_BOX_SUFFIX,
        type: CHECKBOX_TYPE,
        "aria-label": text(one[LABEL]),
        checked: Boolean(one[CHECKED]),
        onChange: function (event) {
          overlayChosen(one[TOGGLE_KEY], event.target.checked);
        }
      }),
      text(one[LABEL])
    );
  }

  // Fourteen boxes wrap to a second row where the tab is too narrow for one.
  function PanelToggles(props) {
    var chrome = props.chrome;
    var rowProps = {
      style: {
        display: FLEX,
        flexWrap: WRAP,
        gap: height(chrome[TOGGLE_GAP]),
        flex: FLEX_NONE,
        alignItems: CENTER
      }
    };
    rowProps[PART_ATTR] = TOGGLE_ROW_PART;
    rowProps[BOT_ATTR] = text(props.botId);
    return element(DIV_TAG, rowProps, listField(chrome, TOGGLES).map(PanelToggle));
  }

  // The host the painted image lands in, carrying the panel values the tab fed it.
  function ChartMount(props) {
    var panel = props.panel;
    var mountProps = {
      className: CHART_CLASS,
      style: {
        flex: AUTO,
        overflow: HIDDEN,
        display: FLEX,
        flexDirection: COLUMN
      }
    };
    mountProps[PART_ATTR] = CHART_PART;
    mountProps[SLOT_ATTR] = CHART_SLOT;
    mountProps[BOT_ATTR] = text(props.botId);
    mountProps[SYMBOL_ATTR] = text(panel[SYMBOL]);
    mountProps[CHART_TF_ATTR] = text(panel[CHART_TIMEFRAME]);
    mountProps[CANDLES_ATTR] = text(panel[CANDLE_COUNT]);
    mountProps[MARKERS_ATTR] = text(listField(panel, MARKERS).length);
    mountProps[FLOORS_ATTR] = text(listField(panel, FLOORS).length);
    mountProps[ANCHOR_ATTR] = text(panel[TB_ANCHOR]);
    mountProps[CEILING_ATTR] = text(panel[TB_CEILING]);
    mountProps[ARMED_ATTR] = text(panel[ARMED] === null ? null : Boolean(panel[ARMED]));

    // renderChartMounts places the image element inside this host itself, so
    // React declares no child of its own inside it and never removes one.
    var hostProps = { key: CHART_HOST_PART, style: { flex: AUTO, overflow: HIDDEN } };
    hostProps[PART_ATTR] = CHART_HOST_PART;
    hostProps[BOT_ATTR] = text(props.botId);

    var drawn = [];
    var errorText = panel[ERROR_TEXT];
    if (typeof errorText === "string" && errorText.length) {
      var errorProps = {
        key: ERROR_PART,
        style: { flex: FLEX_NONE, userSelect: SELECT_NONE }
      };
      errorProps[PART_ATTR] = ERROR_PART;
      errorProps[BOT_ATTR] = text(props.botId);
      drawn.push(element(DIV_TAG, errorProps, errorText));
    }
    drawn.push(element(DIV_TAG, hostProps, null));
    return element(DIV_TAG, mountProps, drawn);
  }

  // The Live / ATA-SMP toggle, above the arrows and the ticker list.
  function ListToggle(props) {
    var selector = props.selector;
    var rowProps = {
      style: {
        display: FLEX,
        flexDirection: ROW,
        alignItems: CENTER,
        flex: FLEX_NONE,
        gap: spacing(selector[SPACING])
      }
    };
    rowProps[PART_ATTR] = LIST_ROW_PART;
    rowProps[LIST_ATTR] = text(selector[LIST_MODE]);

    var toggleProps = {
      style: {
        width: height(selector[TOGGLE_WIDTH]),
        height: height(selector[TOGGLE_HEIGHT]),
        flex: FLEX_NONE
      },
      title: text(selector[TOGGLE_TOOLTIP]),
      onClick: function () {
        assetChosen(TOGGLE_PARAM, true);
      }
    };
    toggleProps[PART_ATTR] = LIST_TOGGLE_PART;
    toggleProps[ARIA_LABEL] = label(selector[TOGGLE_TOOLTIP]);
    toggleProps.key = LIST_TOGGLE_PART;

    var drawn = [element(BUTTON_TAG, toggleProps, text(selector[LIST_TEXT]))];
    if (selector[SHOWING_ATA] === true && !props.listed) {
      var hintProps = { key: LIST_HINT_PART, style: { flex: FLEX_NONE } };
      hintProps[PART_ATTR] = LIST_HINT_PART;
      drawn.push(element(DIV_TAG, hintProps, text(selector[ATA_EMPTY_HINT])));
    }
    return element(DIV_TAG, rowProps, drawn);
  }

  // The arrows, the ticker list and the readout that says which of how many.
  function Selector(props) {
    var selector = props.selector;
    var rowProps = {
      style: {
        display: FLEX,
        flexDirection: ROW,
        alignItems: CENTER,
        flex: FLEX_NONE,
        gap: spacing(selector[SPACING])
      }
    };
    rowProps[PART_ATTR] = SELECTOR_PART;

    var stepping = selector[STEPPING_ENABLED] === true;
    var arrowStyle = {
      width: height(selector[ARROW_WIDTH]),
      height: height(selector[ARROW_HEIGHT]),
      flex: FLEX_NONE
    };

    var prevProps = {
      style: arrowStyle,
      disabled: !stepping,
      title: text(selector[PREV_TOOLTIP]),
      onClick: function () {
        assetChosen(STEP_PARAM, -1);
      }
    };
    prevProps[PART_ATTR] = PREV_PART;
    prevProps[ARIA_LABEL] = label(selector[PREV_TOOLTIP]);

    var nextProps = {
      style: arrowStyle,
      disabled: !stepping,
      title: text(selector[NEXT_TOOLTIP]),
      onClick: function () {
        assetChosen(STEP_PARAM, 1);
      }
    };
    nextProps[PART_ATTR] = NEXT_PART;
    nextProps[ARIA_LABEL] = label(selector[NEXT_TOOLTIP]);

    var items = listField(selector, SELECTOR_ITEMS);
    var tickerProps = {
      style: { minWidth: height(selector[TICKER_MIN_WIDTH]), flex: FLEX_NONE },
      value: text(items[selector[SELECTOR_SHOWN]]),
      title: text(selector[TICKER_TOOLTIP]),
      onChange: function (event) {
        assetChosen(PICK_PARAM, event.target.selectedIndex);
      }
    };
    tickerProps[PART_ATTR] = TICKER_PART;
    tickerProps[ARIA_LABEL] = label(selector[TICKER_TOOLTIP]);
    var drawn = items.map(function (one) {
      return element(OPTION_TAG, { key: String(one), value: text(one) }, text(one));
    });

    var positionProps = { style: { flex: FLEX_NONE, userSelect: SELECT_NONE } };
    positionProps[PART_ATTR] = POSITION_PART;

    return element(
      DIV_TAG,
      rowProps,
      element(BUTTON_TAG, prevProps, text(selector[PREV_TEXT])),
      element(SELECT_TAG, tickerProps, drawn),
      element(BUTTON_TAG, nextProps, text(selector[NEXT_TEXT])),
      element(DIV_TAG, positionProps, text(selector[POSITION_TEXT]))
    );
  }

  function Panel(props) {
    var info = props.info;
    var panel = props.panel;
    var style = { display: FLEX, flexDirection: COLUMN, flex: AUTO };
    style.minHeight = height(panel[MINIMUM_HEIGHT]);
    style.maxHeight = height(panel[MAXIMUM_HEIGHT]);
    var panelProps = { className: PANEL_CLASS, style: style };
    panelProps[PART_ATTR] = PANEL_PART;
    panelProps[BOT_ATTR] = text(props.botId);
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
        element(DIV_TAG, { key: TOOLBAR_GAP_KEY, style: { flex: AUTO } }),
        element(PanelLegend, { botId: props.botId, chrome: props.chrome }),
        element(PanelSource, { botId: props.botId, panel: panel })
      ),
      element(ChartMount, { botId: props.botId, panel: panel }),
      element(PanelToggles, { botId: props.botId, chrome: props.chrome })
    );
  }

  // The toggle row and the selector row over the one chart panel Qt draws.
  function Content(props) {
    var model = props.model;
    var content = objectField(model, CONTENT);
    var known = knownOrder(model);
    var shownId = text(model[SHOWN_ID]);
    var selectorBag = objectField(model, SELECTOR);
    var contentProps = { style: boxStyle(content, COLUMN) };
    contentProps.style.flex = AUTO;
    contentProps[PART_ATTR] = CONTENT_PART;
    contentProps[SLOTS_ATTR] = text(content[LAYOUT_SLOTS]);
    contentProps[MOUNTED_ATTR] = String(known.length ? ONE : ZERO);
    contentProps[DECLARED_ATTR] = text(model[ASSET_COUNT]);
    contentProps[LIST_ATTR] = text(selectorBag[LIST_MODE]);
    contentProps[LISTED_ATTR] = text(listField(model, ASSET_ORDER).length);

    var drawn = [
      element(ListToggle, {
        key: LIST_ROW_PART,
        selector: selectorBag,
        listed: listField(model, ASSET_ORDER).length
      }),
      element(Selector, {
        key: SELECTOR_PART,
        selector: selectorBag
      })
    ];
    if (known.length) {
      drawn.push(
        element(Panel, {
          key: shownId,
          botId: shownId,
          info: objectField(assetsOf(model), shownId),
          panel: objectField(model, PANEL),
          chrome: objectField(model, PANEL_CHROME),
          options: timeframeOptionList(model),
          action: objectField(model, ACTIONS)[TIMEFRAME_ACTION]
        })
      );
    } else {
      var emptyProps = { key: EMPTY_PART, style: { flex: AUTO } };
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
    var tabProps = {
      id: props.id,
      className: TAB_CLASS,
      style: boxStyle(objectField(model, CONTAINER), COLUMN)
    };
    tabProps.style.overflow = HIDDEN;
    tabProps.style.height = FULL;
    tabProps[PART_ATTR] = TAB_PART;
    tabProps[ARIA_LABEL] = label(model[ACCESSIBLE_NAME]);

    return element(DIV_TAG, tabProps, element(Content, { model: model }));
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

  var INFO_FIELDS = [SYMBOL, EXCHANGE_ID, LAST_FETCH];

  var PANEL_FIELDS = [
    SYMBOL,
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
    var assets = assetsOf(model);
    var order = listField(model, ASSET_ORDER);
    var options = timeframeOptionList(model);
    var defaults = objectField(model, PANEL_DEFAULTS);
    var names = Object.keys(assets);
    var bags = names.map(function (name) {
      return objectField(assets, name);
    });
    var first = peerOf(bags, INFO_FIELDS);
    var seen = {};

    order.forEach(function (botId) {
      var name = String(botId);
      if (owns(seen, name)) {
        chartFaults.push(fault(PANEL_AT + name, ASSET_ORDER, REPEATED_FAULT, name));
        return;
      }
      seen[name] = true;
      if (!isPlainObject(assets[name])) {
        chartFaults.push(fault(PANEL_AT + name, ASSET_ORDER, UNMOUNTED_FAULT, null));
      }
    });
    names.forEach(function (name) {
      var where = PANEL_AT + name;
      if (!owns(seen, name)) {
        chartFaults.push(fault(where, ASSETS, UNORDERED_FAULT, null));
      }
      checkAgainstPeer(where, objectField(assets, name), first, INFO_FIELDS);
    });
    if (owns(model, ASSET_COUNT) && names.length !== model[ASSET_COUNT]) {
      chartFaults.push(fault(null, ASSET_COUNT, DISAGREES_FAULT, names.length));
    }

    var panel = objectField(model, PANEL);
    checkPanelTypes(PANEL, panel, peerOf([panel], PANEL_FIELDS), defaults);
    checkPanelCounts(PANEL, panel);
    checkTimeframe(PANEL, panel, options);
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

  // The surface and this module must name the same number of tab rows.
  function checkSlots(model) {
    var content = objectField(model, CONTENT);
    if (!owns(content, LAYOUT_SLOTS)) {
      return;
    }
    if (content[LAYOUT_SLOTS] !== LAYOUT_SLOT_COUNT) {
      chartFaults.push(
        fault(CONTENT, LAYOUT_SLOTS, DISAGREES_FAULT, LAYOUT_SLOT_COUNT)
      );
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
    var assets = assetsOf(model);
    return {
      declared: {
        fields: DECLARED_FIELDS.length,
        panels: model[ASSET_COUNT],
        slots: objectField(model, CONTENT)[LAYOUT_SLOTS],
        candles: declaredCandles(assets)
      },
      held: {
        fields: heldFieldCount(),
        panels: Object.keys(assets).length,
        slots: LAYOUT_SLOT_COUNT,
        candles: heldCandles(assets)
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

  // `reset` drops the panels an earlier paint left, so a fresh open draws
  // only the bots this answer carries.
  function openingRequest() {
    return { reset: true };
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

  function panelIds() {
    return held === null ? [] : Object.keys(assetsOf(held.model));
  }

  function panelOrder() {
    return list(ASSET_ORDER);
  }

  function mountedIds() {
    return held === null ? [] : knownOrder(held.model);
  }

  function panel(name) {
    if (held === null) {
      return undefined;
    }
    var assets = assetsOf(held.model);
    return owns(assets, name) ? copyOf(objectField(assets, name)) : undefined;
  }

  function shownPanel() {
    return held === null ? {} : copyOf(objectField(held.model, PANEL));
  }

  function selector() {
    return bag(SELECTOR);
  }

  function lists() {
    return bag(LISTS);
  }

  function listMode() {
    return held === null ? undefined : objectField(held.model, SELECTOR)[LIST_MODE];
  }

  function container() {
    return bag(CONTAINER);
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

  function chartMounts(target) {
    return target.querySelectorAll(
      SELECT_OPEN + PART_ATTR + SELECT_IS + CHART_PART + SELECT_CLOSE
    );
  }

  // The one image element inside a chart host, made on the first answer.
  function imageIn(into) {
    var found = into.querySelector(
      SELECT_OPEN + PART_ATTR + SELECT_IS + CHART_IMAGE_PART + SELECT_CLOSE
    );
    if (found !== null) {
      return found;
    }
    found = document.createElement(IMG_TAG);
    found.setAttribute(PART_ATTR, CHART_IMAGE_PART);
    found.setAttribute(PAINTER_ATTR, PAINTER);
    found.style.display = BLOCK;
    into.appendChild(found);
    return found;
  }

  // The answer's image goes into the host at its CSS size. The mount takes
  // the painter's natural height as its floor, so the toggles under it never
  // cover a sub-pane, while the image itself fills whatever height the host has.
  function placeImage(mount, into, answer) {
    var image = imageIn(into);
    image.setAttribute(IMAGE_WIDTH_ATTR, text(answer[IMAGE_WIDTH]));
    image.setAttribute(IMAGE_HEIGHT_ATTR, text(answer[IMAGE_HEIGHT]));
    image.setAttribute(IMAGE_RATIO_ATTR, text(answer[IMAGE_RATIO]));
    image.setAttribute(IMAGE_SHA_ATTR, text(answer[IMAGE_SHA]));
    image.setAttribute(CANDLES_ATTR, text(answer[IMAGE_CANDLES]));
    image.style.width = height(answer[IMAGE_WIDTH]);
    image.style.height = height(answer[IMAGE_HEIGHT]);
    image.src = String(answer[IMAGE_DATA_URI]);
    mount.style.minHeight = height(answer[IMAGE_NATURAL_HEIGHT]);
    into.removeAttribute(FAULT_ATTR);
  }

  // Every chart slot asks the tab for the image `native_chart.py` paints of
  // the asset its panel follows, at the slot's width and the page's device
  // pixel ratio. A refused ask is named on the slot rather than drawn over.
  function renderChartMounts(target) {
    var mounts = chartMounts(target);
    var reachable =
      Boolean(global.acervator) && typeof global.acervator.call === "function";
    var drawn = [];
    var chain = Promise.resolve();
    Array.prototype.forEach.call(mounts, function (mount) {
      var symbol = mount.getAttribute(SYMBOL_ATTR);
      var into = mount.querySelector(
        SELECT_OPEN + PART_ATTR + SELECT_IS + CHART_HOST_PART + SELECT_CLOSE
      );
      if (into === null) {
        return;
      }
      mount.setAttribute(SLOT_ATTR, CHART_SLOT);
      if (!reachable) {
        into.setAttribute(FAULT_ATTR, NO_BRIDGE);
        into.textContent = NO_BRIDGE;
        return;
      }
      var params = {};
      params[IMAGE_WIDTH_PARAM] = into.clientWidth;
      params[IMAGE_HEIGHT_PARAM] = into.clientHeight;
      params[IMAGE_RATIO_PARAM] = global.devicePixelRatio || 1;
      chain = chain
        .then(function () {
          return global.acervator.call(IMAGE_METHOD, params);
        })
        .then(
          function (answer) {
            if (!isPlainObject(answer)) {
              into.setAttribute(FAULT_ATTR, String(answer));
              return;
            }
            placeImage(mount, into, answer);
            drawn.push(symbol);
          },
          function (err) {
            into.setAttribute(FAULT_ATTR, err && err.message ? err.message : String(err));
          }
        );
    });
    return chain.then(function () {
      return drawn;
    });
  }

  function renderTab(target, model) {
    var payload = model;
    if (!isPlainObject(payload)) {
      payload = held === null ? null : held.model;
    }
    lastTarget = target;
    var shown = draw(target, element(Tab, { model: payload }));
    renderChartMounts(target);
    return shown;
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
      method: METHOD,
      render: renderTab,
      load: loadCharts,
      loadError: loadError,
      request: openingRequest
    });
  }

  global.acervatorSetCharts = setCharts;
  global.acervatorLoadCharts = loadCharts;
  global.acervatorCharts = {
    method: METHOD,
    Tab: Tab,
    Content: Content,
    ListToggle: ListToggle,
    Selector: Selector,
    Panel: Panel,
    PanelHeader: PanelHeader,
    PanelSource: PanelSource,
    TimeframeControl: TimeframeControl,
    ChartMount: ChartMount,
    field: field,
    declaredNames: declaredNames,
    selector: selector,
    lists: lists,
    listMode: listMode,
    shownPanel: shownPanel,
    container: container,
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
    renderChartMounts: renderChartMounts,
    forget: forget
  };
})(window);
