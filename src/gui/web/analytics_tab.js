// The performance analytics dashboard, as the Python surface serves it.
(function (global) {
  "use strict";

  var METHOD = "analytics.tab";

  var ACCESSIBLE_NAME = "accessible_name";
  var PAGE = "page";
  var CARDS = "cards";
  var CARD_ORDER = "card_order";
  var CARD_LABELS = "card_labels";
  var CARD_SKIN = "card_skin";
  var MAIN_SPLITTER = "main_splitter";
  var BOTTOM_SPLITTER = "bottom_splitter";
  var GROUPS = "groups";
  var GROUP_ORDER = "group_order";
  var BOT_TABLE = "bot_table";
  var TIMEFRAME_TABLE = "timeframe_table";
  var BOT_COLUMNS = "bot_columns";
  var TIMEFRAME_COLUMNS = "timeframe_columns";
  var BOT_FIELDS = "bot_fields";
  var TIMEFRAME_FIELDS = "timeframe_fields";
  var BOT_ROWS = "bot_rows";
  var TIMEFRAME_ROWS = "timeframe_rows";
  var CHART = "chart";
  var CHART_SKIN = "chart_skin";
  var EQUITY_CURVE_HOURS = "equity_curve_hours";
  var SUMMARY_DEFAULTS = "summary_defaults";
  var NUMBER_FORMATS = "number_formats";
  var COLORS = "colors";
  var ACTIONS = "actions";
  var TIMERS = "timers";
  var TIMER_DELAYS_MS = "timer_delays_ms";
  var SKIN = "skin";

  var DECLARED_FIELDS = [
    ACCESSIBLE_NAME,
    ACTIONS,
    BOTTOM_SPLITTER,
    BOT_COLUMNS,
    BOT_FIELDS,
    BOT_ROWS,
    BOT_TABLE,
    CARDS,
    CARD_LABELS,
    CARD_ORDER,
    CARD_SKIN,
    CHART,
    CHART_SKIN,
    COLORS,
    EQUITY_CURVE_HOURS,
    GROUPS,
    GROUP_ORDER,
    MAIN_SPLITTER,
    NUMBER_FORMATS,
    PAGE,
    SKIN,
    SUMMARY_DEFAULTS,
    TIMEFRAME_COLUMNS,
    TIMEFRAME_FIELDS,
    TIMEFRAME_ROWS,
    TIMEFRAME_TABLE,
    TIMERS,
    TIMER_DELAYS_MS
  ];

  var KEY = "key";
  var LABEL = "label";
  var VALUE = "value";
  var COLOR = "color";
  var CLASS_NAME = "class_name";
  var CARD_ACCESSIBLE_NAME = "accessible_name";
  var FRAME_STYLE = "frame_style";
  var LABEL_STYLE = "label_style";
  var VALUE_STYLE = "value_style";

  // One metric card's fields, in the order the surface writes them.
  var CARD_FIELDS = [
    KEY,
    LABEL,
    VALUE,
    COLOR,
    CLASS_NAME,
    CARD_ACCESSIBLE_NAME,
    FRAME_STYLE,
    LABEL_STYLE,
    VALUE_STYLE
  ];

  var TEXT = "text";
  var ALIGN = "align";

  var TITLE = "title";
  var STYLE = "style";
  var CHILD = "child";

  var MARGINS_PX = "margins_px";
  var SPACING_PX = "spacing_px";
  var PADDING_PX = "padding_px";
  var RADIUS_PX = "radius_px";
  var SURFACE = "surface";
  var BORDER = "border";
  var LABEL_COLOR = "label_color";
  var VALUE_COLOR = "value_color";
  var LABEL_SIZE_PX = "label_size_px";
  var VALUE_SIZE_PX = "value_size_px";

  var ORIENTATION = "orientation";
  var VERTICAL = "vertical";
  var HANDLE_WIDTH_PX = "handle_width_px";
  var SIZES_PX = "sizes_px";
  var CHILDREN = "children";

  var COLUMN_COUNT = "column_count";
  var COLUMNS = "columns";
  var ALTERNATING_ROW_COLORS = "alternating_row_colors";
  var VERTICAL_HEADER_VISIBLE = "vertical_header_visible";
  var COLORED_COLUMN = "colored_column";
  var CELL_ALIGNMENT = "cell_alignment";
  var EDIT_TRIGGERS = "edit_triggers";
  var SELECTION_BEHAVIOR = "selection_behavior";

  var EMPTY_CHART = "empty";
  var WIDTH_PX = "width_px";
  var HEIGHT_PX = "height_px";
  var BACKGROUND = "background";
  var ANTIALIASED = "antialiased";
  var TEXT_COLOR = "text_color";
  var RECT_PX = "rect_px";
  var GRID_LINES_PX = "grid_lines_px";
  var GRID_COLOR = "grid_color";
  var GRID_WIDTH_PX = "grid_width_px";
  var POLYGON_PX = "polygon_px";
  var SEGMENTS_PX = "segments_px";
  var GRADIENT = "gradient";
  var LINE_COLOR = "line_color";
  var LINE_WIDTH_PX = "line_width_px";
  var LABELS = "labels";
  var START_PX = "start_px";
  var END_PX = "end_px";
  var STOPS = "stops";
  var X_PX = "x_px";
  var Y_PX = "y_px";
  var FONT_FAMILY = "font_family";
  var FONT_POINT_SIZE = "font_point_size";
  var MIN_HEIGHT_PX = "min_height_px";
  var RISE_FILL = "rise_fill";
  var FALL_FILL = "fall_fill";

  var MISSING_FAULT = "missing";
  var NULL_FAULT = "null";
  var NOT_AN_OBJECT_FAULT = "not-an-object";
  var WRONG_TYPE_FAULT = "wrong-type";
  var NOT_CSS_FAULT = "not-css";
  var SHORT_LIST_FAULT = "short-list";
  var UNNAMED_FAULT = "unnamed";
  var BYTE_ALPHA_FAULT = "byte-alpha";

  var NO_BRIDGE = "the preload bridge is not present";

  var CARD_AT = "card:";
  var BOT_ROW_AT = "bot-row:";
  var TIMEFRAME_ROW_AT = "timeframe-row:";
  var PATH_SPLIT = ".";
  var SEMICOLON = ";";
  var COLON = ":";
  var EMPTY = "";

  var TAB_CLASS = "acervator-analytics-tab";
  var METRICS_CLASS = "acervator-analytics-metrics";
  var CARD_CLASS = "acervator-analytics-card";
  var GROUP_CLASS = "acervator-analytics-group";
  var TITLE_CLASS = "acervator-analytics-title";
  var TABLE_CLASS = "acervator-analytics-table";
  var CHART_CLASS = "acervator-analytics-chart";
  var SPLIT_CLASS = "acervator-analytics-split";

  var TAB_PART = "tab";
  var METRICS_PART = "metrics-row";
  var CARD_PART = "card";
  var CARD_LABEL_PART = "card-label";
  var CARD_VALUE_PART = "card-value";
  var SPLIT_PART = "split";
  var GROUP_PART = "group";
  var TITLE_PART = "group-title";
  var TABLE_PART = "table";
  var HEAD_PART = "head-cell";
  var ROW_PART = "row";
  var CELL_PART = "cell";
  var CHART_PART = "chart";
  var CHART_GROUND_PART = "chart-ground";
  var CHART_GRID_PART = "chart-grid";
  var CHART_FILL_PART = "chart-fill";
  var CHART_LINE_PART = "chart-line";
  var CHART_LABEL_PART = "chart-label";
  var CHART_EMPTY_PART = "chart-empty";

  var PART_ATTR = "data-part";
  var KEY_ATTR = "data-key";
  var AT_ATTR = "data-at";
  var COLUMN_ATTR = "data-column";
  var ROW_ATTR = "data-row";
  var COLORED_ATTR = "data-colored";
  var ALTERNATING_ATTR = "data-alternating";
  var VERTICAL_HEADER_ATTR = "data-vertical-header";
  var DECLARED_COLUMNS_ATTR = "data-declared-columns";
  var HELD_COLUMNS_ATTR = "data-held-columns";
  var DECLARED_CARDS_ATTR = "data-declared-cards";
  var HELD_CARDS_ATTR = "data-held-cards";
  var ORIENTATION_ATTR = "data-orientation";
  var EMPTY_ATTR = "data-empty";
  var ANTIALIASED_ATTR = "data-antialiased";
  var ARIA_LABEL = "aria-label";

  var DIV = "div";
  var SPAN = "span";
  var SECTION = "section";
  var TABLE = "table";
  var HEAD = "thead";
  var BODY = "tbody";
  var TABLE_ROW = "tr";
  var HEAD_CELL = "th";
  var CELL = "td";
  var SVG = "svg";
  var DEFS = "defs";
  var LINEAR_GRADIENT = "linearGradient";
  var STOP = "stop";
  var RECT = "rect";
  var LINE = "line";
  var POLYGON = "polygon";
  var SVG_TEXT = "text";
  var GROUP_ROLE = "group";

  var FLEX = "flex";
  var ROW_DIRECTION = "row";
  var COLUMN_DIRECTION = "column";
  var PX = "px";
  var PERCENT = "%";
  var ZERO = 0;
  var ONE = 1;
  var BOLD = "bold";
  var CENTRE = "center";
  var MIDDLE = "middle";
  var NONE = "none";
  var GRADIENT_ID = "acervator-analytics-fill";
  var URL_OPEN = "url(#";
  var URL_CLOSE = ")";
  var RGBA_OPEN = "rgba(";
  var RGBA_CLOSE = ")";
  var COMMA_SPACE = ", ";
  var SPACE = " ";
  var POINT_TO_PX = 4 / 3;
  var ALPHA_HIGHEST_SHARE = 1;
  var COLOUR_CHANNELS = 4;
  var ALPHA_AT = 3;

  // The surface publishes a margin in left, top, right, bottom order.
  var PADDING_SIDES = [
    "paddingLeft",
    "paddingTop",
    "paddingRight",
    "paddingBottom"
  ];

  var held = null;
  var analyticsFaults = [];
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
    Object.keys(bag).forEach(function (name) {
      found[name] = bag[name];
    });
    return found;
  }

  function holds(items, value) {
    return items.some(function (one) {
      return one === value;
    });
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

  // label returns undefined for an empty name, so the attribute stays off.
  function label(value) {
    return typeof value === "string" && value.length ? value : undefined;
  }

  function pixels(value) {
    return value === null || value === undefined ? undefined : String(value) + PX;
  }

  // A Qt point size is three quarters of a CSS pixel size.
  function fontPixels(points) {
    return typeof points === "number" ? pixels(points * POINT_TO_PX) : undefined;
  }

  function marginStyle(bag, name) {
    var style = {};
    var margins = listField(bag, name);
    PADDING_SIDES.forEach(function (side, at) {
      if (at < margins.length) {
        style[side] = pixels(margins[at]);
      }
    });
    return style;
  }

  // sheetApi answers null when acervatorHeader is absent, so styleOf paints nothing.
  function sheetApi() {
    var api = global.acervatorHeader;
    var usable =
      api &&
      typeof api.styleOf === "function" &&
      typeof api.declarations === "function";
    return usable ? api : null;
  }

  function styleOf(sheet) {
    var api = sheetApi();
    return api === null ? {} : api.styleOf(sheet);
  }

  function declarations(sheet) {
    var api = sheetApi();
    return api === null ? [] : api.declarations(sheet);
  }

  // variableFor asks acervatorWidgets, which names the single token carrying a value.
  function variableFor(value) {
    var api = global.acervatorWidgets;
    if (!api || typeof api.variableFor !== "function") {
      return undefined;
    }
    return api.variableFor(value);
  }

  // Every property of one sheet that styleOf paints nothing from.
  function unpaintable(sheet) {
    var found = [];
    declarations(sheet).forEach(function (one) {
      var alone = one.property + COLON + one.value + SEMICOLON;
      if (!Object.keys(styleOf(alone)).length) {
        found.push(one.property);
      }
    });
    return found;
  }

  // The surface converts Qt's alpha byte before it publishes, so the
  // fourth field arrives as the share CSS reads and is written straight.
  function rgba(channels) {
    var values = Array.isArray(channels) ? channels : [];
    if (values.length < COLOUR_CHANNELS) {
      return undefined;
    }
    return (
      RGBA_OPEN +
      values.slice(ZERO, ALPHA_AT).join(COMMA_SPACE) +
      COMMA_SPACE +
      String(values[ALPHA_AT]) +
      RGBA_CLOSE
    );
  }

  // A colour whose alpha is above one is Qt's byte, which CSS paints opaque.
  function byteAlpha(channels) {
    return (
      Array.isArray(channels) &&
      channels.length >= COLOUR_CHANNELS &&
      typeof channels[ALPHA_AT] === "number" &&
      channels[ALPHA_AT] > ALPHA_HIGHEST_SHARE
    );
  }

  function cardObject(one) {
    var found = {};
    CARD_FIELDS.forEach(function (name) {
      found[name] = isPlainObject(one) ? one[name] : undefined;
    });
    return found;
  }

  function cardList(model) {
    return listField(model, CARDS).filter(isPlainObject);
  }

  function rowsOf(model, field) {
    return listField(model, field).filter(function (one) {
      return Array.isArray(one);
    });
  }

  function publishedLabels(model) {
    var named = objectField(model, CARD_LABELS);
    return Object.keys(named).map(function (name) {
      return named[name];
    });
  }

  function checkFields(model) {
    DECLARED_FIELDS.forEach(function (field) {
      if (!owns(model, field)) {
        analyticsFaults.push(fault(null, field, MISSING_FAULT, null));
        return;
      }
      if (model[field] === null) {
        analyticsFaults.push(fault(null, field, NULL_FAULT, null));
      }
    });
  }

  function checkCards(model) {
    var order = listField(model, CARD_ORDER);
    var named = publishedLabels(model);
    listField(model, CARDS).forEach(function (one, at) {
      var where = CARD_AT + String(at);
      if (!isPlainObject(one)) {
        analyticsFaults.push(fault(where, CARDS, WRONG_TYPE_FAULT, kindOf(one)));
        return;
      }
      var card = cardObject(one);
      CARD_FIELDS.forEach(function (name) {
        if (card[name] === undefined) {
          analyticsFaults.push(fault(where, name, MISSING_FAULT, null));
          return;
        }
        if (typeof card[name] !== "string") {
          analyticsFaults.push(
            fault(where, name, WRONG_TYPE_FAULT, kindOf(card[name]))
          );
        }
      });
      if (!holds(named, card[LABEL])) {
        analyticsFaults.push(fault(where, LABEL, UNNAMED_FAULT, text(card[LABEL])));
      }
      if (order.length && card[KEY] !== order[at]) {
        analyticsFaults.push(fault(where, KEY, UNNAMED_FAULT, text(card[KEY])));
      }
      [FRAME_STYLE, LABEL_STYLE, VALUE_STYLE].forEach(function (name) {
        unpaintable(card[name]).forEach(function (property) {
          analyticsFaults.push(fault(where, name, NOT_CSS_FAULT, property));
        });
      });
    });
  }

  function checkRows(model, rowsField, tableField, where) {
    var declared = objectField(model, tableField)[COLUMN_COUNT];
    listField(model, rowsField).forEach(function (one, at) {
      var at_where = where + String(at);
      if (!Array.isArray(one)) {
        analyticsFaults.push(
          fault(at_where, rowsField, WRONG_TYPE_FAULT, kindOf(one))
        );
        return;
      }
      if (typeof declared === "number" && one.length !== declared) {
        analyticsFaults.push(
          fault(at_where, COLUMN_COUNT, SHORT_LIST_FAULT, one.length)
        );
      }
      one.forEach(function (item) {
        if (!isPlainObject(item) || typeof item[TEXT] !== "string") {
          analyticsFaults.push(fault(at_where, TEXT, WRONG_TYPE_FAULT, kindOf(item)));
        }
      });
    });
  }

  function checkColumns(model, tableField, columnsField) {
    var table = objectField(model, tableField);
    var columns = listField(model, columnsField);
    if (typeof table[COLUMN_COUNT] === "number" && table[COLUMN_COUNT] !== columns.length) {
      analyticsFaults.push(
        fault(tableField, COLUMN_COUNT, SHORT_LIST_FAULT, columns.length)
      );
    }
  }

  // Every published colour whose alpha is still Qt's byte, which CSS clamps.
  function checkAlpha(model) {
    var chart = objectField(model, CHART);
    var skin = objectField(model, CHART_SKIN);
    listField(objectField(chart, GRADIENT), STOPS).forEach(function (one, at) {
      var channels = Array.isArray(one) ? one[ONE] : null;
      if (byteAlpha(channels)) {
        analyticsFaults.push(
          fault(CHART, STOPS, BYTE_ALPHA_FAULT, channels[ALPHA_AT])
        );
      }
      if (Array.isArray(one) && typeof one[ZERO] !== "number") {
        analyticsFaults.push(fault(CHART, STOPS, WRONG_TYPE_FAULT, at));
      }
    });
    [RISE_FILL, FALL_FILL].forEach(function (name) {
      listField(skin, name).forEach(function (one) {
        if (byteAlpha(one)) {
          analyticsFaults.push(
            fault(CHART_SKIN, name, BYTE_ALPHA_FAULT, one[ALPHA_AT])
          );
        }
      });
    });
  }

  function heldFieldCount() {
    return DECLARED_FIELDS.filter(function (field) {
      return held !== null && owns(held.model, field);
    }).length;
  }

  function heldCellTotal(model) {
    var cells = ZERO;
    rowsOf(model, BOT_ROWS).forEach(function (one) {
      cells += one.length;
    });
    rowsOf(model, TIMEFRAME_ROWS).forEach(function (one) {
      cells += one.length;
    });
    return cells;
  }

  function report() {
    var model = held.model;
    var bots = listField(model, BOT_ROWS);
    var frames = listField(model, TIMEFRAME_ROWS);
    return {
      declared: {
        fields: DECLARED_FIELDS.length,
        cards: listField(model, CARD_ORDER).length,
        bot_columns: objectField(model, BOT_TABLE)[COLUMN_COUNT],
        timeframe_columns: objectField(model, TIMEFRAME_TABLE)[COLUMN_COUNT],
        rows: bots.length + frames.length
      },
      held: {
        fields: heldFieldCount(),
        cards: listField(model, CARDS).length,
        bot_columns: listField(model, BOT_COLUMNS).length,
        timeframe_columns: listField(model, TIMEFRAME_COLUMNS).length,
        rows: rowsOf(model, BOT_ROWS).length + rowsOf(model, TIMEFRAME_ROWS).length,
        cells: heldCellTotal(model)
      },
      faults: analyticsFaults.slice()
    };
  }

  function setAnalytics(model) {
    if (!isPlainObject(model)) {
      held = null;
      analyticsFaults = [fault(null, null, NOT_AN_OBJECT_FAULT, kindOf(model))];
      return { declared: null, held: null, faults: analyticsFaults.slice() };
    }
    held = { model: model };
    analyticsFaults = [];
    checkFields(model);
    checkCards(model);
    checkColumns(model, BOT_TABLE, BOT_COLUMNS);
    checkColumns(model, TIMEFRAME_TABLE, TIMEFRAME_COLUMNS);
    checkRows(model, BOT_ROWS, BOT_TABLE, BOT_ROW_AT);
    checkRows(model, TIMEFRAME_ROWS, TIMEFRAME_TABLE, TIMEFRAME_ROW_AT);
    checkAlpha(model);
    return report();
  }

  // loadAnalytics asks once per page and clears asked when the call is refused.
  function loadAnalytics(params) {
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
        setAnalytics(model);
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
    return held === null ? undefined : held.model[name];
  }

  function bag(name) {
    return held === null ? {} : copyOf(objectField(held.model, name));
  }

  function list(name) {
    return held === null ? [] : listField(held.model, name).slice();
  }

  function accessibleName() {
    return field(ACCESSIBLE_NAME);
  }

  function page() {
    return bag(PAGE);
  }

  function cards() {
    return list(CARDS);
  }

  function cardOrder() {
    return list(CARD_ORDER);
  }

  function cardLabels() {
    return bag(CARD_LABELS);
  }

  function cardSkin() {
    return bag(CARD_SKIN);
  }

  function mainSplitter() {
    return bag(MAIN_SPLITTER);
  }

  function bottomSplitter() {
    return bag(BOTTOM_SPLITTER);
  }

  function groups() {
    return bag(GROUPS);
  }

  function groupOrder() {
    return list(GROUP_ORDER);
  }

  function botTable() {
    return bag(BOT_TABLE);
  }

  function timeframeTable() {
    return bag(TIMEFRAME_TABLE);
  }

  function botColumns() {
    return list(BOT_COLUMNS);
  }

  function timeframeColumns() {
    return list(TIMEFRAME_COLUMNS);
  }

  function botFields() {
    return list(BOT_FIELDS);
  }

  function timeframeFields() {
    return list(TIMEFRAME_FIELDS);
  }

  function botRows() {
    return list(BOT_ROWS);
  }

  function timeframeRows() {
    return list(TIMEFRAME_ROWS);
  }

  function chart() {
    return bag(CHART);
  }

  function chartSkin() {
    return bag(CHART_SKIN);
  }

  function equityCurveHours() {
    return field(EQUITY_CURVE_HOURS);
  }

  function summaryDefaults() {
    return bag(SUMMARY_DEFAULTS);
  }

  function numberFormats() {
    return bag(NUMBER_FORMATS);
  }

  function colors() {
    return bag(COLORS);
  }

  function actions() {
    return bag(ACTIONS);
  }

  function timers() {
    return bag(TIMERS);
  }

  function timerDelaysMs() {
    return list(TIMER_DELAYS_MS);
  }

  function skin() {
    return bag(SKIN);
  }

  function declaredFields() {
    return DECLARED_FIELDS.slice();
  }

  function cardFields() {
    return CARD_FIELDS.slice();
  }

  // Every drawn card's label, in the order the surface published them.
  function cardTitles() {
    return held === null
      ? []
      : cardList(held.model).map(function (one) {
          return cardObject(one)[LABEL];
        });
  }

  // The card the surface keyed name, undefined when no card carries it.
  function card(name) {
    var found;
    if (held === null) {
      return found;
    }
    cardList(held.model).forEach(function (one) {
      var fields = cardObject(one);
      if (fields[KEY] === name && found === undefined) {
        found = fields;
      }
    });
    return found;
  }

  // The label the surface published under name, own names only.
  function labelFor(name) {
    var named = held === null ? {} : objectField(held.model, CARD_LABELS);
    return owns(named, name) ? named[name] : undefined;
  }

  // The gradient stop colours the chart fills with, as CSS values.
  function fillColours() {
    var stops = listField(objectField(chart(), GRADIENT), STOPS);
    return stops.map(function (one) {
      return rgba(Array.isArray(one) ? one[ONE] : null);
    });
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
    return analyticsFaults.slice();
  }

  function loadError() {
    return loadFault;
  }

  function isLoaded() {
    return held !== null;
  }

  function element() {
    return global.React.createElement.apply(null, arguments);
  }

  function MetricCard(props) {
    var fields = props.card;
    var skinBag = props.skin;
    var style = styleOf(fields[FRAME_STYLE]);
    var padding = marginStyle(skinBag, PADDING_PX);
    Object.keys(padding).forEach(function (side) {
      style[side] = padding[side];
    });
    style.display = FLEX;
    style.flexDirection = COLUMN_DIRECTION;
    style.gap = pixels(skinBag[SPACING_PX]);
    style.flex = String(ONE);
    var cardProps = { className: CARD_CLASS, style: style };
    cardProps[PART_ATTR] = CARD_PART;
    cardProps[KEY_ATTR] = text(fields[KEY]);
    cardProps[AT_ATTR] = text(props.at);
    cardProps[ARIA_LABEL] = label(fields[CARD_ACCESSIBLE_NAME]);
    var labelProps = { className: TITLE_CLASS, style: styleOf(fields[LABEL_STYLE]) };
    labelProps[PART_ATTR] = CARD_LABEL_PART;
    labelProps[KEY_ATTR] = text(fields[KEY]);
    var valueProps = { style: styleOf(fields[VALUE_STYLE]) };
    valueProps[PART_ATTR] = CARD_VALUE_PART;
    valueProps[KEY_ATTR] = text(fields[KEY]);
    return element(
      DIV,
      cardProps,
      element(SPAN, labelProps, text(fields[LABEL])),
      element(SPAN, valueProps, text(fields[VALUE]))
    );
  }

  function MetricsRow(props) {
    var model = props.model;
    var skinBag = objectField(model, CARD_SKIN);
    var pageBag = objectField(model, PAGE);
    var style = {
      display: FLEX,
      flexDirection: ROW_DIRECTION,
      gap: pixels(pageBag[SPACING_PX])
    };
    var rowProps = { className: METRICS_CLASS, style: style };
    rowProps[PART_ATTR] = METRICS_PART;
    rowProps[DECLARED_CARDS_ATTR] = text(listField(model, CARD_ORDER).length);
    rowProps[HELD_CARDS_ATTR] = text(listField(model, CARDS).length);
    return element(
      DIV,
      rowProps,
      cardList(model).map(function (one, at) {
        return element(MetricCard, {
          card: cardObject(one),
          skin: skinBag,
          at: at,
          key: String(at)
        });
      })
    );
  }

  function DataTable(props) {
    var table = props.table;
    var columns = props.columns;
    var coloured = table[COLORED_COLUMN];
    var tableProps = {
      className: TABLE_CLASS,
      style: { width: String(100) + PERCENT, borderCollapse: "collapse" }
    };
    tableProps[PART_ATTR] = TABLE_PART;
    tableProps[KEY_ATTR] = props.name;
    tableProps[DECLARED_COLUMNS_ATTR] = text(table[COLUMN_COUNT]);
    tableProps[HELD_COLUMNS_ATTR] = text(columns.length);
    tableProps[COLORED_ATTR] = text(coloured);
    tableProps[ALTERNATING_ATTR] = text(table[ALTERNATING_ROW_COLORS]);
    tableProps[VERTICAL_HEADER_ATTR] = text(table[VERTICAL_HEADER_VISIBLE]);
    var head = element(
      HEAD,
      null,
      element(
        TABLE_ROW,
        null,
        columns.map(function (name, at) {
          var headProps = { key: String(at), style: { textAlign: CENTRE } };
          headProps[PART_ATTR] = HEAD_PART;
          headProps[COLUMN_ATTR] = text(at);
          return element(HEAD_CELL, headProps, text(name));
        })
      )
    );
    var body = element(
      BODY,
      null,
      props.rows.map(function (row, at) {
        var rowProps = { key: String(at) };
        rowProps[PART_ATTR] = ROW_PART;
        rowProps[ROW_ATTR] = text(at);
        return element(
          TABLE_ROW,
          rowProps,
          row.map(function (one, column) {
            var style = { textAlign: isPlainObject(one) ? one[ALIGN] : CENTRE };
            if (isPlainObject(one) && label(one[COLOR]) !== undefined) {
              style.color = one[COLOR];
            }
            var cellProps = { key: String(column), style: style };
            cellProps[PART_ATTR] = CELL_PART;
            cellProps[ROW_ATTR] = text(at);
            cellProps[COLUMN_ATTR] = text(column);
            return element(CELL, cellProps, text(isPlainObject(one) ? one[TEXT] : one));
          })
        );
      })
    );
    return element(TABLE, tableProps, head, body);
  }

  function ChartGradient(props) {
    var gradient = props.gradient;
    var from = listField(gradient, START_PX);
    var to = listField(gradient, END_PX);
    return element(
      LINEAR_GRADIENT,
      {
        id: GRADIENT_ID,
        gradientUnits: "userSpaceOnUse",
        x1: from[ZERO],
        y1: from[ONE],
        x2: to[ZERO],
        y2: to[ONE]
      },
      listField(gradient, STOPS).map(function (one, at) {
        var parts = Array.isArray(one) ? one : [];
        return element(STOP, {
          key: String(at),
          offset: parts[ZERO],
          stopColor: rgba(parts[ONE])
        });
      })
    );
  }

  function EquityChart(props) {
    var plan = props.chart;
    var skinBag = props.skin;
    var width = plan[WIDTH_PX];
    var height = plan[HEIGHT_PX];
    var svgProps = {
      className: CHART_CLASS,
      width: width,
      height: height,
      viewBox: [ZERO, ZERO, width, height].join(SPACE),
      style: {
        background: plan[BACKGROUND],
        minHeight: pixels(skinBag[MIN_HEIGHT_PX]),
        width: String(100) + PERCENT
      },
      shapeRendering: plan[ANTIALIASED] ? "auto" : "crispEdges"
    };
    svgProps[PART_ATTR] = CHART_PART;
    svgProps[EMPTY_ATTR] = text(plan[EMPTY_CHART]);
    svgProps[ANTIALIASED_ATTR] = text(plan[ANTIALIASED]);
    svgProps[ARIA_LABEL] = label(skinBag[CARD_ACCESSIBLE_NAME]);
    var rect = listField(plan, RECT_PX);
    var groundProps = {
      x: rect[ZERO],
      y: rect[ONE],
      width: rect[2],
      height: rect[ALPHA_AT],
      fill: plan[BACKGROUND]
    };
    groundProps[PART_ATTR] = CHART_GROUND_PART;
    var parts = [element(RECT, groundProps, null)];
    if (plan[EMPTY_CHART] === true) {
      var emptyProps = {
        x: width / 2,
        y: height / 2,
        fill: plan[TEXT_COLOR],
        textAnchor: MIDDLE,
        dominantBaseline: MIDDLE
      };
      emptyProps[PART_ATTR] = CHART_EMPTY_PART;
      parts.push(element(SVG_TEXT, emptyProps, text(plan[TEXT])));
      return element(SVG, svgProps, parts);
    }
    parts.push(
      element(DEFS, { key: GRADIENT }, element(ChartGradient, {
        gradient: objectField(plan, GRADIENT)
      }))
    );
    listField(plan, GRID_LINES_PX).forEach(function (one, at) {
      var lineProps = {
        key: CHART_GRID_PART + String(at),
        x1: one[ZERO],
        y1: one[ONE],
        x2: one[2],
        y2: one[ALPHA_AT],
        stroke: plan[GRID_COLOR],
        strokeWidth: plan[GRID_WIDTH_PX]
      };
      lineProps[PART_ATTR] = CHART_GRID_PART;
      lineProps[AT_ATTR] = text(at);
      parts.push(element(LINE, lineProps));
    });
    var fillProps = {
      key: CHART_FILL_PART,
      points: listField(plan, POLYGON_PX)
        .map(function (one) {
          return one.join(",");
        })
        .join(SPACE),
      fill: URL_OPEN + GRADIENT_ID + URL_CLOSE,
      stroke: NONE
    };
    fillProps[PART_ATTR] = CHART_FILL_PART;
    parts.push(element(POLYGON, fillProps));
    listField(plan, SEGMENTS_PX).forEach(function (one, at) {
      var lineProps = {
        key: CHART_LINE_PART + String(at),
        x1: one[ZERO],
        y1: one[ONE],
        x2: one[2],
        y2: one[ALPHA_AT],
        stroke: plan[LINE_COLOR],
        strokeWidth: plan[LINE_WIDTH_PX]
      };
      lineProps[PART_ATTR] = CHART_LINE_PART;
      lineProps[AT_ATTR] = text(at);
      parts.push(element(LINE, lineProps));
    });
    listField(plan, LABELS).forEach(function (one, at) {
      var labelProps = {
        key: CHART_LABEL_PART + String(at),
        x: one[X_PX],
        y: one[Y_PX],
        fill: one[COLOR],
        fontFamily: one[FONT_FAMILY],
        fontSize: fontPixels(one[FONT_POINT_SIZE])
      };
      labelProps[PART_ATTR] = CHART_LABEL_PART;
      labelProps[AT_ATTR] = text(at);
      parts.push(element(SVG_TEXT, labelProps, text(one[TEXT])));
    });
    return element(SVG, svgProps, parts);
  }

  function Group(props) {
    var group = props.group;
    var style = styleOf(group[STYLE]);
    style.display = FLEX;
    style.flexDirection = COLUMN_DIRECTION;
    style.overflow = "auto";
    style.flex = props.share;
    var groupProps = { className: GROUP_CLASS, role: GROUP_ROLE, style: style };
    groupProps[PART_ATTR] = GROUP_PART;
    groupProps[KEY_ATTR] = props.name;
    groupProps[ARIA_LABEL] = label(group[TITLE]);
    var titleProps = { className: TITLE_CLASS };
    titleProps[PART_ATTR] = TITLE_PART;
    titleProps[KEY_ATTR] = props.name;
    return element(
      SECTION,
      groupProps,
      element(DIV, titleProps, text(group[TITLE])),
      props.children
    );
  }

  // A Qt splitter shares its space by the sizes it was given, which is
  // what a flex-grow of the same number does.
  function share(splitter, at) {
    var sizes = listField(splitter, SIZES_PX);
    return at < sizes.length ? String(sizes[at]) : undefined;
  }

  function splitStyle(splitter) {
    return {
      display: FLEX,
      flexDirection:
        splitter[ORIENTATION] === VERTICAL ? COLUMN_DIRECTION : ROW_DIRECTION,
      gap: pixels(splitter[HANDLE_WIDTH_PX]),
      flex: String(ONE),
      minHeight: String(ZERO),
      minWidth: String(ZERO)
    };
  }

  function BottomSplitter(props) {
    var model = props.model;
    var splitter = objectField(model, BOTTOM_SPLITTER);
    var named = objectField(model, GROUPS);
    var splitProps = { className: SPLIT_CLASS, style: splitStyle(splitter) };
    splitProps[PART_ATTR] = SPLIT_PART;
    splitProps[KEY_ATTR] = BOTTOM_SPLITTER;
    splitProps[ORIENTATION_ATTR] = text(splitter[ORIENTATION]);
    return element(
      DIV,
      splitProps,
      element(
        Group,
        { key: "bots", name: "bots", group: objectField(named, "bots"), share: share(splitter, ZERO) },
        element(DataTable, {
          name: BOT_TABLE,
          table: objectField(model, BOT_TABLE),
          columns: listField(model, BOT_COLUMNS),
          rows: rowsOf(model, BOT_ROWS)
        })
      ),
      element(
        Group,
        {
          key: "timeframes",
          name: "timeframes",
          group: objectField(named, "timeframes"),
          share: share(splitter, ONE)
        },
        element(DataTable, {
          name: TIMEFRAME_TABLE,
          table: objectField(model, TIMEFRAME_TABLE),
          columns: listField(model, TIMEFRAME_COLUMNS),
          rows: rowsOf(model, TIMEFRAME_ROWS)
        })
      )
    );
  }

  function MainSplitter(props) {
    var model = props.model;
    var splitter = objectField(model, MAIN_SPLITTER);
    var named = objectField(model, GROUPS);
    var splitProps = { className: SPLIT_CLASS, style: splitStyle(splitter) };
    splitProps[PART_ATTR] = SPLIT_PART;
    splitProps[KEY_ATTR] = MAIN_SPLITTER;
    splitProps[ORIENTATION_ATTR] = text(splitter[ORIENTATION]);
    return element(
      DIV,
      splitProps,
      element(
        Group,
        {
          key: "equity",
          name: "equity",
          group: objectField(named, "equity"),
          share: share(splitter, ZERO)
        },
        element(EquityChart, {
          chart: objectField(model, CHART),
          skin: objectField(model, CHART_SKIN)
        })
      ),
      element(BottomSplitter, { key: BOTTOM_SPLITTER, model: model })
    );
  }

  function AnalyticsTab(props) {
    var model = props.model;
    if (!isPlainObject(model)) {
      return null;
    }
    var pageBag = objectField(model, PAGE);
    var style = marginStyle(pageBag, MARGINS_PX);
    style.display = FLEX;
    style.flexDirection = COLUMN_DIRECTION;
    style.gap = pixels(pageBag[SPACING_PX]);
    var tabProps = { className: TAB_CLASS, style: style };
    tabProps[PART_ATTR] = TAB_PART;
    tabProps[ARIA_LABEL] = label(model[ACCESSIBLE_NAME]);
    return element(
      DIV,
      tabProps,
      element(MetricsRow, { key: METRICS_PART, model: model }),
      element(MainSplitter, { key: MAIN_SPLITTER, model: model })
    );
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

  function renderTab(target, model) {
    var payload = model;
    if (!isPlainObject(payload)) {
      payload = held === null ? null : held.model;
    }
    return draw(target, element(AnalyticsTab, { model: payload }));
  }

  function forget() {
    held = null;
    analyticsFaults = [];
    loadFault = null;
    asked = null;
  }

  global.acervatorSetAnalytics = setAnalytics;
  global.acervatorLoadAnalytics = loadAnalytics;
  global.acervatorAnalytics = {
    method: METHOD,
    AnalyticsTab: AnalyticsTab,
    MetricsRow: MetricsRow,
    MetricCard: MetricCard,
    MainSplitter: MainSplitter,
    BottomSplitter: BottomSplitter,
    Group: Group,
    EquityChart: EquityChart,
    ChartGradient: ChartGradient,
    DataTable: DataTable,
    accessibleName: accessibleName,
    page: page,
    cards: cards,
    cardOrder: cardOrder,
    cardLabels: cardLabels,
    cardSkin: cardSkin,
    mainSplitter: mainSplitter,
    bottomSplitter: bottomSplitter,
    groups: groups,
    groupOrder: groupOrder,
    botTable: botTable,
    timeframeTable: timeframeTable,
    botColumns: botColumns,
    timeframeColumns: timeframeColumns,
    botFields: botFields,
    timeframeFields: timeframeFields,
    botRows: botRows,
    timeframeRows: timeframeRows,
    chart: chart,
    chartSkin: chartSkin,
    equityCurveHours: equityCurveHours,
    summaryDefaults: summaryDefaults,
    numberFormats: numberFormats,
    colors: colors,
    actions: actions,
    timers: timers,
    timerDelaysMs: timerDelaysMs,
    skin: skin,
    declaredFields: declaredFields,
    cardFields: cardFields,
    cardTitles: cardTitles,
    card: card,
    labelFor: labelFor,
    fillColours: fillColours,
    rgba: rgba,
    byteAlpha: byteAlpha,
    declarations: declarations,
    styleOf: styleOf,
    unpaintable: unpaintable,
    variableFor: variableFor,
    kinds: kinds,
    faults: faults,
    loadError: loadError,
    isLoaded: isLoaded,
    renderTab: renderTab,
    forget: forget
  };
})(window);
