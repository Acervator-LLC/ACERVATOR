// The Asset Charts drawing, as the Python surface serves it.
(function (global) {
  "use strict";

  var METHOD = "native_chart.state";

  var ACCESSIBLE_NAME = "accessible_name";
  var ACTIONS = "actions";
  var BACKGROUND_CSS = "background_css";
  var BUS_TOPICS = "bus_topics";
  var CANDLE_COUNT = "candle_count";
  var CANDLES = "candles";
  var EMPTY_VIEW = "empty";
  var ERROR_TEXT = "error_text";
  var FIRE_ARMED_STATE = "fire_armed_state";
  var FLAGS = "flags";
  var GRID_LINES_HELD = "grid_lines_held";
  var HEADER_PARTS = "header_parts";
  var HEADER_TEXT = "header_text";
  var MARKERS = "markers";
  var METRICS = "metrics";
  var MINIMUM_HEIGHT = "minimum_height_px";
  var NATURAL_HEIGHT = "natural_height_px";
  var OHLC_ROW = "ohlc_row";
  var OHLC_ROW_CSS = "ohlc_row_css";
  var PANES = "panes";
  var PARENT_HEIGHT_PAD = "parent_height_pad_px";
  var POSITIONS = "positions";
  var PRICE_AXIS = "price_axis";
  var PRICE_LINES = "price_lines";
  var RESIZE_GRIP = "resize_grip_px";
  var SIGNALS = "signals";
  var SKIN = "skin";
  var SKIN_CSS = "skin_css";
  var SOURCE_LABEL = "source_label";
  var STATUS_TEXT = "status_text";
  var STEPS = "steps";
  var SUB_PANES = "sub_panes";
  var SYMBOL = "symbol";
  var TARGET_BALANCE = "target_balance";
  var THREADS = "threads";
  var TIME_AXIS = "time_axis";
  var TIMEFRAME = "timeframe";
  var TIMEFRAMES = "timeframes";
  var TIMER_DELAYS = "timer_delays_ms";
  var TIMERS = "timers";
  var TRANCHE_FLOORS = "tranche_floors";
  var VISIBLE_COUNT = "visible_count";
  var VISIBLE_START = "visible_start";
  var Y_ZOOM = "y_zoom_pct";

  var DECLARED_FIELDS = [
    ACCESSIBLE_NAME,
    ACTIONS,
    BACKGROUND_CSS,
    BUS_TOPICS,
    CANDLE_COUNT,
    CANDLES,
    EMPTY_VIEW,
    ERROR_TEXT,
    FIRE_ARMED_STATE,
    FLAGS,
    GRID_LINES_HELD,
    HEADER_PARTS,
    HEADER_TEXT,
    MARKERS,
    METRICS,
    MINIMUM_HEIGHT,
    NATURAL_HEIGHT,
    OHLC_ROW,
    OHLC_ROW_CSS,
    PANES,
    PARENT_HEIGHT_PAD,
    POSITIONS,
    PRICE_AXIS,
    PRICE_LINES,
    RESIZE_GRIP,
    SIGNALS,
    SKIN,
    SKIN_CSS,
    SOURCE_LABEL,
    STATUS_TEXT,
    STEPS,
    SUB_PANES,
    SYMBOL,
    TARGET_BALANCE,
    THREADS,
    TIME_AXIS,
    TIMEFRAME,
    TIMEFRAMES,
    TIMER_DELAYS,
    TIMERS,
    TRANCHE_FLOORS,
    VISIBLE_COUNT,
    VISIBLE_START,
    Y_ZOOM
  ];

  // A null STATE_FIELDS entry says the chart is not in that state.
  var STATE_FIELDS = [
    CANDLES,
    EMPTY_VIEW,
    OHLC_ROW,
    OHLC_ROW_CSS,
    PANES,
    PRICE_AXIS,
    PRICE_LINES,
    TIME_AXIS
  ];

  var BAG_FIELDS = [
    ACTIONS,
    FIRE_ARMED_STATE,
    FLAGS,
    METRICS,
    SKIN,
    SKIN_CSS,
    TARGET_BALANCE,
    TIMERS
  ];

  var LIST_FIELDS = [
    BUS_TOPICS,
    HEADER_PARTS,
    MARKERS,
    POSITIONS,
    SIGNALS,
    STEPS,
    SUB_PANES,
    THREADS,
    TIMEFRAMES,
    TIMER_DELAYS,
    TRANCHE_FLOORS
  ];

  var BODIES = "bodies";
  var GRID = "grid";
  var TICKS = "ticks";
  var INDEX = "index";
  var LABEL = "label";
  var MESSAGE = "message";
  var COLOR_CSS = "color_css";
  var COLORS_CSS = "colors_css";
  var VOLUME_COLORS_CSS = "volume_colors_css";
  var LABEL_COLOR_CSS = "label_color_css";
  var VOLUME_AXIS_LABEL = "volume_axis_label";
  var MAX_VOLUME = "max_volume";
  var FILL = "fill";
  var BORDER = "border";
  var WICK = "wick";
  var KIND = "kind";
  var STYLE = "style";
  var WIDTH_FIELD = "width_px";
  var ON_PANE = "on_pane";
  var MAJOR = "major";
  var UP = "up";
  var Y_PX = "y_px";
  var X_PX = "x_px";
  var BODY_X = "body_x_px";
  var BODY_Y = "body_y_px";
  var BODY_WIDTH = "body_width_px";
  var BODY_HEIGHT = "body_height_px";
  var WICK_X = "wick_x_px";
  var WICK_Y = "wick_y_px";
  var WICK_HEIGHT = "wick_height_px";
  var VOLUME_Y = "volume_y_px";
  var VOLUME_HEIGHT = "volume_height_px";
  var OPEN = "open";
  var HIGH = "high";
  var LOW = "low";
  var CLOSE = "close";
  var VOLUME = "volume";

  var LEFT_MARGIN = "left_margin_px";
  var CHART_WIDTH = "chart_width_px";
  var CHART_RIGHT = "chart_right_px";
  var PANE_WIDTH = "width_px";
  var PANE_HEIGHT = "height_px";
  var CENTRE = "centre_px";
  var OHLC_TOP = "ohlc_top_px";
  var PRICE_TOP = "price_top_px";
  var VOLUME_TOP = "volume_top_px";
  var VOLUME_PANE_HEIGHT = "volume_height_px";
  var TIME_AXIS_TOP = "time_axis_top_px";

  var HEADER_HEIGHT = "header_height_px";
  var HEADER_SYMBOL_X = "header_symbol_x_px";
  var HEADER_ERROR_DROP = "header_error_drop_px";
  var OHLC_ROW_HEIGHT = "ohlc_row_height_px";
  var OHLC_INSET = "ohlc_inset_px";
  var OHLC_LABEL_GAP = "ohlc_label_gap_px";
  var OHLC_VALUE_GAP = "ohlc_value_gap_px";
  var GRID_LINE_WIDTH = "grid_line_width_px";
  var GRID_LINE_STYLE = "grid_line_style";
  var SOLID_LINE_STYLE = "solid_line_style";
  var CANDLE_BORDER_WIDTH = "candle_border_width_px";
  var WICK_WIDTH = "wick_width_px";
  var PRICE_BADGE_RADIUS = "price_badge_radius_px";
  var PRICE_BADGE_HEIGHT = "price_badge_height_px";
  var PRICE_BADGE_LIFT = "price_badge_lift_px";
  var PRICE_BADGE_PAD = "price_badge_pad_px";
  var PRICE_LABEL_INSET = "price_label_inset_px";
  var VOLUME_AXIS_INSET = "volume_axis_inset_px";
  var VOLUME_AXIS_BASELINE = "volume_axis_baseline_px";
  var TIME_LABEL_OFFSET = "time_label_offset_px";
  var TIME_LABEL_BASELINE = "time_label_baseline_px";
  var GRIP_DASH_OFFSETS = "grip_dash_offsets_px";
  var GRIP_DASH_HALF = "grip_dash_half_px";
  var GRIP_LINE_WIDTH = "grip_line_width_px";
  var TRANCHE_LABEL_INSET = "tranche_floor_label_inset_px";
  var POSITION_LABEL_INSET = "position_label_inset_px";
  var TB_BADGE_INSET = "tb_badge_inset_px";
  var KIND_LAST_PRICE = "line_kind_last_price";
  var KIND_TRANCHE_FLOOR = "line_kind_tranche_floor";
  var KIND_POSITION = "line_kind_position";

  var GRID_MAJOR = "grid_major";
  var GRID_MINOR = "grid_minor";
  var TEXT_DIM = "text_dim";
  var TEXT_LIGHT = "text_light";
  var ACCENT = "accent";
  var GRIP_COLOR = "grip_color";
  var HEADER_ERROR_COLOR = "header_error_color";
  var PRICE_BADGE_FILL = "price_badge_fill";
  var PRICE_LINE_COLOR = "price_line_color";

  var MISSING_FAULT = "missing";
  var NULL_FAULT = "null";
  var NOT_AN_OBJECT_FAULT = "not-an-object";
  var NOT_A_LIST_FAULT = "not-a-list";
  var WRONG_TYPE_FAULT = "wrong-type";
  var QT_COLOUR_FAULT = "qt-colour";
  var DISAGREES_FAULT = "disagrees";
  var OUT_OF_ORDER_FAULT = "out-of-order";

  var NO_BRIDGE = "the preload bridge is not present";

  var BODY_AT = "body:";
  var TICK_AT = "tick:";
  var LINE_AT = "line:";
  var CELL_AT = "cell:";
  var PATH_SPLIT = ".";
  var EMPTY = "";
  var GAP = " ";
  var COMMA = ",";
  var HASH = "#";
  var DOT = ".";
  var PERCENT = "%";
  var CLOSE_BRACKET = ")";
  var PX = "px";
  var VAR_OPEN = "var(--";
  var VAR_SPLIT = ", ";
  var VAR_CLOSE = ")";
  var CALC_OPEN = "calc(";
  // The unit factor that turns a unitless token into a CSS length.
  var PX_FACTOR = " * 1px)";

  // FIRST, SECOND and THIRD index the label, value and colour of a row.
  var FIRST = Number(EMPTY);
  var SECOND = Number(true);
  var THIRD = SECOND + SECOND;

  // Qt reads an eight-digit hex colour alpha first; CSS reads it last.
  var HEX_ARGB = "AARRGGBB";
  // Qt counts an rgba alpha in bytes; CSS counts it as a fraction.
  var RGBA_OPEN = "rgba(";

  // A radius borrows a radius token; every other length borrows spacing.
  var RADIUS_SUFFIX = "_radius_px";
  var RADIUS_GROUPS = ["radii"];
  var SPACING_GROUPS = ["spacing", "target_sizes", "focus"];

  var ABSOLUTE = "absolute";
  var RELATIVE = "relative";
  var HIDDEN = "hidden";
  var NONE = "none";
  var PRE = "pre";
  var FLEX = "flex";
  var CENTRE_ALIGN = "center";
  var BORDER_BOX = "border-box";
  var FULL = "100%";
  var ORIGIN = "0px";
  var DIV_TAG = "div";
  var SPAN_TAG = "span";

  var CHART_PART = "chart";
  var HEADER_PART = "header";
  var SYMBOL_PART = "symbol";
  var HEADER_TEXT_PART = "header-text";
  var HEADER_ERROR_PART = "header-error";
  var OHLC_ROW_PART = "ohlc-row";
  var OHLC_CELL_PART = "ohlc-cell";
  var OHLC_LABEL_PART = "ohlc-label";
  var OHLC_VALUE_PART = "ohlc-value";
  var EMPTY_PART = "empty";
  var PRICE_PANE_PART = "price-pane";
  var GRID_LINE_PART = "grid-line";
  var GRID_LABEL_PART = "grid-label";
  var TIME_LINE_PART = "time-line";
  var TIME_LABEL_PART = "time-label";
  var CANDLE_PART = "candle";
  var WICK_PART = "wick";
  var BODY_PART = "body";
  var VOLUME_BAR_PART = "volume-bar";
  var VOLUME_DIVIDER_PART = "volume-divider";
  var VOLUME_LABEL_PART = "volume-label";
  var VOLUME_CHROME_PART = "volume-chrome";
  var PRICE_LINE_PART = "price-line";
  var PRICE_BADGE_PART = "price-badge";
  var PRICE_ROW_PART = "price-row";
  var GRIP_DASH_PART = "grip-dash";
  var MOUNT_PART = "overlay-mount";

  // The mount holds every sloped stroke and every round shape: the
  // indicator polylines, the Ichimoku cloud and the marker icons.
  var MOUNT_LABEL = "chart overlay canvas";

  var PART_ATTR = "data-part";
  var SLOT_ATTR = "data-slot";
  var INDEX_ATTR = "data-index";
  var KIND_ATTR = "data-kind";
  var MAJOR_ATTR = "data-major";
  var UP_ATTR = "data-up";
  var COUNT_ATTR = "data-candle-count";
  var LABEL_ATTR = "aria-label";

  var held = null;
  var chartFaults = [];
  var loadFault = null;
  var asked = null;
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

  function raise(where, name, kind, detail) {
    chartFaults.push(fault(where, name, kind, detail));
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

  function element() {
    return global.React.createElement.apply(null, arguments);
  }

  function dressed(part, props) {
    var found = copyOf(props);
    found[PART_ATTR] = part;
    return found;
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

  // The groups whose meaning matches what the chart calls this value.
  function groupsFor(name) {
    return carries(name, RADIUS_SUFFIX) ? RADIUS_GROUPS : SPACING_GROUPS;
  }

  // The token name for `value`, only from a group meaning the same thing.
  function variableInGroups(value, groups) {
    var name = variableFor(value);
    if (name === undefined || !inGroups(name, groups)) {
      return undefined;
    }
    return name;
  }

  // px writes a worked-out pixel, which is no constant and takes no token.
  function px(value) {
    if (value === null || value === undefined) {
      return undefined;
    }
    return String(value) + PX;
  }

  // A named metric borrows a token when one name carries it and means it.
  function length(name, value) {
    if (value === null || value === undefined) {
      return undefined;
    }
    var token = variableInGroups(value, groupsFor(name));
    if (token === undefined) {
      return px(value);
    }
    return (
      CALC_OPEN + VAR_OPEN + token + VAR_SPLIT + String(value) + VAR_CLOSE + PX_FACTOR
    );
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

  // A colour CSS would read as another colour is refused, not painted.
  function paint(where, name, value) {
    var swapped = qtColour(value);
    if (swapped !== undefined) {
      raise(where, name, QT_COLOUR_FAULT, swapped);
      return undefined;
    }
    return text(value);
  }

  function metric(model, name) {
    return objectField(model, METRICS)[name];
  }

  function skinColour(model, name) {
    return paint(SKIN_CSS, name, objectField(model, SKIN_CSS)[name]);
  }

  function paneValue(model, name) {
    return objectField(model, PANES)[name];
  }

  function gridTicks(model) {
    return listField(objectField(objectField(model, PRICE_AXIS), GRID), TICKS);
  }

  function candleBodies(model) {
    return listField(objectField(model, CANDLES), BODIES);
  }

  function Header(props) {
    var model = props.model;
    var errorText = model[ERROR_TEXT];
    return element(
      DIV_TAG,
      dressed(HEADER_PART, {
        key: HEADER_PART,
        style: {
          position: ABSOLUTE,
          left: ORIGIN,
          top: ORIGIN,
          width: FULL,
          height: px(metric(model, HEADER_HEIGHT)),
          paddingLeft: length(HEADER_SYMBOL_X, metric(model, HEADER_SYMBOL_X)),
          whiteSpace: PRE
        }
      }),
      element(
        SPAN_TAG,
        dressed(SYMBOL_PART, {
          key: SYMBOL_PART,
          style: { color: skinColour(model, ACCENT) }
        }),
        text(model[SYMBOL])
      ),
      element(
        SPAN_TAG,
        dressed(HEADER_TEXT_PART, {
          key: HEADER_TEXT_PART,
          style: { color: skinColour(model, TEXT_DIM) }
        }),
        text(model[HEADER_TEXT])
      ),
      errorText
        ? element(
            SPAN_TAG,
            dressed(HEADER_ERROR_PART, {
              key: HEADER_ERROR_PART,
              style: {
                position: ABSOLUTE,
                left: length(HEADER_SYMBOL_X, metric(model, HEADER_SYMBOL_X)),
                top: px(metric(model, HEADER_ERROR_DROP)),
                color: skinColour(model, HEADER_ERROR_COLOR)
              }
            }),
            text(errorText)
          )
        : null
    );
  }

  function OhlcCell(model, row, at) {
    var label = Array.isArray(row) ? row[FIRST] : undefined;
    var value = Array.isArray(row) ? row[SECOND] : undefined;
    var tone = Array.isArray(row) ? row[THIRD] : undefined;
    return element(
      SPAN_TAG,
      dressed(OHLC_CELL_PART, {
        key: CELL_AT + String(at),
        "data-index": String(at),
        "data-slot": text(label)
      }),
      label
        ? element(
            SPAN_TAG,
            dressed(OHLC_LABEL_PART, {
              key: OHLC_LABEL_PART,
              "data-index": String(at),
              style: {
                color: skinColour(model, TEXT_DIM),
                marginRight: length(OHLC_LABEL_GAP, metric(model, OHLC_LABEL_GAP))
              }
            }),
            text(label)
          )
        : null,
      element(
        SPAN_TAG,
        dressed(OHLC_VALUE_PART, {
          key: OHLC_VALUE_PART,
          "data-index": String(at),
          style: {
            color: paint(CELL_AT + String(at), OHLC_ROW_CSS, tone),
            marginRight: length(OHLC_VALUE_GAP, metric(model, OHLC_VALUE_GAP))
          }
        }),
        text(value)
      )
    );
  }

  function OhlcRow(props) {
    var model = props.model;
    return element(
      DIV_TAG,
      dressed(OHLC_ROW_PART, {
        key: OHLC_ROW_PART,
        style: {
          position: ABSOLUTE,
          left: px(paneValue(model, LEFT_MARGIN)),
          top: px(paneValue(model, OHLC_TOP)),
          height: px(metric(model, OHLC_ROW_HEIGHT)),
          paddingLeft: length(OHLC_INSET, metric(model, OHLC_INSET)),
          whiteSpace: PRE
        }
      }),
      listField(model, OHLC_ROW_CSS).map(function (row, at) {
        return OhlcCell(model, row, at);
      })
    );
  }

  function EmptyView(props) {
    var model = props.model;
    var view = objectField(model, EMPTY_VIEW);
    return element(
      DIV_TAG,
      dressed(EMPTY_PART, {
        key: EMPTY_PART,
        style: {
          position: ABSOLUTE,
          left: ORIGIN,
          top: ORIGIN,
          width: FULL,
          height: FULL,
          display: FLEX,
          alignItems: CENTRE_ALIGN,
          justifyContent: CENTRE_ALIGN,
          color: paint(EMPTY_PART, COLOR_CSS, view[COLOR_CSS])
        }
      }),
      text(view[MESSAGE])
    );
  }

  function GridLines(props) {
    var model = props.model;
    var panes = objectField(model, PANES);
    return gridTicks(model).map(function (tick, at) {
      if (!isPlainObject(tick) || tick[ON_PANE] === false) {
        return null;
      }
      return element(
        DIV_TAG,
        dressed(GRID_LINE_PART, {
          key: TICK_AT + String(at),
          "data-index": String(at),
          "data-major": String(Boolean(tick[MAJOR])),
          style: {
            position: ABSOLUTE,
            left: px(panes[LEFT_MARGIN]),
            top: px(tick[Y_PX]),
            width: px(panes[CHART_WIDTH]),
            borderTopStyle: text(metric(model, GRID_LINE_STYLE)),
            borderTopWidth: length(GRID_LINE_WIDTH, metric(model, GRID_LINE_WIDTH)),
            borderTopColor: paint(TICK_AT + String(at), COLOR_CSS, tick[COLOR_CSS]),
            boxSizing: BORDER_BOX
          }
        })
      );
    });
  }

  function GridLabels(props) {
    var model = props.model;
    var panes = objectField(model, PANES);
    return gridTicks(model).map(function (tick, at) {
      if (!isPlainObject(tick) || tick[ON_PANE] === false) {
        return null;
      }
      return element(
        DIV_TAG,
        dressed(GRID_LABEL_PART, {
          key: TICK_AT + String(at),
          "data-index": String(at),
          style: {
            position: ABSOLUTE,
            left: px(panes[CHART_RIGHT]),
            top: px(tick[Y_PX]),
            paddingLeft: length(PRICE_LABEL_INSET, metric(model, PRICE_LABEL_INSET)),
            color: skinColour(model, TEXT_LIGHT),
            whiteSpace: PRE
          }
        }),
        text(tick[LABEL])
      );
    });
  }

  function TimeLines(props) {
    var model = props.model;
    var panes = objectField(model, PANES);
    return listField(objectField(model, TIME_AXIS), TICKS).map(function (tick, at) {
      if (!isPlainObject(tick) || tick[ON_PANE] === false) {
        return null;
      }
      return element(
        DIV_TAG,
        dressed(TIME_LINE_PART, {
          key: TICK_AT + String(at),
          "data-index": String(at),
          style: {
            position: ABSOLUTE,
            left: px(tick[X_PX]),
            top: px(panes[PRICE_TOP]),
            height: px(panes[TIME_AXIS_TOP] - panes[PRICE_TOP]),
            borderLeftStyle: text(metric(model, GRID_LINE_STYLE)),
            borderLeftWidth: length(GRID_LINE_WIDTH, metric(model, GRID_LINE_WIDTH)),
            borderLeftColor: skinColour(model, GRID_MINOR),
            boxSizing: BORDER_BOX
          }
        })
      );
    });
  }

  function TimeLabels(props) {
    var model = props.model;
    var panes = objectField(model, PANES);
    return listField(objectField(model, TIME_AXIS), TICKS).map(function (tick, at) {
      if (!isPlainObject(tick) || tick[ON_PANE] === false || !tick[LABEL]) {
        return null;
      }
      return element(
        DIV_TAG,
        dressed(TIME_LABEL_PART, {
          key: TICK_AT + String(at),
          "data-index": String(at),
          style: {
            position: ABSOLUTE,
            left: px(tick[X_PX] - metric(model, TIME_LABEL_OFFSET)),
            top: px(panes[TIME_AXIS_TOP]),
            height: px(metric(model, TIME_LABEL_BASELINE)),
            color: skinColour(model, TEXT_LIGHT),
            whiteSpace: PRE
          }
        }),
        text(tick[LABEL])
      );
    });
  }

  function Candle(model, body, at) {
    var colours = objectField(body, COLORS_CSS);
    var where = BODY_AT + String(at);
    return element(
      DIV_TAG,
      dressed(CANDLE_PART, {
        key: BODY_AT + String(at),
        "data-index": String(at),
        "data-up": String(Boolean(body[UP]))
      }),
      element(
        DIV_TAG,
        dressed(WICK_PART, {
          key: WICK_PART,
          "data-index": String(at),
          style: {
            position: ABSOLUTE,
            left: px(body[WICK_X]),
            top: px(body[WICK_Y]),
            width: length(WICK_WIDTH, metric(model, WICK_WIDTH)),
            height: px(body[WICK_HEIGHT]),
            backgroundColor: paint(where, WICK, colours[WICK])
          }
        })
      ),
      element(
        DIV_TAG,
        dressed(BODY_PART, {
          key: BODY_PART,
          "data-index": String(at),
          style: {
            position: ABSOLUTE,
            left: px(body[BODY_X]),
            top: px(body[BODY_Y]),
            width: px(body[BODY_WIDTH]),
            height: px(body[BODY_HEIGHT]),
            backgroundColor: paint(where, FILL, colours[FILL]),
            borderStyle: text(metric(model, SOLID_LINE_STYLE)),
            borderWidth: length(
              CANDLE_BORDER_WIDTH,
              metric(model, CANDLE_BORDER_WIDTH)
            ),
            borderColor: paint(where, BORDER, colours[BORDER]),
            boxSizing: BORDER_BOX
          }
        })
      )
    );
  }

  function Candles(props) {
    var model = props.model;
    return candleBodies(model).map(function (body, at) {
      return isPlainObject(body) ? Candle(model, body, at) : null;
    });
  }

  function VolumeBars(props) {
    var model = props.model;
    if (!paneValue(model, VOLUME_PANE_HEIGHT)) {
      return null;
    }
    return candleBodies(model).map(function (body, at) {
      if (!isPlainObject(body) || !body[VOLUME_HEIGHT]) {
        return null;
      }
      var colours = objectField(body, VOLUME_COLORS_CSS);
      var where = BODY_AT + String(at);
      return element(
        DIV_TAG,
        dressed(VOLUME_BAR_PART, {
          key: BODY_AT + String(at),
          "data-index": String(at),
          "data-up": String(Boolean(body[UP])),
          style: {
            position: ABSOLUTE,
            left: px(body[BODY_X]),
            top: px(body[VOLUME_Y]),
            width: px(body[BODY_WIDTH]),
            height: px(body[VOLUME_HEIGHT]),
            backgroundColor: paint(where, FILL, colours[FILL]),
            borderStyle: text(metric(model, SOLID_LINE_STYLE)),
            borderWidth: length(
              CANDLE_BORDER_WIDTH,
              metric(model, CANDLE_BORDER_WIDTH)
            ),
            borderColor: paint(where, BORDER, colours[BORDER]),
            boxSizing: BORDER_BOX
          }
        })
      );
    });
  }

  function VolumeChrome(props) {
    var model = props.model;
    var panes = objectField(model, PANES);
    if (!panes[VOLUME_PANE_HEIGHT]) {
      return null;
    }
    var shown = objectField(model, CANDLES);
    return element(
      DIV_TAG,
      dressed(VOLUME_CHROME_PART, { key: VOLUME_CHROME_PART }),
      element(
        DIV_TAG,
        dressed(VOLUME_DIVIDER_PART, {
          key: VOLUME_DIVIDER_PART,
          style: {
            position: ABSOLUTE,
            left: px(panes[LEFT_MARGIN]),
            top: px(panes[VOLUME_TOP]),
            width: px(panes[CHART_WIDTH]),
            borderTopStyle: text(metric(model, SOLID_LINE_STYLE)),
            borderTopWidth: length(GRID_LINE_WIDTH, metric(model, GRID_LINE_WIDTH)),
            borderTopColor: skinColour(model, GRID_MAJOR),
            boxSizing: BORDER_BOX
          }
        })
      ),
      shown[MAX_VOLUME]
        ? element(
            DIV_TAG,
            dressed(VOLUME_LABEL_PART, {
              key: VOLUME_LABEL_PART,
              style: {
                position: ABSOLUTE,
                left: px(panes[CHART_RIGHT]),
                top: px(panes[VOLUME_TOP]),
                paddingLeft: length(
                  VOLUME_AXIS_INSET,
                  metric(model, VOLUME_AXIS_INSET)
                ),
                height: px(metric(model, VOLUME_AXIS_BASELINE)),
                color: skinColour(model, TEXT_DIM),
                whiteSpace: PRE
              }
            }),
            text(shown[VOLUME_AXIS_LABEL])
          )
        : null
    );
  }

  function labelInset(model, kind) {
    if (kind === metric(model, KIND_TRANCHE_FLOOR)) {
      return length(TRANCHE_LABEL_INSET, metric(model, TRANCHE_LABEL_INSET));
    }
    if (kind === metric(model, KIND_POSITION)) {
      return length(POSITION_LABEL_INSET, metric(model, POSITION_LABEL_INSET));
    }
    return length(TB_BADGE_INSET, metric(model, TB_BADGE_INSET));
  }

  // The last price wears the right-edge badge; every other line wears a
  // left-edge label.
  function badgeStyle(model, row) {
    var panes = objectField(model, PANES);
    var found = {
      position: ABSOLUTE,
      top: px(row[Y_PX] - metric(model, PRICE_BADGE_LIFT)),
      whiteSpace: PRE
    };
    if (row[KIND] === metric(model, KIND_LAST_PRICE)) {
      found.left = px(panes[CHART_RIGHT]);
      found.paddingLeft = length(PRICE_BADGE_PAD, metric(model, PRICE_BADGE_PAD));
      found.paddingRight = found.paddingLeft;
      found.height = px(metric(model, PRICE_BADGE_HEIGHT));
      found.backgroundColor = skinColour(model, PRICE_BADGE_FILL);
      found.borderRadius = length(
        PRICE_BADGE_RADIUS,
        metric(model, PRICE_BADGE_RADIUS)
      );
      found.color = skinColour(model, PRICE_LINE_COLOR);
      return found;
    }
    found.left = px(panes[LEFT_MARGIN]);
    found.paddingLeft = labelInset(model, row[KIND]);
    found.color = paint(
      row[KIND],
      LABEL_COLOR_CSS,
      owns(row, LABEL_COLOR_CSS) ? row[LABEL_COLOR_CSS] : row[COLOR_CSS]
    );
    return found;
  }

  function PriceLines(props) {
    var model = props.model;
    var panes = objectField(model, PANES);
    return listField(model, PRICE_LINES).map(function (row, at) {
      if (!isPlainObject(row) || row[ON_PANE] === false) {
        return null;
      }
      return element(
        DIV_TAG,
        dressed(PRICE_ROW_PART, {
          key: LINE_AT + String(at),
          "data-index": String(at),
          "data-kind": text(row[KIND])
        }),
        element(
          DIV_TAG,
          dressed(PRICE_LINE_PART, {
            key: PRICE_LINE_PART,
            "data-index": String(at),
            "data-kind": text(row[KIND]),
            style: {
              position: ABSOLUTE,
              left: px(panes[LEFT_MARGIN]),
              top: px(row[Y_PX]),
              width: px(panes[CHART_WIDTH]),
              borderTopStyle: text(row[STYLE]),
              borderTopWidth: px(row[WIDTH_FIELD]),
              borderTopColor: paint(LINE_AT + String(at), COLOR_CSS, row[COLOR_CSS]),
              boxSizing: BORDER_BOX
            }
          })
        ),
        element(
          DIV_TAG,
          dressed(PRICE_BADGE_PART, {
            key: PRICE_BADGE_PART,
            "data-index": String(at),
            "data-kind": text(row[KIND]),
            style: badgeStyle(model, row)
          }),
          text(row[LABEL])
        )
      );
    });
  }

  function GripDashes(props) {
    var model = props.model;
    var panes = objectField(model, PANES);
    var half = metric(model, GRIP_DASH_HALF);
    var offsets = metric(model, GRIP_DASH_OFFSETS);
    if (!Array.isArray(offsets)) {
      return null;
    }
    return offsets.map(function (offset, at) {
      return element(
        DIV_TAG,
        dressed(GRIP_DASH_PART, {
          key: TICK_AT + String(at),
          "data-index": String(at),
          style: {
            position: ABSOLUTE,
            left: px(panes[CENTRE] + offset - half),
            top: px(panes[PANE_HEIGHT] - model[RESIZE_GRIP]),
            width: px(half + half),
            borderTopStyle: text(metric(model, SOLID_LINE_STYLE)),
            borderTopWidth: px(metric(model, GRIP_LINE_WIDTH)),
            borderTopColor: skinColour(model, GRIP_COLOR),
            boxSizing: BORDER_BOX
          }
        })
      );
    });
  }

  function Mount(props) {
    var model = props.model;
    var panes = objectField(model, PANES);
    return element(
      DIV_TAG,
      dressed(MOUNT_PART, {
        key: MOUNT_PART,
        "aria-label": MOUNT_LABEL,
        style: {
          position: ABSOLUTE,
          left: px(panes[LEFT_MARGIN]),
          top: px(panes[PRICE_TOP]),
          width: px(panes[CHART_WIDTH]),
          height: px(panes[TIME_AXIS_TOP] - panes[PRICE_TOP]),
          pointerEvents: NONE
        }
      })
    );
  }

  function PricePane(props) {
    var model = props.model;
    return element(
      DIV_TAG,
      dressed(PRICE_PANE_PART, {
        key: PRICE_PANE_PART,
        style: {
          position: ABSOLUTE,
          left: ORIGIN,
          top: ORIGIN,
          width: FULL,
          height: FULL
        }
      }),
      GridLines({ model: model }),
      GridLabels({ model: model }),
      TimeLines({ model: model }),
      Candles({ model: model }),
      VolumeBars({ model: model }),
      VolumeChrome({ model: model }),
      PriceLines({ model: model }),
      TimeLabels({ model: model }),
      GripDashes({ model: model }),
      Mount({ model: model })
    );
  }

  function Chart(props) {
    var model = isPlainObject(props.model) ? props.model : {};
    var panes = objectField(model, PANES);
    return element(
      DIV_TAG,
      dressed(CHART_PART, {
        "aria-label": text(model[ACCESSIBLE_NAME]),
        "data-candle-count": text(model[CANDLE_COUNT]),
        style: {
          position: RELATIVE,
          width: px(panes[PANE_WIDTH]),
          height: px(panes[PANE_HEIGHT]),
          minHeight: px(model[MINIMUM_HEIGHT]),
          background: text(model[BACKGROUND_CSS]),
          overflow: HIDDEN
        }
      }),
      Header({ model: model }),
      Array.isArray(model[OHLC_ROW_CSS]) ? OhlcRow({ model: model }) : null,
      isPlainObject(model[EMPTY_VIEW]) ? EmptyView({ model: model }) : null,
      isPlainObject(model[PANES]) ? PricePane({ model: model }) : null
    );
  }

  function checkFields(model) {
    var optional = {};
    STATE_FIELDS.forEach(function (name) {
      optional[name] = true;
    });
    DECLARED_FIELDS.forEach(function (name) {
      if (!owns(model, name)) {
        raise(null, name, MISSING_FAULT, null);
        return;
      }
      if (model[name] === null && !owns(optional, name)) {
        raise(null, name, NULL_FAULT, null);
      }
    });
  }

  function checkShapes(model) {
    BAG_FIELDS.forEach(function (name) {
      if (owns(model, name) && !isPlainObject(model[name])) {
        raise(null, name, NOT_AN_OBJECT_FAULT, kindOf(model[name]));
      }
    });
    LIST_FIELDS.forEach(function (name) {
      if (owns(model, name) && !Array.isArray(model[name])) {
        raise(null, name, NOT_A_LIST_FAULT, kindOf(model[name]));
      }
    });
  }

  // HELD_TWICE names each value the surface publishes twice, so one copy
  // holds the type and value of the other.
  var HELD_TWICE = [RESIZE_GRIP, PARENT_HEIGHT_PAD];

  function checkHeldTwice(model) {
    var published = objectField(model, METRICS);
    HELD_TWICE.forEach(function (name) {
      if (!owns(model, name) || !owns(published, name)) {
        return;
      }
      if (kindOf(model[name]) !== kindOf(published[name])) {
        raise(METRICS, name, WRONG_TYPE_FAULT, kindOf(model[name]));
        return;
      }
      if (model[name] !== published[name]) {
        raise(METRICS, name, DISAGREES_FAULT, model[name]);
      }
    });
  }

  function checkSkinColours(model) {
    var css = objectField(model, SKIN_CSS);
    Object.keys(css).forEach(function (name) {
      if (typeof css[name] !== "string") {
        raise(SKIN_CSS, name, WRONG_TYPE_FAULT, kindOf(css[name]));
        return;
      }
      var swapped = qtColour(css[name]);
      if (swapped !== undefined) {
        raise(SKIN_CSS, name, QT_COLOUR_FAULT, swapped);
      }
    });
    var ground = qtColour(model[BACKGROUND_CSS]);
    if (owns(model, BACKGROUND_CSS) && ground !== undefined) {
      raise(null, BACKGROUND_CSS, QT_COLOUR_FAULT, ground);
    }
  }

  function checkBars(model) {
    candleBodies(model).forEach(function (body, at) {
      if (!isPlainObject(body)) {
        raise(BODY_AT + String(at), BODIES, NOT_AN_OBJECT_FAULT, kindOf(body));
        return;
      }
      if (body[INDEX] !== at) {
        raise(BODY_AT + String(at), INDEX, OUT_OF_ORDER_FAULT, body[INDEX]);
      }
    });
  }

  function checkAxis(model) {
    gridTicks(model).forEach(function (tick, at) {
      if (!isPlainObject(tick)) {
        raise(TICK_AT + String(at), TICKS, NOT_AN_OBJECT_FAULT, kindOf(tick));
        return;
      }
      if (typeof tick[Y_PX] !== "number") {
        raise(TICK_AT + String(at), Y_PX, WRONG_TYPE_FAULT, kindOf(tick[Y_PX]));
      }
    });
    listField(model, PRICE_LINES).forEach(function (row, at) {
      if (!isPlainObject(row)) {
        raise(LINE_AT + String(at), PRICE_LINES, NOT_AN_OBJECT_FAULT, kindOf(row));
        return;
      }
      var swapped = qtColour(row[COLOR_CSS]);
      if (swapped !== undefined) {
        raise(LINE_AT + String(at), COLOR_CSS, QT_COLOUR_FAULT, swapped);
      }
    });
  }

  function heldFieldCount() {
    return DECLARED_FIELDS.filter(function (name) {
      return held !== null && owns(held.model, name);
    }).length;
  }

  function report() {
    var model = held.model;
    return {
      declared: {
        fields: DECLARED_FIELDS.length,
        bars: model[CANDLE_COUNT],
        ticks: gridTicks(model).length,
        lines: listField(model, PRICE_LINES).length
      },
      held: {
        fields: heldFieldCount(),
        bars: candleBodies(model).length,
        ticks: gridTicks(model).length,
        lines: listField(model, PRICE_LINES).length
      },
      faults: chartFaults.slice()
    };
  }

  function setChart(model) {
    if (!isPlainObject(model)) {
      held = null;
      chartFaults = [fault(null, null, NOT_AN_OBJECT_FAULT, kindOf(model))];
      return { declared: null, held: null, faults: chartFaults.slice() };
    }
    held = { model: model };
    chartFaults = [];
    checkFields(model);
    checkShapes(model);
    checkHeldTwice(model);
    checkSkinColours(model);
    checkBars(model);
    checkAxis(model);
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

  function stateNames() {
    return STATE_FIELDS.slice();
  }

  function panes() {
    return bag(PANES);
  }

  function priceAxis() {
    return bag(PRICE_AXIS);
  }

  function candles() {
    return bag(CANDLES);
  }

  function timeAxis() {
    return bag(TIME_AXIS);
  }

  function bodies() {
    return held === null ? [] : candleBodies(held.model).slice();
  }

  function priceLines() {
    return list(PRICE_LINES);
  }

  function skinCss() {
    return bag(SKIN_CSS);
  }

  function metrics() {
    return bag(METRICS);
  }

  function actions() {
    return bag(ACTIONS);
  }

  // Where each bar sits, so a reordered series shows as a moved index.
  function barOrder() {
    return bodies().map(function (one) {
      return isPlainObject(one) ? one[INDEX] : null;
    });
  }

  // What each bar carries, so two swapped bars show as changed values.
  function barIdentity() {
    return bodies().map(function (one, at) {
      if (!isPlainObject(one)) {
        return [at, null, null, null, null, null, null];
      }
      return [at, one[INDEX], one[OPEN], one[HIGH], one[LOW], one[CLOSE], one[VOLUME]];
    });
  }

  // kinds reports the JavaScript type of every value, by dotted path.
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

  function renderChart(target, model) {
    var payload = model;
    if (!isPlainObject(payload)) {
      payload = held === null ? null : held.model;
    }
    return draw(target, element(Chart, { model: payload }));
  }

  function forget() {
    held = null;
    chartFaults = [];
    loadFault = null;
    asked = null;
  }

  // The chart belongs to the Charts tab, so it names no bridge method and
  // takes no tab of its own.
  if (global.acervatorPanelHost) {
    global.acervatorPanelHost.register({
      render: renderChart,
      load: loadChart,
      loadError: loadError
    });
  }

  global.acervatorSetChart = setChart;
  global.acervatorLoadChart = loadChart;
  global.acervatorChart = {
    method: METHOD,
    Chart: Chart,
    Header: Header,
    OhlcRow: OhlcRow,
    EmptyView: EmptyView,
    PricePane: PricePane,
    Candles: Candles,
    PriceLines: PriceLines,
    Mount: Mount,
    mountLabel: MOUNT_LABEL,
    field: field,
    declaredNames: declaredNames,
    stateNames: stateNames,
    panes: panes,
    priceAxis: priceAxis,
    candles: candles,
    timeAxis: timeAxis,
    bodies: bodies,
    priceLines: priceLines,
    skinCss: skinCss,
    metrics: metrics,
    actions: actions,
    barOrder: barOrder,
    barIdentity: barIdentity,
    qtColour: qtColour,
    variableFor: variableFor,
    variableInGroups: variableInGroups,
    groupsFor: groupsFor,
    length: length,
    px: px,
    kinds: kinds,
    faults: faults,
    loadError: loadError,
    isLoaded: isLoaded,
    renderChart: renderChart,
    forget: forget
  };
})(window);
