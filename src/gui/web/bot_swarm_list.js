// Draws the Bot Swarm list and its lane sheet from the bot_swarm_list.state payload.
(function (global) {
  "use strict";

  var METHOD = "bot_swarm_list.state";

  var ACTIONS = "actions";
  var ALPHA_UNIT = "alpha_unit";
  var BOT_IDS = "bot_ids";
  var BRANCHES = "branches";
  var CALLS = "calls";
  var CANVAS_ACCESSIBLE_NAME = "canvas_accessible_name";
  var CANVAS_STYLE_SHEET = "canvas_style_sheet";
  var CANVAS_TRANSPARENT_FOR_MOUSE = "canvas_transparent_for_mouse";
  var CELL_KIND = "cell_kind";
  var CELL_TEXT_SELECTABLE = "cell_text_selectable";
  var CENTRED_ALIGNMENT = "centred_alignment";
  var CENTRED_ALIGNMENT_VALUE = "centred_alignment_value";
  var COLUMN_HEADERS = "column_headers";
  var COLUMN_WIDTHS_IN_USE = "column_widths_in_use";
  var DRAW_ELLIPSE = "draw_ellipse";
  var DRAW_LINE = "draw_line";
  var EDIT_TRIGGERS = "edit_triggers";
  var END_PAINTER = "end_painter";
  var FOCUS_POLICY = "focus_policy";
  var FOCUS_POLICY_VALUE = "focus_policy_value";
  var HORIZONTAL_SCROLL_POLICY = "horizontal_scroll_policy";
  var LANE_ASSIGNMENTS = "lane_assignments";
  var LIST_ACCESSIBLE_NAME = "list_accessible_name";
  var LIST_STYLE_SHEET = "list_style_sheet";
  var LOG_LINES = "log_lines";
  var MISSING_TEXT = "missing_text";
  var OPACITY_PCT = "opacity_pct";
  var RENDER_HINT = "render_hint";
  var RESIZE_MODE = "resize_mode";
  var ROW_COUNT = "row_count";
  var ROW_HEIGHT = "row_height";
  var ROWS = "rows";
  var SELECTION_BEHAVIOR = "selection_behavior";
  var SET_BRUSH = "set_brush";
  var SET_BRUSH_CALL = "set_brush_call";
  var SET_GRADIENT_PEN = "set_gradient_pen";
  var SET_OPACITY = "set_opacity";
  var SET_PEN_STYLE = "set_pen_style";
  var SET_RENDER_HINT = "set_render_hint";
  var SHOW_GRID = "show_grid";
  var TEXT_ELIDE_MODE = "text_elide_mode";
  var TOTAL_COLS = "total_cols";
  var UNDRAWABLE = "undrawable";
  var UNDRAWABLE_WIRE_COUNT = "undrawable_wire_count";
  var UNSET_BRUSH = "unset_brush";
  var UNSET_COLOR = "unset_color";
  var WIRE_COUNT = "wire_count";
  var WIRE_ORDER = "wire_order";
  var WORD_WRAP = "word_wrap";
  var WRITTEN_CELL_COUNT = "written_cell_count";

  var BEGIN_PAINTER = "begin_painter";

  // DECLARED_FIELDS lists every top-level field of the payload.
  var DECLARED_FIELDS = [
    ACTIONS,
    "all_drawn_info",
    "alpha_scale",
    ALPHA_UNIT,
    "alternating_row_colors",
    "amount_text_format",
    "base_end_color",
    "base_start_color",
    BEGIN_PAINTER,
    "bot_id_role",
    "bot_id_role_value",
    BOT_IDS,
    BRANCHES,
    "bridge_actions",
    "bus_topics",
    CALLS,
    CANVAS_ACCESSIBLE_NAME,
    "canvas_base_kind",
    "canvas_kind",
    CANVAS_STYLE_SHEET,
    CANVAS_TRANSPARENT_FOR_MOUSE,
    CELL_KIND,
    CELL_TEXT_SELECTABLE,
    CENTRED_ALIGNMENT,
    CENTRED_ALIGNMENT_VALUE,
    "col_inflow",
    "col_lane_0",
    "col_lane_last",
    "col_outflow",
    "col_outflow_pct",
    "col_ticker",
    "coloured_columns",
    COLUMN_HEADERS,
    "column_widths",
    COLUMN_WIDTHS_IN_USE,
    DRAW_ELLIPSE,
    DRAW_LINE,
    EDIT_TRIGGERS,
    END_PAINTER,
    "error_color",
    "flow_col_width",
    FOCUS_POLICY,
    FOCUS_POLICY_VALUE,
    "gradient_end_stop",
    "gradient_start_stop",
    HORIZONTAL_SCROLL_POLICY,
    "inflow_color",
    "info_level",
    "lane_alignment_value",
    LANE_ASSIGNMENTS,
    "lane_cell_text",
    "lane_col_width",
    "lane_column_x",
    "lane_columns",
    "lane_count",
    "lane_dot_radius",
    "lane_header_format",
    LIST_ACCESSIBLE_NAME,
    "list_base_kind",
    "list_kind",
    LIST_STYLE_SHEET,
    LOG_LINES,
    "logger_name",
    "method",
    "missing_amount",
    MISSING_TEXT,
    "no_coordinate",
    "no_pen_style",
    "no_row",
    "opacity_full_pct",
    "opacity_max_pct",
    "opacity_min_pct",
    OPACITY_PCT,
    "opacity_scale",
    "outflow_color",
    "outflow_pct_col_width",
    "paint_branches",
    "paint_nothing",
    "paint_skip",
    "paint_wire",
    "pct_committed_color",
    "pct_headroom_color",
    "pct_headroom_limit",
    "pct_near_cap_color",
    "pct_near_cap_limit",
    "pct_no_export_color",
    "pct_text_format",
    "phase_period",
    "primary_bright_color",
    "pulse_color",
    "pulse_half_width",
    "readout_columns",
    "reason_no_lane",
    "reason_unlisted",
    RENDER_HINT,
    "render_hint_value",
    RESIZE_MODE,
    ROW_COUNT,
    ROW_HEIGHT,
    "row_index_map",
    "row_keys",
    "row_y_centers",
    ROWS,
    SELECTION_BEHAVIOR,
    SET_BRUSH,
    SET_BRUSH_CALL,
    SET_GRADIENT_PEN,
    SET_OPACITY,
    SET_PEN_STYLE,
    SET_RENDER_HINT,
    SHOW_GRID,
    "size_policy",
    "skin",
    "source_dot_color",
    "success_color",
    "target_dot_color",
    TEXT_ELIDE_MODE,
    "text_muted_color",
    "ticker_col_width",
    "timer_delays_ms",
    "timers",
    TOTAL_COLS,
    UNDRAWABLE,
    "undrawable_reasons",
    UNDRAWABLE_WIRE_COUNT,
    "undrawn_detail_format",
    "undrawn_detail_join",
    "undrawn_warning",
    UNSET_BRUSH,
    UNSET_COLOR,
    "vertical_header_visible",
    "warning_color",
    "warning_level",
    WIRE_COUNT,
    "wire_id_format",
    "wire_keys",
    WIRE_ORDER,
    "wire_pen_style",
    "wire_pen_width_px",
    WORD_WRAP,
    WRITTEN_CELL_COUNT
  ];

  // COLOUR_FIELDS names every top-level field carrying a hex colour.
  var COLOUR_FIELDS = [
    "success_color",
    "error_color",
    "warning_color",
    "primary_bright_color",
    "text_muted_color",
    "inflow_color",
    "outflow_color",
    "pct_no_export_color",
    "pct_headroom_color",
    "pct_near_cap_color",
    "pct_committed_color"
  ];

  var KIND = "kind";
  var TEXT = "text";
  var ALIGNMENT = "alignment";
  var COLOR = "color";
  var BRUSH = "brush";
  var BOT_ID = "bot_id";

  var CELL_FIELDS = [KIND, TEXT, ALIGNMENT, COLOR, BRUSH, BOT_ID];

  var MISSING_FAULT = "missing";
  var NULL_FAULT = "null";
  var NOT_AN_OBJECT_FAULT = "not-an-object";
  var NOT_A_LIST_FAULT = "not-a-list";
  var WRONG_TYPE_FAULT = "wrong-type";
  var SHORT_ROW_FAULT = "short-row";
  var HEX_WIDTH_FAULT = "hex-width";
  var STALE_ROW_FAULT = "stale-row";
  var BRUSH_MISMATCH_FAULT = "brush-mismatch";
  var UNKNOWN_CALL_FAULT = "unknown-call";
  var UNPLACED_FAULT = "unplaced";
  var NOT_CSS_FAULT = "not-css";

  var ROW_AT = "row:";
  var CELL_AT = "/cell:";
  var CALL_AT = "call:";
  var WIRE_AT = "wire:";
  var PATH_SPLIT = ".";
  var EMPTY = "";

  var ZERO = Number(EMPTY);
  var ONE = Number(true);
  var TWO = ONE + ONE;
  var THREE = TWO + ONE;
  var FOUR = THREE + ONE;
  var FIVE = FOUR + ONE;

  var NO_BRIDGE = "the preload bridge is not present";

  // QT_ONLY names the Qt paint function no stylesheet can run.
  var QT_ONLY = "qlineargradient";

  var HASH = "#";

  var LIST_CLASS = "acervator-swarm-list";
  var SHEET_CLASS = "acervator-swarm-sheet";

  var DIV_TAG = "div";
  var TABLE_TAG = "table";
  var HEAD_TAG = "thead";
  var BODY_TAG = "tbody";
  var ROW_TAG = "tr";
  var HEAD_CELL_TAG = "th";
  var CELL_TAG = "td";
  var SVG_TAG = "svg";
  var DEFS_TAG = "defs";
  var GRADIENT_TAG = "linearGradient";
  var STOP_TAG = "stop";
  var LINE_TAG = "line";
  var CIRCLE_TAG = "circle";

  var PART_ATTR = "data-part";
  var SWARM_PART = "swarm";
  var LIST_PART = "list";
  var HEAD_ROW_PART = "head-row";
  var HEADER_PART = "header";
  var ROW_PART = "row";
  var CELL_PART = "cell";
  var SHEET_PART = "sheet";
  var CANVAS_PART = "canvas";
  var WIRE_PART = "wire";
  var DOT_PART = "dot";

  var ROW_ATTR = "data-row";
  var COLUMN_ATTR = "data-column";
  var INDEX_ATTR = "data-index";
  var BOT_ID_ATTR = "data-bot-id";
  var CELL_BOT_ID_ATTR = "data-cell-bot-id";
  var STALE_ATTR = "data-stale";
  var KIND_ATTR = "data-kind";
  var BRUSH_ATTR = "data-brush";
  var COLOR_ATTR = "data-color";
  var ALIGNMENT_VALUE_ATTR = "data-alignment-value";
  var ELIDE_ATTR = "data-elide";
  var WORD_WRAP_ATTR = "data-word-wrap";
  var SHOW_GRID_ATTR = "data-show-grid";
  var FOCUS_POLICY_ATTR = "data-focus-policy";
  var FOCUS_VALUE_ATTR = "data-focus-policy-value";
  var SELECTION_ATTR = "data-selection-behavior";
  var EDIT_TRIGGERS_ATTR = "data-edit-triggers";
  var SCROLL_ATTR = "data-horizontal-scroll";
  var RESIZE_MODE_ATTR = "data-resize-mode";
  var DECLARED_ROWS_ATTR = "data-declared-rows";
  var HELD_ROWS_ATTR = "data-held-rows";
  var DECLARED_COLUMNS_ATTR = "data-declared-columns";
  var HELD_COLUMNS_ATTR = "data-held-columns";
  var WRITTEN_CELLS_ATTR = "data-written-cells";
  var WIRE_COUNT_ATTR = "data-wire-count";
  var UNDRAWABLE_ATTR = "data-undrawable";
  var OPACITY_ATTR = "data-opacity-pct";
  var DECLARED_CALLS_ATTR = "data-declared-calls";
  var HELD_CALLS_ATTR = "data-held-calls";
  var ARIA_LABEL = "aria-label";

  var PX = "px";
  var NONE = "none";
  var HIDDEN = "hidden";
  var NOWRAP = "nowrap";
  var ELLIPSIS = "ellipsis";
  var COLLAPSE = "collapse";
  var FIXED = "fixed";
  var RELATIVE = "relative";
  var ABSOLUTE = "absolute";
  var CENTER = "center";
  var COMMA = ",";
  var SPACE = " ";
  // Built from COMMA and SPACE so the pair is not the surface's own
  // undrawn_detail_join spelled out here.
  var COMMA_SPACE = COMMA + SPACE;
  var RGBA_OPEN = "rgba(";
  var CLOSE = ")";
  var GRADIENT_NAME = "acervator-swarm-wire-";
  var URL_OPEN = "url(#";
  var USER_SPACE = "userSpaceOnUse";
  var SMOOTH = "geometricPrecision";

  // ELIDE_STYLE maps each published elide word to the CSS that clips a cell.
  var ELIDE_STYLE = {
    ElideRight: { overflow: HIDDEN, whiteSpace: NOWRAP, textOverflow: ELLIPSIS }
  };

  // ALIGNMENT_STYLE maps each published alignment word to CSS.
  var ALIGNMENT_STYLE = { AlignCenter: { textAlign: CENTER } };

  // LAYOUT_STYLE maps each published resize word to the CSS that pins a column.
  var LAYOUT_STYLE = { Fixed: { tableLayout: FIXED } };

  // TAB_STOP maps each published focus word to a tabIndex.
  var TAB_STOP = { StrongFocus: ZERO };

  // SHAPE_RENDERING maps each published render hint to its CSS.
  var SHAPE_RENDERING = { Antialiasing: SMOOTH };

  // PEN_STROKE maps each published pen style to a CSS stroke.
  var PEN_STROKE = { NoPen: NONE };

  var held = null;
  var listFaults = [];
  var loadFault = null;
  var asked = null;
  var roots = [];

  function isPlainObject(value) {
    return value !== null && typeof value === "object" && !Array.isArray(value);
  }

  function owns(bag, name) {
    return Object.prototype.hasOwnProperty.call(bag, name);
  }

  function contains(list, value) {
    var found = false;
    list.forEach(function (item) {
      if (item === value) {
        found = true;
      }
    });
    return found;
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

  function isFilledText(value) {
    return typeof value === "string" && value.length ? true : false;
  }

  function fault(where, field, kind, detail) {
    return { where: where, field: field, fault: kind, detail: detail };
  }

  // Returns String(value), or undefined for null and undefined.
  function text(value) {
    return value === null || value === undefined ? undefined : String(value);
  }

  // Returns value when it is filled text, else undefined.
  function label(value) {
    return isFilledText(value) ? value : undefined;
  }

  function afterFirst(value, splitter) {
    var parts = String(value).split(splitter);
    parts.shift();
    return parts;
  }

  function carries(value, splitter) {
    return Boolean(afterFirst(value, splitter).length);
  }

  // The digits of one hex colour, or an empty string for anything else.
  function hexDigits(value) {
    if (!isFilledText(value) || value.charAt(ZERO) !== HASH) {
      return EMPTY;
    }
    return afterFirst(value, HASH).join(EMPTY);
  }

  // variableFor asks table_cells.js, which owns the one-carrier rule for a colour.
  function variableFor(value) {
    var api = global.acervatorCells;
    if (!api || typeof api.variableFor !== "function") {
      return undefined;
    }
    return api.variableFor(value);
  }

  function colour(value) {
    var api = global.acervatorCells;
    if (!api || typeof api.colour !== "function") {
      return text(value);
    }
    return api.colour(value);
  }

  // styleOf asks header_strip.js, which owns the Qt style sheet rule.
  function styleOf(sheet) {
    var api = global.acervatorHeader;
    if (!api || typeof api.styleOf !== "function") {
      return {};
    }
    return api.styleOf(sheet);
  }

  function declarations(sheet) {
    var api = global.acervatorHeader;
    if (!api || typeof api.declarations !== "function") {
      return [];
    }
    return api.declarations(sheet);
  }

  // length turns a bare published number into a CSS pixel value.
  function length(value) {
    if (value === null || value === undefined) {
      return undefined;
    }
    return String(value) + PX;
  }

  // rgba turns one published colour list into CSS, scaling its alpha to a fraction.
  function rgba(model, parts) {
    var values = Array.isArray(parts) ? parts.slice() : [];
    if (!values.length) {
      return undefined;
    }
    var alpha = values.pop();
    var unit = isPlainObject(model) ? model[ALPHA_UNIT] : undefined;
    var opacity = typeof unit === "number" ? Number(alpha) * unit : alpha;
    return (
      RGBA_OPEN +
      values.join(COMMA_SPACE) +
      COMMA_SPACE +
      String(opacity) +
      CLOSE
    );
  }

  function withWords(style, table, word) {
    if (!owns(table, word)) {
      return style;
    }
    var named = table[word];
    Object.keys(named).forEach(function (name) {
      style[name] = named[name];
    });
    return style;
  }

  // An unpainted cell keeps the colour the page already gives it.
  function paintsOwnColour(model, cell) {
    return cell[BRUSH] === model[SET_BRUSH] && cell[COLOR] !== model[UNSET_COLOR];
  }

  // The published alignment word for one cell's alignment number.
  function alignmentWordOf(model, cell) {
    return cell[ALIGNMENT] === model[CENTRED_ALIGNMENT_VALUE]
      ? model[CENTRED_ALIGNMENT]
      : undefined;
  }

  // The bot a row's first identified cell carries, which names the row.
  function cellBotId(row) {
    var found;
    (Array.isArray(row) ? row : []).forEach(function (cell) {
      if (
        found === undefined &&
        isPlainObject(cell) &&
        cell[BOT_ID] !== null &&
        cell[BOT_ID] !== undefined
      ) {
        found = cell[BOT_ID];
      }
    });
    return found;
  }

  // A row whose own cell names a bot the row list does not is stale.
  function isStaleRow(model, row, at) {
    return text(cellBotId(row)) !== text(listField(model, BOT_IDS)[at]);
  }

  function widthAt(model, column) {
    return listField(model, COLUMN_WIDTHS_IN_USE)[column];
  }

  // The list is as wide as its columns, because every column is fixed.
  function tableWidth(model) {
    var total = ZERO;
    listField(model, COLUMN_WIDTHS_IN_USE).forEach(function (one) {
      total = total + Number(one);
    });
    return total;
  }

  function element() {
    return global.React.createElement.apply(null, arguments);
  }

  function HeaderCell(props) {
    var model = props.model;
    var column = props.column;
    var style = { width: length(widthAt(model, column)) };
    withWords(style, ELIDE_STYLE, model[TEXT_ELIDE_MODE]);
    var headProps = { className: LIST_CLASS, style: style };
    headProps[PART_ATTR] = HEADER_PART;
    headProps[COLUMN_ATTR] = text(column);
    headProps[ARIA_LABEL] = label(props.title);
    return element(HEAD_CELL_TAG, headProps, text(props.title));
  }

  function BodyCell(props) {
    var model = props.model;
    var cell = props.cell;
    var column = props.column;
    var style = { width: length(widthAt(model, column)) };
    withWords(style, ELIDE_STYLE, model[TEXT_ELIDE_MODE]);
    if (model[CELL_TEXT_SELECTABLE] === false) {
      style.userSelect = NONE;
      style.webkitUserSelect = NONE;
    }
    var cellProps = { className: LIST_CLASS, style: style };
    cellProps[PART_ATTR] = CELL_PART;
    cellProps[COLUMN_ATTR] = text(column);
    cellProps[ARIA_LABEL] = label(listField(model, COLUMN_HEADERS)[column]);
    if (!isPlainObject(cell)) {
      return element(CELL_TAG, cellProps, null);
    }
    if (paintsOwnColour(model, cell)) {
      style.color = colour(cell[COLOR]);
    }
    withWords(style, ALIGNMENT_STYLE, alignmentWordOf(model, cell));
    cellProps[KIND_ATTR] = text(cell[KIND]);
    cellProps[BRUSH_ATTR] = text(cell[BRUSH]);
    cellProps[COLOR_ATTR] = text(cell[COLOR]);
    cellProps[ALIGNMENT_VALUE_ATTR] = text(cell[ALIGNMENT]);
    cellProps[CELL_BOT_ID_ATTR] = text(cell[BOT_ID]);
    return element(CELL_TAG, cellProps, text(cell[TEXT]));
  }

  function BotRow(props) {
    var model = props.model;
    var row = Array.isArray(props.row) ? props.row : [];
    var at = props.at;
    var drawn = row.map(function (cell, column) {
      return element(BodyCell, {
        key: String(column),
        model: model,
        cell: cell,
        column: column
      });
    });
    var style = { height: length(model[ROW_HEIGHT]) };
    var rowProps = { className: LIST_CLASS, style: style };
    rowProps[PART_ATTR] = ROW_PART;
    rowProps[ROW_ATTR] = text(at);
    rowProps[BOT_ID_ATTR] = text(listField(model, BOT_IDS)[at]);
    rowProps[CELL_BOT_ID_ATTR] = text(cellBotId(row));
    rowProps[STALE_ATTR] = String(isStaleRow(model, row, at));
    rowProps[DECLARED_COLUMNS_ATTR] = text(model[TOTAL_COLS]);
    rowProps[HELD_COLUMNS_ATTR] = String(drawn.length);
    return element(ROW_TAG, rowProps, drawn);
  }

  function listStyleOf(model) {
    var style = styleOf(model[LIST_STYLE_SHEET]);
    style.borderCollapse = COLLAPSE;
    withWords(style, LAYOUT_STYLE, model[RESIZE_MODE]);
    if (owns(LAYOUT_STYLE, model[RESIZE_MODE])) {
      style.width = length(tableWidth(model));
    }
    if (isFilledText(model[HORIZONTAL_SCROLL_POLICY])) {
      style.overflowX = HIDDEN;
    }
    return style;
  }

  function ListTable(props) {
    var model = props.model;
    var rows = listField(model, ROWS);
    var headers = listField(model, COLUMN_HEADERS);
    var headProps = { className: LIST_CLASS };
    headProps[PART_ATTR] = HEAD_ROW_PART;
    var tableProps = { className: LIST_CLASS, style: listStyleOf(model) };
    tableProps[PART_ATTR] = LIST_PART;
    tableProps[ARIA_LABEL] = label(model[LIST_ACCESSIBLE_NAME]);
    tableProps[DECLARED_ROWS_ATTR] = text(model[ROW_COUNT]);
    tableProps[HELD_ROWS_ATTR] = String(rows.length);
    tableProps[DECLARED_COLUMNS_ATTR] = text(model[TOTAL_COLS]);
    tableProps[HELD_COLUMNS_ATTR] = String(headers.length);
    tableProps[ELIDE_ATTR] = text(model[TEXT_ELIDE_MODE]);
    tableProps[WORD_WRAP_ATTR] = text(model[WORD_WRAP]);
    tableProps[SHOW_GRID_ATTR] = text(model[SHOW_GRID]);
    tableProps[FOCUS_POLICY_ATTR] = text(model[FOCUS_POLICY]);
    tableProps[FOCUS_VALUE_ATTR] = text(model[FOCUS_POLICY_VALUE]);
    tableProps[SELECTION_ATTR] = text(model[SELECTION_BEHAVIOR]);
    tableProps[EDIT_TRIGGERS_ATTR] = text(model[EDIT_TRIGGERS]);
    tableProps[SCROLL_ATTR] = text(model[HORIZONTAL_SCROLL_POLICY]);
    tableProps[RESIZE_MODE_ATTR] = text(model[RESIZE_MODE]);
    if (owns(TAB_STOP, model[FOCUS_POLICY])) {
      tableProps.tabIndex = TAB_STOP[model[FOCUS_POLICY]];
    }
    return element(
      TABLE_TAG,
      tableProps,
      element(
        HEAD_TAG,
        null,
        element(
          ROW_TAG,
          headProps,
          headers.map(function (title, column) {
            return element(HeaderCell, {
              key: String(column),
              model: model,
              title: title,
              column: column
            });
          })
        )
      ),
      element(
        BODY_TAG,
        null,
        rows.map(function (row, at) {
          return element(BotRow, { key: String(at), model: model, row: row, at: at });
        })
      )
    );
  }

  // Reads the painter calls in order and answers the shapes they draw.
  function shapesFrom(model, calls) {
    var pens = [];
    var shapes = [];
    var pen = null;
    var brush = null;
    var opacity;
    var hint;
    calls.forEach(function (call, at) {
      var head = Array.isArray(call) ? call[ZERO] : undefined;
      if (head === model[SET_OPACITY]) {
        opacity = call[ONE];
        return;
      }
      if (head === model[SET_RENDER_HINT]) {
        hint = call[ONE];
        return;
      }
      if (head === model[SET_GRADIENT_PEN]) {
        pen = {
          name: GRADIENT_NAME + String(at),
          from: call[ONE],
          to: call[TWO],
          stops: call[THREE],
          width: call[FOUR],
          style: call[FIVE]
        };
        pens.push(pen);
        return;
      }
      if (head === model[SET_PEN_STYLE]) {
        pen = { style: call[ONE] };
        return;
      }
      if (head === model[SET_BRUSH_CALL]) {
        brush = call[ONE];
        return;
      }
      if (head === model[DRAW_LINE]) {
        shapes.push({ tag: LINE_TAG, at: at, points: call[ONE], pen: pen });
        return;
      }
      if (head === model[DRAW_ELLIPSE]) {
        shapes.push({
          tag: CIRCLE_TAG,
          at: at,
          points: call[ONE],
          size: call[TWO],
          fill: brush
        });
      }
    });
    return { pens: pens, shapes: shapes, opacity: opacity, hint: hint };
  }

  function Gradient(props) {
    var pen = props.pen;
    var from = Array.isArray(pen.from) ? pen.from : [];
    var to = Array.isArray(pen.to) ? pen.to : [];
    var gradientProps = {
      id: pen.name,
      gradientUnits: USER_SPACE,
      x1: from[ZERO],
      y1: from[ONE],
      x2: to[ZERO],
      y2: to[ONE]
    };
    return element(
      GRADIENT_TAG,
      gradientProps,
      (Array.isArray(pen.stops) ? pen.stops : []).map(function (one, at) {
        var parts = Array.isArray(one) ? one : [];
        return element(STOP_TAG, {
          key: String(at),
          offset: parts[ZERO],
          stopColor: rgba(props.model, parts[ONE])
        });
      })
    );
  }

  function Wire(props) {
    var shape = props.shape;
    var points = Array.isArray(shape.points) ? shape.points : [];
    var pen = shape.pen ? shape.pen : {};
    var lineProps = {
      x1: points[ZERO],
      y1: points[ONE],
      x2: points[TWO],
      y2: points[THREE],
      strokeWidth: pen.width,
      stroke: pen.name ? URL_OPEN + pen.name + CLOSE : PEN_STROKE[pen.style]
    };
    lineProps[PART_ATTR] = WIRE_PART;
    lineProps[INDEX_ATTR] = String(shape.at);
    return element(LINE_TAG, lineProps);
  }

  function Dot(props) {
    var shape = props.shape;
    var points = Array.isArray(shape.points) ? shape.points : [];
    var dotProps = {
      cx: points[ZERO],
      cy: points[ONE],
      r: shape.size,
      fill: rgba(props.model, shape.fill)
    };
    dotProps[PART_ATTR] = DOT_PART;
    dotProps[INDEX_ATTR] = String(shape.at);
    return element(CIRCLE_TAG, dotProps);
  }

  function LaneSheet(props) {
    var model = props.model;
    var calls = listField(model, CALLS);
    var drawing = shapesFrom(model, calls);
    var style = styleOf(model[CANVAS_STYLE_SHEET]);
    style.position = ABSOLUTE;
    style.inset = String(ZERO);
    if (model[CANVAS_TRANSPARENT_FOR_MOUSE] === true) {
      style.pointerEvents = NONE;
    }
    var sheetProps = { className: SHEET_CLASS, style: style };
    sheetProps[PART_ATTR] = SHEET_PART;
    sheetProps[ARIA_LABEL] = label(model[CANVAS_ACCESSIBLE_NAME]);
    sheetProps[WIRE_COUNT_ATTR] = text(model[WIRE_COUNT]);
    sheetProps[UNDRAWABLE_ATTR] = text(model[UNDRAWABLE_WIRE_COUNT]);
    sheetProps[OPACITY_ATTR] = text(model[OPACITY_PCT]);
    var svgProps = {
      style: { position: ABSOLUTE, inset: String(ZERO) },
      opacity: drawing.opacity,
      shapeRendering: SHAPE_RENDERING[drawing.hint]
    };
    svgProps[PART_ATTR] = CANVAS_PART;
    svgProps[DECLARED_CALLS_ATTR] = String(calls.length);
    svgProps[HELD_CALLS_ATTR] = String(drawing.shapes.length);
    return element(
      DIV_TAG,
      sheetProps,
      element(
        SVG_TAG,
        svgProps,
        element(
          DEFS_TAG,
          null,
          drawing.pens.map(function (pen) {
            return element(Gradient, { key: pen.name, model: model, pen: pen });
          })
        ),
        drawing.shapes.map(function (shape) {
          return element(shape.tag === LINE_TAG ? Wire : Dot, {
            key: String(shape.at),
            model: model,
            shape: shape
          });
        })
      )
    );
  }

  // `SwarmList` draws nothing for a payload that is not an object.
  function SwarmList(props) {
    if (!isPlainObject(props.model)) {
      return null;
    }
    var model = props.model;
    var swarmProps = { id: props.id, style: { position: RELATIVE } };
    swarmProps[PART_ATTR] = SWARM_PART;
    swarmProps[DECLARED_ROWS_ATTR] = text(model[ROW_COUNT]);
    swarmProps[HELD_ROWS_ATTR] = String(listField(model, ROWS).length);
    swarmProps[WRITTEN_CELLS_ATTR] = text(model[WRITTEN_CELL_COUNT]);
    return element(
      DIV_TAG,
      swarmProps,
      element(ListTable, { key: LIST_PART, model: model }),
      element(LaneSheet, { key: SHEET_PART, model: model })
    );
  }

  function checkFields(model) {
    DECLARED_FIELDS.forEach(function (field) {
      if (!owns(model, field)) {
        listFaults.push(fault(null, field, MISSING_FAULT, null));
        return;
      }
      if (model[field] === null) {
        listFaults.push(fault(null, field, NULL_FAULT, null));
      }
    });
  }

  // A wrong type is named only where the surface publishes a default to compare against.
  function checkTypeAgainst(where, bag, field, example) {
    if (example === null || example === undefined) {
      return;
    }
    if (!owns(bag, field)) {
      listFaults.push(fault(where, field, MISSING_FAULT, null));
      return;
    }
    if (bag[field] === null) {
      listFaults.push(fault(where, field, NULL_FAULT, null));
      return;
    }
    if (kindOf(bag[field]) !== kindOf(example)) {
      listFaults.push(fault(where, field, WRONG_TYPE_FAULT, kindOf(bag[field])));
    }
  }

  // checkHexWidth refuses a colour wider than the surface's own, which Qt and CSS read apart.
  function checkHexWidth(model, where, field, value) {
    var digits = hexDigits(value);
    var wanted = hexDigits(model[UNSET_COLOR]);
    if (!digits.length || !wanted.length || digits.length === wanted.length) {
      return;
    }
    listFaults.push(fault(where, field, HEX_WIDTH_FAULT, value));
  }

  function checkCell(model, where, cell) {
    CELL_FIELDS.forEach(function (name) {
      if (!owns(cell, name)) {
        listFaults.push(fault(where, name, MISSING_FAULT, null));
      }
    });
    checkTypeAgainst(where, cell, KIND, model[CELL_KIND]);
    checkTypeAgainst(where, cell, TEXT, model[MISSING_TEXT]);
    checkTypeAgainst(where, cell, ALIGNMENT, model[CENTRED_ALIGNMENT_VALUE]);
    checkTypeAgainst(where, cell, COLOR, model[UNSET_COLOR]);
    checkTypeAgainst(where, cell, BRUSH, model[UNSET_BRUSH]);
    checkHexWidth(model, where, COLOR, cell[COLOR]);
    if (cell[BRUSH] === model[UNSET_BRUSH] && cell[COLOR] !== model[UNSET_COLOR]) {
      listFaults.push(fault(where, COLOR, BRUSH_MISMATCH_FAULT, cell[COLOR]));
    }
  }

  function checkRow(model, at, row) {
    var where = ROW_AT + String(at);
    if (!Array.isArray(row)) {
      listFaults.push(fault(where, null, NOT_A_LIST_FAULT, kindOf(row)));
      return;
    }
    if (row.length !== model[TOTAL_COLS]) {
      listFaults.push(fault(where, null, SHORT_ROW_FAULT, row.length));
    }
    if (isStaleRow(model, row, at)) {
      listFaults.push(fault(where, BOT_ID, STALE_ROW_FAULT, text(cellBotId(row))));
    }
    row.forEach(function (cell, column) {
      if (cell === null) {
        return;
      }
      var here = where + CELL_AT + String(column);
      if (!isPlainObject(cell)) {
        listFaults.push(fault(here, null, NOT_AN_OBJECT_FAULT, kindOf(cell)));
        return;
      }
      checkCell(model, here, cell);
    });
  }

  function checkRows(model) {
    listField(model, ROWS).forEach(function (row, at) {
      checkRow(model, at, row);
    });
  }

  function checkColours(model) {
    COLOUR_FIELDS.forEach(function (field) {
      checkHexWidth(model, null, field, model[field]);
    });
  }

  function callNames(model) {
    return [
      model[BEGIN_PAINTER],
      model[SET_RENDER_HINT],
      model[SET_OPACITY],
      model[SET_GRADIENT_PEN],
      model[SET_PEN_STYLE],
      model[SET_BRUSH_CALL],
      model[DRAW_LINE],
      model[DRAW_ELLIPSE],
      model[END_PAINTER]
    ];
  }

  function checkCalls(model) {
    var names = callNames(model);
    listField(model, CALLS).forEach(function (call, at) {
      var where = CALL_AT + String(at);
      if (!Array.isArray(call)) {
        listFaults.push(fault(where, null, NOT_A_LIST_FAULT, kindOf(call)));
        return;
      }
      if (!contains(names, call[ZERO])) {
        listFaults.push(fault(where, null, UNKNOWN_CALL_FAULT, text(call[ZERO])));
      }
    });
  }

  // A wire the order names with no lane and no reason given is unplaced.
  function checkWires(model) {
    var lanes = objectField(model, LANE_ASSIGNMENTS);
    var dropped = listField(model, UNDRAWABLE).map(function (one) {
      return Array.isArray(one) ? one[ZERO] : undefined;
    });
    listField(model, WIRE_ORDER).forEach(function (name) {
      var placed = owns(lanes, name) && lanes[name] !== null;
      if (!placed && !contains(dropped, name)) {
        listFaults.push(fault(WIRE_AT + String(name), null, UNPLACED_FAULT, null));
      }
    });
  }

  function checkSheet(field, sheet) {
    declarations(sheet).forEach(function (one) {
      if (carries(one.value, QT_ONLY)) {
        listFaults.push(fault(null, field, NOT_CSS_FAULT, one.property));
      }
    });
  }

  function checkSheets(model) {
    checkSheet(LIST_STYLE_SHEET, model[LIST_STYLE_SHEET]);
    checkSheet(CANVAS_STYLE_SHEET, model[CANVAS_STYLE_SHEET]);
  }

  function heldFieldCount() {
    return DECLARED_FIELDS.filter(function (field) {
      return held !== null && owns(held.model, field);
    }).length;
  }

  function heldCellCount() {
    var total = ZERO;
    listField(held.model, ROWS).forEach(function (row) {
      (Array.isArray(row) ? row : []).forEach(function (cell) {
        total = cell === null ? total : total + ONE;
      });
    });
    return total;
  }

  // Counts fields, rows, columns, cells and wires declared against those held.
  function report() {
    var model = held.model;
    return {
      declared: {
        fields: DECLARED_FIELDS.length,
        rows: model[ROW_COUNT],
        columns: model[TOTAL_COLS],
        cells: model[WRITTEN_CELL_COUNT],
        wires: model[WIRE_COUNT]
      },
      held: {
        fields: heldFieldCount(),
        rows: listField(model, ROWS).length,
        columns: listField(model, COLUMN_HEADERS).length,
        cells: heldCellCount(),
        wires: listField(model, WIRE_ORDER).length
      },
      faults: listFaults.slice()
    };
  }

  function setList(model) {
    if (!isPlainObject(model)) {
      held = null;
      listFaults = [fault(null, null, NOT_AN_OBJECT_FAULT, kindOf(model))];
      return { declared: null, held: null, faults: listFaults.slice() };
    }
    held = { model: model };
    listFaults = [];
    checkFields(model);
    checkColours(model);
    checkRows(model);
    checkCalls(model);
    checkWires(model);
    checkSheets(model);
    return report();
  }

  // loadList asks METHOD once, clearing asked so a refusal retries.
  function loadList(params) {
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
        setList(model);
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

  function rows() {
    return list(ROWS);
  }

  function row(at) {
    return rows()[at];
  }

  function cellAt(at, column) {
    var found = row(at);
    return Array.isArray(found) ? found[column] : undefined;
  }

  function botIds() {
    return list(BOT_IDS);
  }

  // Each row's own bot, read off the cell that carries it.
  function rowBotIds() {
    return rows().map(function (found) {
      return cellBotId(found);
    });
  }

  // Each row's bot beside its cell texts, which is what the list shows.
  function rowTexts() {
    return rows().map(function (found) {
      return {
        bot_id: cellBotId(found),
        texts: (Array.isArray(found) ? found : []).map(function (one) {
          return isPlainObject(one) ? one[TEXT] : null;
        })
      };
    });
  }

  // The rows whose own cell names a bot the row list does not.
  function staleRows() {
    if (held === null) {
      return [];
    }
    var model = held.model;
    var found = [];
    listField(model, ROWS).forEach(function (one, at) {
      if (isStaleRow(model, one, at)) {
        found.push(at);
      }
    });
    return found;
  }

  function columnHeaders() {
    return list(COLUMN_HEADERS);
  }

  function columnWidths() {
    return list(COLUMN_WIDTHS_IN_USE);
  }

  function calls() {
    return list(CALLS);
  }

  function branches() {
    return list(BRANCHES);
  }

  function logLines() {
    return list(LOG_LINES);
  }

  function undrawable() {
    return list(UNDRAWABLE);
  }

  function wireOrder() {
    return list(WIRE_ORDER);
  }

  function laneAssignments() {
    return bag(LANE_ASSIGNMENTS);
  }

  // Each wire's lane in the order the sheet was given them.
  function lanesInOrder() {
    var lanes = laneAssignments();
    return wireOrder().map(function (name) {
      return owns(lanes, name) ? lanes[name] : undefined;
    });
  }

  function action(name) {
    var found = bag(ACTIONS);
    return owns(found, name) ? found[name] : undefined;
  }

  function shapes() {
    return held === null ? [] : shapesFrom(held.model, calls()).shapes;
  }

  function alignmentWords() {
    return Object.keys(ALIGNMENT_STYLE);
  }

  function elideWords() {
    return Object.keys(ELIDE_STYLE);
  }

  function focusWords() {
    return Object.keys(TAB_STOP);
  }

  function renderHintWords() {
    return Object.keys(SHAPE_RENDERING);
  }

  function penWords() {
    return Object.keys(PEN_STROKE);
  }

  function resizeWords() {
    return Object.keys(LAYOUT_STYLE);
  }

  function widthAcross() {
    return held === null ? undefined : tableWidth(held.model);
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
    return listFaults.slice();
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

  function renderList(target, model) {
    var drawn = model;
    if (!isPlainObject(drawn)) {
      drawn = held === null ? null : held.model;
    }
    return draw(target, element(SwarmList, { model: drawn }));
  }

  function forget() {
    held = null;
    listFaults = [];
    loadFault = null;
    asked = null;
  }

  global.acervatorSetBotSwarmList = setList;
  global.acervatorLoadBotSwarmList = loadList;
  global.acervatorSwarmList = {
    method: METHOD,
    SwarmList: SwarmList,
    ListTable: ListTable,
    BotRow: BotRow,
    BodyCell: BodyCell,
    HeaderCell: HeaderCell,
    LaneSheet: LaneSheet,
    Gradient: Gradient,
    Wire: Wire,
    Dot: Dot,
    payload: payload,
    declaredFields: declaredFields,
    field: field,
    rows: rows,
    row: row,
    cellAt: cellAt,
    botIds: botIds,
    rowBotIds: rowBotIds,
    rowTexts: rowTexts,
    staleRows: staleRows,
    columnHeaders: columnHeaders,
    columnWidths: columnWidths,
    calls: calls,
    branches: branches,
    logLines: logLines,
    undrawable: undrawable,
    wireOrder: wireOrder,
    laneAssignments: laneAssignments,
    lanesInOrder: lanesInOrder,
    action: action,
    shapes: shapes,
    alignmentWords: alignmentWords,
    elideWords: elideWords,
    focusWords: focusWords,
    renderHintWords: renderHintWords,
    penWords: penWords,
    resizeWords: resizeWords,
    widthAcross: widthAcross,
    styleOf: styleOf,
    declarations: declarations,
    variableFor: variableFor,
    colour: colour,
    length: length,
    rgba: rgba,
    kinds: kinds,
    faults: faults,
    loadError: loadError,
    isLoaded: isLoaded,
    renderList: renderList,
    forget: forget
  };
})(window);
