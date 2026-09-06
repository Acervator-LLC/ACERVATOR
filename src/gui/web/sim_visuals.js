// Publishes the Simulator drawn panes on the page global, as the surface serves them.
(function (global) {
  "use strict";

  var METHOD = "sim_visuals.state";

  var METHOD_FIELD = "method";
  var PANE = "gate_panel";
  var ROW = "gate_row";
  var CHART = "chart";
  var VOTES = "votes";
  var EXPAND = "expand";
  var ACTIONS = "actions";
  var TIMERS = "timers";
  var TIMER_DELAYS_MS = "timer_delays_ms";
  var BUS_TOPICS = "bus_topics";
  var BUS_EMITS = "bus_emits";
  var SIGNALS = "signals";
  var CALL_NAMES = "call_names";

  var DECLARED_FIELDS = [
    ACTIONS,
    BUS_EMITS,
    BUS_TOPICS,
    CALL_NAMES,
    CHART,
    EXPAND,
    METHOD_FIELD,
    PANE,
    ROW,
    SIGNALS,
    TIMERS,
    TIMER_DELAYS_MS,
    VOTES
  ];

  var ACCESSIBLE_NAME = "accessible_name";
  var ACCESSIBLE_DESCRIPTION = "accessible_description";
  var TOOLTIP = "tooltip";
  var STYLE_SHEET = "style_sheet";
  var MARGINS_PX = "margins_px";
  var SPACING_PX = "spacing_px";
  var SYMBOLS = "symbols";
  var SYMBOL = "symbol";
  var ROWS = "rows";
  var PROGRAM = "program";

  var SCROLL_STYLE = "scroll_style";
  var SCROLL_RESIZABLE = "scroll_resizable";
  var HOST_MARGINS_PX = "host_margins_px";
  var HOST_SPACING_PX = "host_spacing_px";
  var EMPTY_TEXT = "empty_text";
  var EMPTY_STYLE = "empty_style";
  var EMPTY_VISIBLE = "empty_visible";
  var ROW_MARGINS_PX = "row_margins_px";
  var ROW_SPACING_PX = "row_spacing_px";
  var LABEL_MIN_WIDTH_PX = "label_min_width_px";
  var LABEL_STYLE = "label_style";
  var TRAILING_STRETCH = "trailing_stretch";
  var ITEMS = "items";

  var PANE_FIELDS = [
    ACCESSIBLE_NAME,
    EMPTY_STYLE,
    EMPTY_TEXT,
    EMPTY_VISIBLE,
    HOST_MARGINS_PX,
    HOST_SPACING_PX,
    ITEMS,
    LABEL_MIN_WIDTH_PX,
    LABEL_STYLE,
    MARGINS_PX,
    ROW_MARGINS_PX,
    ROW_SPACING_PX,
    SCROLL_RESIZABLE,
    SCROLL_STYLE,
    SPACING_PX,
    SYMBOLS,
    TRAILING_STRETCH
  ];

  var FONT_PT = "font_pt";
  var PITCH_PX = "pitch_px";
  var HEIGHT_PX = "height_px";
  var MIN_WIDTH_PX = "min_width_px";
  var BANKS = "banks";
  var LABEL_COLOUR = "label_colour";
  var MARKER_COLOUR = "marker_colour";
  var LIGHT_COLOURS = "light_colours";
  var LIGHTS = "lights";

  var ROW_FIELDS = [
    BANKS,
    FONT_PT,
    HEIGHT_PX,
    LABEL_COLOUR,
    LIGHT_COLOURS,
    MARKER_COLOUR,
    MIN_WIDTH_PX,
    PITCH_PX,
    ROWS,
    TOOLTIP
  ];

  var SIZE_POLICY = "size_policy";
  var BAND_HEIGHT_PX = "band_height_px";
  var LABEL_WIDTH_PX = "label_width_px";
  var MAX_POINTS = "max_points";
  var VWAP_WINDOW = "vwap_window";
  var MAX_MARKERS = "max_markers";
  var MAX_CANDLES = "max_candles";
  var CANDLE_WIDTH_PX = "candle_width_px";
  var CANDLE_GAP_PX = "candle_gap_px";
  var FOCUS_MIN_HEIGHT_PX = "focus_min_height_px";
  var MINIMUM_HEIGHT_PX = "minimum_height_px";
  var FOCUS = "focus";

  var CHART_FIELDS = [
    ACCESSIBLE_DESCRIPTION,
    ACCESSIBLE_NAME,
    BAND_HEIGHT_PX,
    CANDLE_GAP_PX,
    CANDLE_WIDTH_PX,
    FOCUS,
    FOCUS_MIN_HEIGHT_PX,
    LABEL_WIDTH_PX,
    MAX_CANDLES,
    MAX_MARKERS,
    MAX_POINTS,
    MINIMUM_HEIGHT_PX,
    PROGRAM,
    SIZE_POLICY,
    STYLE_SHEET,
    SYMBOLS,
    TOOLTIP,
    VWAP_WINDOW
  ];

  var COLUMNS = "columns";
  var EDIT_TRIGGERS = "edit_triggers";
  var SELECTION_BEHAVIOUR = "selection_behaviour";
  var ALTERNATING_ROWS = "alternating_rows";
  var ALTERNATE_ROW_COLOUR = "alternate_row_colour";
  var ROW_HEIGHT_PX = "row_height_px";
  var HEADER_HEIGHT_PX = "header_height_px";
  var ROW_HEADER_VISIBLE = "row_header_visible";
  var COLUMN_MODE = "column_mode";
  var SYMBOL_COLUMN_MODE = "symbol_column_mode";
  var STRETCH_LAST_COLUMN = "stretch_last_column";
  var PLACEHOLDER = "placeholder";
  var CELLS = "cells";
  var DIRECTION_COLOUR = "direction_colour";

  var VOTE_FIELDS = [
    ACCESSIBLE_DESCRIPTION,
    ACCESSIBLE_NAME,
    ALTERNATE_ROW_COLOUR,
    ALTERNATING_ROWS,
    COLUMNS,
    COLUMN_MODE,
    EDIT_TRIGGERS,
    HEADER_HEIGHT_PX,
    PLACEHOLDER,
    ROWS,
    ROW_HEADER_VISIBLE,
    ROW_HEIGHT_PX,
    SELECTION_BEHAVIOUR,
    STRETCH_LAST_COLUMN,
    STYLE_SHEET,
    SYMBOL_COLUMN_MODE,
    TOOLTIP
  ];

  var CLAIM_FIELD = "claim_field";
  var DELETE_ON_CLOSE = "delete_on_close";
  var OPEN = "open";

  var EXPAND_FIELDS = [CLAIM_FIELD, DELETE_ON_CLOSE, MARGINS_PX, OPEN, STYLE_SHEET];

  var KIND = "kind";
  var KIND_EMPTY = "empty";
  var KIND_ROW = "row";
  var KIND_STRETCH = "stretch";
  var VISIBLE = "visible";

  var DRAWN_KINDS = {};
  DRAWN_KINDS[KIND_EMPTY] = true;
  DRAWN_KINDS[KIND_ROW] = true;
  DRAWN_KINDS[KIND_STRETCH] = true;

  var OP = "op";
  var OP_TEXT = "text";
  var OP_ELLIPSE = "ellipse";
  var OP_LINE = "line";
  var OP_RECT = "rect";
  var OP_FILL = "fill";
  var PEN = "pen";
  var BRUSH = "brush";
  var RECT = "rect";
  var ALIGN = "align";
  var LINE_FIELD = "line";
  var WIDTH_FIELD = "width";
  var STYLE_FIELD = "style";
  var AT_FIELD = "at";

  // NO_PAINT is the pen and the brush the surface writes for "do not paint".
  var NO_PAINT = "none";
  var TRANSPARENT = "transparent";
  var DASH_LINE = "dash";
  var CONTEXT_2D = "2d";
  // READ_BACK keeps the surface on the processor, so a whole repaint every
  // tick costs no upload and the painted pixels stay readable.
  var READ_BACK = { willReadFrequently: true };
  var CANVAS_TAG = "canvas";
  var CHART_CANVAS_PART = "chart-canvas";
  var BLOCK = "block";
  var MIDDLE = "middle";
  var LEFT = "left";
  var RIGHT = "right";
  var FUNCTION_KIND = "function";
  var TEXT_FIELD = "text";
  var BANK = "bank";
  var LABEL = "label";
  var STATE = "state";
  var COLOUR = "colour";

  var LIGHT_FIELDS = [BANK, COLOUR, LABEL, STATE];

  var ALIGN_LABEL = "hcenter|vcenter";
  var ALIGN_MARKER = "right|vcenter";
  var CENTER = "center";
  var FLEX_END = "flex-end";

  // ALIGNMENT maps one published align word to the two flex properties.
  var ALIGNMENT = {};
  ALIGNMENT[ALIGN_LABEL] = { justifyContent: CENTER, alignItems: CENTER };
  ALIGNMENT[ALIGN_MARKER] = { justifyContent: FLEX_END, alignItems: CENTER };

  var MODE_STRETCH = "Stretch";
  var MODE_TO_CONTENTS = "ResizeToContents";
  var POLICY_EXPANDING = "Expanding";
  var NO_EDIT_TRIGGERS = "NoEditTriggers";
  var SELECT_ROWS = "SelectRows";

  var MISSING_FAULT = "missing";
  var NULL_FAULT = "null";
  var NOT_AN_OBJECT_FAULT = "not-an-object";
  var NOT_A_LIST_FAULT = "not-a-list";
  var WRONG_TYPE_FAULT = "wrong-type";
  var NOT_CSS_FAULT = "not-css";
  var QT_COLOUR_FAULT = "qt-colour";
  var UNKNOWN_KIND_FAULT = "unknown-kind";
  var UNKNOWN_MODE_FAULT = "unknown-mode";
  var UNKNOWN_SYMBOL_FAULT = "unknown-symbol";
  var LAMP_ORDER_FAULT = "lamp-order";
  var LAMP_LABEL_FAULT = "lamp-label";
  var LAMP_COLOUR_FAULT = "lamp-colour";
  var LAMP_COUNT_FAULT = "lamp-count";
  var COLUMN_COUNT_FAULT = "column-count";
  var NO_SHEET_SOURCE_FAULT = "no-sheet-source";

  var NO_BRIDGE = "the preload bridge is not present";

  var EMPTY = "";
  var PATH_SPLIT = ".";
  var HASH = "#";
  var GAP = " ";
  var COLON = ":";
  var SEMICOLON = ";";
  var COMMA = ",";
  var DOT = ".";
  var PERCENT = "%";
  var CLOSE = ")";
  var PX = "px";
  var PT = "pt";
  var RGBA_OPEN = "rgba(";
  // Qt reads an eight-digit hex alpha first, CSS reads it last.
  var HEX_ARGB = "AARRGGBB";


  var PADDING_SIDES = [
    "paddingLeft",
    "paddingTop",
    "paddingRight",
    "paddingBottom"
  ];

  var OBJECT_KIND = "object";
  var STRING_KIND = "string";

  var FLEX = "flex";
  var ROW_WAY = "row";
  var COLUMN_WAY = "column";
  var FLEX_NONE = "none";
  var AUTO = "auto";
  var NO_WRAP = "nowrap";
  var CLIPPED = "hidden";
  var ELLIPSIS = "ellipsis";
  var NO_SELECT = "none";
  var RELATIVE = "relative";
  var ABSOLUTE = "absolute";
  var RADIUS_HALF = "50%";
  var FULL = "100%";
  var MIN_CONTENT = "min-content";
  var COLLAPSE = "collapse";
  var ZERO = Number(EMPTY);
  var ONE = Number(true);
  var TWO = ONE + ONE;
  var THREE = TWO + ONE;
  var FOUR = TWO + TWO;
  var EIGHT = FOUR + FOUR;
  // HALF puts a one-pixel stroke on the pixel centre, as Qt's painter does.
  var HALF = Math.pow(TWO, -ONE);
  // BYTE_STEP turns the alpha Qt counts in bytes into the fraction CSS reads.
  var BYTE_STEP = Math.pow(Math.pow(TWO, EIGHT) - ONE, -ONE);

  var DIV_TAG = "div";
  var SPAN_TAG = "span";
  var TABLE_TAG = "table";
  var HEAD_TAG = "thead";
  var BODY_TAG = "tbody";
  var TR_TAG = "tr";
  var TH_TAG = "th";
  var TD_TAG = "td";

  var VISUALS_PART = "visuals";
  var PANE_PART = "pane";
  var PANE_SCROLL_PART = "pane-scroll";
  var PANE_HOST_PART = "pane-host";
  var PANE_EMPTY_PART = "pane-empty";
  var PANE_ROW_PART = "pane-row";
  var PANE_LABEL_PART = "pane-label";
  var PANE_STRETCH_PART = "pane-stretch";
  var LAMP_ROW_PART = "lamp-row";
  var LAMP_PART = "lamp";
  var LAMP_LABEL_PART = "lamp-label";
  var BANK_MARKER_PART = "bank-marker";
  var CHART_MOUNT_PART = "chart-mount";
  var VOTE_TABLE_PART = "vote-table";
  var VOTE_GRID_PART = "vote-grid";
  var VOTE_HEAD_PART = "vote-head";
  var VOTE_HEAD_ROW_PART = "vote-head-row";
  var VOTE_HEAD_CELL_PART = "vote-head-cell";
  var VOTE_BODY_PART = "vote-body";
  var VOTE_ROW_PART = "vote-row";
  var VOTE_CELL_PART = "vote-cell";
  var VOTE_STUB_PART = "vote-stub";
  var EXPAND_PART = "expand";

  var PANE_SLOT = "gate-status-panel";
  var CHART_SLOT = "sim-price-chart";
  var VOTES_SLOT = "indicator-voting-panel";

  var PART_ATTR = "data-part";
  var SLOT_ATTR = "data-slot";
  var KIND_ATTR = "data-kind";
  var SYMBOL_ATTR = "data-symbol";
  var BANK_ATTR = "data-bank";
  var LABEL_ATTR = "data-label";
  var STATE_ATTR = "data-state";
  var AT_ATTR = "data-at";
  var COLUMN_ATTR = "data-column";
  var LAMPS_ATTR = "data-lamps";
  var OPS_ATTR = "data-ops";
  var FOCUS_ATTR = "data-focus";
  var ROWS_ATTR = "data-rows";
  var OPEN_ATTR = "data-open";
  var CLAIM_ATTR = "data-claim";
  var ARIA_LABEL = "aria-label";
  var ARIA_DESCRIPTION = "aria-description";
  var TITLE_ATTR = "title";

  var held = null;
  var visualFaults = [];
  var loadFault = null;
  var asked = null;
  var roots = [];

  function isPlainObject(value) {
    return value !== null && typeof value === "object" && !Array.isArray(value);
  }

  function owns(bag, name) {
    return Object.prototype.hasOwnProperty.call(bag, name);
  }

  function isNumber(value) {
    return typeof value === "number" && isFinite(value);
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

  function kindOf(value) {
    if (value === null) {
      return NULL_FAULT;
    }
    return Array.isArray(value) ? OBJECT_KIND : typeof value;
  }

  function fault(where, field, kind, detail) {
    return { where: where, field: field, fault: kind, detail: detail };
  }

  function note(where, field, kind, detail) {
    visualFaults.push(fault(where, field, kind, detail));
  }

  // text answers undefined so an attribute stays off the element.
  function text(value) {
    return value === null || value === undefined ? undefined : String(value);
  }

  function element() {
    return global.React.createElement.apply(null, arguments);
  }

  function afterFirst(value, splitter) {
    var parts = String(value).split(splitter);
    parts.shift();
    return parts;
  }

  function carries(value, splitter) {
    return Boolean(afterFirst(value, splitter).length);
  }

  // sheetApi finds acervatorHeader, which owns the Qt sheet grammar.
  function sheetApi() {
    var api = global.acervatorHeader;
    if (!api || typeof api.styleOf !== "function") {
      return undefined;
    }
    return api;
  }

  function declarations(sheet) {
    var api = sheetApi();
    return api === undefined ? [] : api.declarations(sheet);
  }

  function stateRules(sheet) {
    var api = sheetApi();
    return api === undefined ? [] : api.stateRules(sheet);
  }

  // The first hex word of one value, empty when it carries none.
  function hexWord(value) {
    var parts = afterFirst(value, HASH);
    if (!parts.length) {
      return EMPTY;
    }
    return String(parts.shift()).trim().split(GAP).shift();
  }

  // byteAlpha answers true for an alpha Qt counts in bytes.
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
    return byteAlpha(value) ? RGBA_OPEN : undefined;
  }

  // A sheet without the declarations CSS would read as another colour.
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
    var api = sheetApi();
    return api === undefined ? {} : api.styleOf(keptSheet(sheet));
  }

  // The only state rule of one sheet, undefined when it carries no single one.
  function loneStateRule(sheet) {
    var found = stateRules(sheet);
    return found.length === ONE ? found.shift() : undefined;
  }

  function stateStyle(sheet) {
    var rule = loneStateRule(sheet);
    return rule === undefined ? {} : styleOf(rule.body);
  }

  function variableFor(value) {
    var api = global.acervatorWidgets;
    if (!api || typeof api.variableFor !== "function") {
      return undefined;
    }
    return api.variableFor(value);
  }

  // Plain pixels: the one token carrying a size here means a corner radius.
  function pixels(value) {
    if (value === null || value === undefined) {
      return undefined;
    }
    return String(value) + PX;
  }

  // A points value takes no token, because every token group counts pixels.
  function points(value) {
    if (value === null || value === undefined) {
      return undefined;
    }
    return String(value) + PT;
  }

  // Plain paint, because each token carrying a colour value here means an error.
  function colour(value) {
    if (value === null || value === undefined || qtColour(value) !== undefined) {
      return undefined;
    }
    return String(value);
  }

  function marginStyle(bag, field) {
    var style = {};
    var margins = listField(bag, field);
    PADDING_SIDES.forEach(function (side, at) {
      if (at < margins.length) {
        style[side] = pixels(margins[at]);
      }
    });
    return style;
  }

  function boxStyle(bag, marginField, spacingField, way) {
    var style = marginStyle(bag, marginField);
    style.display = FLEX;
    style.flexDirection = way;
    if (owns(bag, spacingField)) {
      style.gap = pixels(bag[spacingField]);
    }
    return style;
  }

  // asLabel cuts one text the way a Qt QLabel cuts it, never wrapping.
  function asLabel(style) {
    style.whiteSpace = NO_WRAP;
    style.overflow = CLIPPED;
    style.textOverflow = ELLIPSIS;
    style.userSelect = NO_SELECT;
    return style;
  }

  function merged(into, from) {
    Object.keys(from).forEach(function (name) {
      into[name] = from[name];
    });
    return into;
  }


  // Lamp draws one light of one bank as the program places it.
  function Lamp(props) {
    var style = {
      position: ABSOLUTE,
      left: pixels(props.box.left),
      top: pixels(props.box.top),
      width: pixels(props.box.width),
      height: pixels(props.box.height),
      borderRadius: RADIUS_HALF,
      backgroundColor: colour(props.paint)
    };
    var lampProps = { style: style };
    lampProps[PART_ATTR] = LAMP_PART;
    lampProps[BANK_ATTR] = text(props.bank);
    lampProps[LABEL_ATTR] = text(props.label);
    lampProps[STATE_ATTR] = text(props.state);
    lampProps[AT_ATTR] = text(props.at);
    return element(DIV_TAG, lampProps, null);
  }

  // Caption draws one text of the program inside the rectangle it names.
  function Caption(props) {
    var style = {
      position: ABSOLUTE,
      left: pixels(props.box.left),
      top: pixels(props.box.top),
      width: pixels(props.box.width),
      height: pixels(props.box.height),
      display: FLEX,
      color: colour(props.paint),
      fontSize: points(props.size)
    };
    asLabel(style);
    merged(style, ALIGNMENT[props.align] || {});
    var captionProps = { style: style };
    captionProps[PART_ATTR] = props.part;
    captionProps[BANK_ATTR] = text(props.bank);
    captionProps[LABEL_ATTR] = text(props.label);
    captionProps[AT_ATTR] = text(props.at);
    return element(DIV_TAG, captionProps, text(props.words));
  }

  function boxOf(op) {
    var box = listField(op, RECT).slice();
    return {
      left: box.shift(),
      top: box.shift(),
      width: box.shift(),
      height: box.shift()
    };
  }

  // LampRow replays one row's program, taking each light's name in turn.
  function LampRow(props) {
    var row = props.row;
    var chrome = props.chrome;
    var pending = listField(row, LIGHTS).slice();
    var taken = [];
    var drawn = [];
    listField(row, PROGRAM).forEach(function (op, at) {
      if (!isPlainObject(op)) {
        return;
      }
      var next = pending.length ? pending[ZERO] : {};
      if (op[OP] === OP_ELLIPSE) {
        drawn.push(
          element(Lamp, {
            key: String(at),
            box: boxOf(op),
            paint: op[BRUSH],
            bank: next[BANK],
            label: next[LABEL],
            state: next[STATE],
            at: String(taken.length)
          })
        );
        taken.push(pending.shift());
        return;
      }
      if (op[OP] !== OP_TEXT) {
        return;
      }
      var marker = op[PEN] === chrome[MARKER_COLOUR];
      drawn.push(
        element(Caption, {
          key: String(at),
          part: marker ? BANK_MARKER_PART : LAMP_LABEL_PART,
          box: boxOf(op),
          paint: op[PEN],
          size: chrome[FONT_PT],
          align: op[ALIGN],
          words: op[TEXT_FIELD],
          bank: marker ? op[TEXT_FIELD] : next[BANK],
          label: marker ? undefined : next[LABEL],
          at: marker ? undefined : String(taken.length)
        })
      );
    });
    var rowProps = {
      style: {
        position: RELATIVE,
        flex: FLEX_NONE,
        height: pixels(chrome[HEIGHT_PX]),
        minWidth: pixels(chrome[MIN_WIDTH_PX])
      }
    };
    rowProps[PART_ATTR] = LAMP_ROW_PART;
    rowProps[SYMBOL_ATTR] = text(props.symbol);
    rowProps[LAMPS_ATTR] = String(taken.length);
    rowProps[TITLE_ATTR] = text(chrome[TOOLTIP]);
    return element(DIV_TAG, rowProps, drawn);
  }

  // PaneRow puts one symbol's name beside that symbol's lights.
  function PaneRow(props) {
    var pane = props.pane;
    var style = boxStyle(pane, ROW_MARGINS_PX, ROW_SPACING_PX, ROW_WAY);
    style.flex = FLEX_NONE;
    var rowProps = { style: style };
    rowProps[PART_ATTR] = PANE_ROW_PART;
    rowProps[KIND_ATTR] = KIND_ROW;
    rowProps[SYMBOL_ATTR] = text(props.symbol);

    var labelStyle = asLabel(styleOf(pane[LABEL_STYLE]));
    labelStyle.minWidth = pixels(pane[LABEL_MIN_WIDTH_PX]);
    labelStyle.flex = FLEX_NONE;
    var labelProps = { style: labelStyle };
    labelProps[PART_ATTR] = PANE_LABEL_PART;

    var spacerProps = { style: { flex: AUTO } };
    spacerProps[PART_ATTR] = PANE_STRETCH_PART;
    return element(
      DIV_TAG,
      rowProps,
      element(SPAN_TAG, labelProps, text(props.symbol)),
      element(LampRow, {
        symbol: props.symbol,
        row: props.row,
        chrome: props.chrome
      }),
      element(DIV_TAG, spacerProps, null)
    );
  }

  function paneItemNode(model, item, at) {
    var pane = objectField(model, PANE);
    var chrome = objectField(model, ROW);
    if (!isPlainObject(item) || !owns(DRAWN_KINDS, item[KIND])) {
      return null;
    }
    if (item[KIND] === KIND_EMPTY) {
      var emptyStyle = asLabel(styleOf(pane[EMPTY_STYLE]));
      emptyStyle.flex = FLEX_NONE;
      var emptyProps = { key: String(at), style: emptyStyle };
      emptyProps[PART_ATTR] = PANE_EMPTY_PART;
      emptyProps[KIND_ATTR] = KIND_EMPTY;
      emptyProps.hidden = item[VISIBLE] !== true;
      return element(DIV_TAG, emptyProps, text(pane[EMPTY_TEXT]));
    }
    if (item[KIND] === KIND_STRETCH) {
      var stretchProps = { key: String(at), style: { flex: AUTO } };
      stretchProps[PART_ATTR] = PANE_STRETCH_PART;
      stretchProps[KIND_ATTR] = KIND_STRETCH;
      return element(DIV_TAG, stretchProps, null);
    }
    return element(PaneRow, {
      key: String(at),
      pane: pane,
      chrome: chrome,
      symbol: item[SYMBOL],
      row: objectField(chrome, ROWS)[item[SYMBOL]]
    });
  }

  // Pane draws the scrollable column of one labelled row per symbol.
  function Pane(props) {
    if (!isPlainObject(props.model)) {
      return null;
    }
    var model = props.model;
    var pane = objectField(model, PANE);
    var outerStyle = boxStyle(pane, MARGINS_PX, SPACING_PX, COLUMN_WAY);
    outerStyle.flex = AUTO;
    outerStyle.overflow = CLIPPED;
    var outerProps = { style: outerStyle };
    outerProps[PART_ATTR] = PANE_PART;
    outerProps[SLOT_ATTR] = PANE_SLOT;
    outerProps[ARIA_LABEL] = text(pane[ACCESSIBLE_NAME]);

    var scrollStyle = styleOf(pane[SCROLL_STYLE]);
    scrollStyle.flex = AUTO;
    scrollStyle.overflow = pane[SCROLL_RESIZABLE] === true ? AUTO : CLIPPED;
    var scrollProps = { style: scrollStyle };
    scrollProps[PART_ATTR] = PANE_SCROLL_PART;

    var hostStyle = boxStyle(pane, HOST_MARGINS_PX, HOST_SPACING_PX, COLUMN_WAY);
    hostStyle.minHeight = FULL;
    var hostProps = { style: hostStyle };
    hostProps[PART_ATTR] = PANE_HOST_PART;

    return element(
      DIV_TAG,
      outerProps,
      element(
        DIV_TAG,
        scrollProps,
        element(
          DIV_TAG,
          hostProps,
          listField(pane, ITEMS).map(function (item, at) {
            return paneItemNode(model, item, at);
          })
        )
      )
    );
  }

  // paintOn is the surface's draw program executed on a 2D context.
  function paintOn(surface, program) {
    program.forEach(function (step) {
      var box = listField(step, RECT);
      var ends = listField(step, LINE_FIELD);
      surface.lineWidth = isNumber(step[WIDTH_FIELD]) ? step[WIDTH_FIELD] : ONE;
      surface.setLineDash(step[STYLE_FIELD] === DASH_LINE ? [FOUR, THREE] : []);
      surface.strokeStyle = brushText(step[PEN]);
      surface.fillStyle = brushText(step[BRUSH]);
      if (step[OP] === OP_LINE && ends.length === FOUR) {
        surface.beginPath();
        surface.moveTo(ends[ZERO] + HALF, ends[ONE] + HALF);
        surface.lineTo(ends[TWO] + HALF, ends[THREE] + HALF);
        surface.stroke();
        return;
      }
      if (box.length !== FOUR) {
        return;
      }
      if (step[OP] === OP_FILL) {
        surface.fillRect(box[ZERO], box[ONE], box[TWO], box[THREE]);
        return;
      }
      if (step[OP] === OP_RECT) {
        paintShape(surface, step, function () {
          surface.rect(box[ZERO] + HALF, box[ONE] + HALF, box[TWO], box[THREE]);
        });
        return;
      }
      if (step[OP] === OP_ELLIPSE) {
        paintShape(surface, step, function () {
          surface.ellipse(
            box[ZERO] + box[TWO] * HALF,
            box[ONE] + box[THREE] * HALF,
            Math.max(box[TWO] * HALF, HALF),
            Math.max(box[THREE] * HALF, HALF),
            ZERO,
            ZERO,
            TWO * Math.PI
          );
        });
        return;
      }
      if (step[OP] === OP_TEXT) {
        paintText(surface, step, box);
      }
    });
  }

  // brushText answers a CSS colour for a name, an rgba list, or "none".
  function brushText(value) {
    if (Array.isArray(value)) {
      var parts = value.slice();
      var alpha = parts.length === FOUR ? parts.pop() * BYTE_STEP : ONE;
      return RGBA_OPEN + parts.join(COMMA) + COMMA + alpha + CLOSE;
    }
    return value === NO_PAINT || value === undefined ? TRANSPARENT : String(value);
  }

  function paintShape(surface, step, trace) {
    surface.beginPath();
    trace();
    if (step[BRUSH] !== NO_PAINT && step[BRUSH] !== undefined) {
      surface.fill();
    }
    if (step[PEN] !== NO_PAINT && step[PEN] !== undefined) {
      surface.stroke();
    }
  }

  // paintText places one label in its box, on the alignment the surface named.
  function paintText(surface, step, box) {
    var written = String(step[TEXT_FIELD] === undefined ? EMPTY : step[TEXT_FIELD]);
    var at = listField(step, AT_FIELD);
    surface.fillStyle = brushText(step[PEN]);
    surface.textBaseline = MIDDLE;
    if (at.length === TWO) {
      surface.textAlign = LEFT;
      surface.fillText(written, at[ZERO], at[ONE]);
      return;
    }
    if (box.length !== FOUR) {
      return;
    }
    var middle = box[ONE] + box[THREE] * HALF;
    if (step[ALIGN] === ALIGN_LABEL) {
      surface.textAlign = CENTER;
      surface.fillText(written, box[ZERO] + box[TWO] * HALF, middle);
      return;
    }
    if (step[ALIGN] === ALIGN_MARKER) {
      surface.textAlign = RIGHT;
      surface.fillText(written, box[ZERO] + box[TWO], middle);
      return;
    }
    surface.textAlign = LEFT;
    surface.fillText(written, box[ZERO], middle);
  }

  // chartCanvas sizes the canvas to its box and repaints it from the program.
  function chartCanvas(node, program) {
    if (node === null || typeof node.getContext !== FUNCTION_KIND) {
      return null;
    }
    node.width = Math.max(node.clientWidth || node.parentNode.clientWidth, ONE);
    node.height = Math.max(node.clientHeight || node.parentNode.clientHeight, ONE);
    var surface = node.getContext(CONTEXT_2D, READ_BACK);
    if (surface === null) {
      return null;
    }
    surface.clearRect(ZERO, ZERO, node.width, node.height);
    paintOn(surface, program);
    return node;
  }

  // ChartMount frames the chart and paints its program onto one canvas.
  function ChartMount(props) {
    if (!isPlainObject(props.model)) {
      return null;
    }
    var chart = objectField(props.model, CHART);
    var policy = listField(chart, SIZE_POLICY).slice();
    var across = policy.shift();
    var down = policy.shift();
    var style = styleOf(chart[STYLE_SHEET]);
    style.display = FLEX;
    style.flexDirection = COLUMN_WAY;
    style.minHeight = pixels(chart[MINIMUM_HEIGHT_PX]);
    style.flexGrow = down === POLICY_EXPANDING ? ONE : ZERO;
    style.width = across === POLICY_EXPANDING ? FULL : MIN_CONTENT;
    style.overflow = CLIPPED;
    var mountProps = { style: style };
    var program = listField(chart, PROGRAM);
    mountProps[PART_ATTR] = CHART_MOUNT_PART;
    mountProps[SLOT_ATTR] = CHART_SLOT;
    mountProps[ARIA_LABEL] = text(chart[ACCESSIBLE_NAME]);
    mountProps[ARIA_DESCRIPTION] = text(chart[ACCESSIBLE_DESCRIPTION]);
    mountProps[TITLE_ATTR] = text(chart[TOOLTIP]);
    mountProps[FOCUS_ATTR] = text(chart[FOCUS]);
    mountProps[OPS_ATTR] = String(program.length);
    var canvasProps = {
      style: { display: BLOCK, width: FULL, flexGrow: ONE, minHeight: ZERO },
      ref: function (node) {
        chartCanvas(node, program);
      }
    };
    canvasProps[PART_ATTR] = CHART_CANVAS_PART;
    return element(DIV_TAG, mountProps, element(CANVAS_TAG, canvasProps));
  }

  // toContents narrows the first column, which Qt sizes to its own text.
  function toContents(votes, style, at) {
    if (at === ZERO && votes[SYMBOL_COLUMN_MODE] === MODE_TO_CONTENTS) {
      style.width = MIN_CONTENT;
    }
    return style;
  }

  function headCellNode(votes, headStyle, name, at) {
    var style = toContents(votes, asLabel(copyOf(headStyle)), at);
    style.height = pixels(votes[HEADER_HEIGHT_PX]);
    var cellProps = { key: String(at), style: style };
    cellProps[PART_ATTR] = VOTE_HEAD_CELL_PART;
    cellProps[COLUMN_ATTR] = text(name);
    cellProps[AT_ATTR] = String(at);
    return element(TH_TAG, cellProps, text(name));
  }

  function bodyCellNode(votes, row, columns, one, at) {
    var style = toContents(votes, asLabel({}), at);
    style.height = pixels(votes[ROW_HEIGHT_PX]);
    if (at === columns.length - ONE) {
      style.color = colour(row[DIRECTION_COLOUR]);
    }
    var cellProps = { key: String(at), style: style };
    cellProps[PART_ATTR] = VOTE_CELL_PART;
    cellProps[COLUMN_ATTR] = text(columns[at]);
    cellProps[AT_ATTR] = String(at);
    return element(TD_TAG, cellProps, text(one));
  }

  // ordinalNode draws the numbered stub Qt shows only with row headers on.
  function ordinalNode(votes, at) {
    if (votes[ROW_HEADER_VISIBLE] !== true) {
      return null;
    }
    var stubProps = { key: ROW_HEADER_VISIBLE, style: asLabel({}) };
    stubProps[PART_ATTR] = VOTE_STUB_PART;
    return element(TH_TAG, stubProps, String(at + ONE));
  }

  function bodyRowNode(votes, columns, alternate, row, at) {
    var style = { height: pixels(votes[ROW_HEIGHT_PX]) };
    if (votes[ALTERNATING_ROWS] === true && at % TWO === ONE) {
      style.backgroundColor = colour(alternate);
    }
    var rowProps = { key: String(at), style: style };
    rowProps[PART_ATTR] = VOTE_ROW_PART;
    rowProps[AT_ATTR] = String(at);
    return element(
      TR_TAG,
      rowProps,
      ordinalNode(votes, at),
      listField(row, CELLS).map(function (one, column) {
        return bodyCellNode(votes, row, columns, one, column);
      })
    );
  }

  // VoteTable draws one row per bot under the columns the surface names.
  function VoteTable(props) {
    if (!isPlainObject(props.model)) {
      return null;
    }
    var votes = objectField(props.model, VOTES);
    var columns = listField(votes, COLUMNS);
    var rows = listField(votes, ROWS);
    var style = styleOf(votes[STYLE_SHEET]);
    style.overflow = AUTO;
    style.display = FLEX;
    style.flexDirection = COLUMN_WAY;
    var frameProps = { style: style, tabIndex: ZERO };
    frameProps[PART_ATTR] = VOTE_TABLE_PART;
    frameProps[SLOT_ATTR] = VOTES_SLOT;
    frameProps[ARIA_LABEL] = text(votes[ACCESSIBLE_NAME]);
    frameProps[ARIA_DESCRIPTION] = text(votes[ACCESSIBLE_DESCRIPTION]);
    frameProps[TITLE_ATTR] = text(votes[TOOLTIP]);
    frameProps[ROWS_ATTR] = String(rows.length);

    var gridProps = {
      style: { width: FULL, borderCollapse: COLLAPSE, tableLayout: AUTO }
    };
    gridProps[PART_ATTR] = VOTE_GRID_PART;

    var headStyle = stateStyle(votes[STYLE_SHEET]);
    var headProps = {};
    headProps[PART_ATTR] = VOTE_HEAD_PART;
    var headRowProps = {};
    headRowProps[PART_ATTR] = VOTE_HEAD_ROW_PART;
    var bodyProps = {};
    bodyProps[PART_ATTR] = VOTE_BODY_PART;
    var alternate = votes[ALTERNATE_ROW_COLOUR];
    return element(
      DIV_TAG,
      frameProps,
      element(
        TABLE_TAG,
        gridProps,
        element(
          HEAD_TAG,
          headProps,
          element(
            TR_TAG,
            headRowProps,
            columns.map(function (name, at) {
              return headCellNode(votes, headStyle, name, at);
            })
          )
        ),
        element(
          BODY_TAG,
          bodyProps,
          rows.map(function (row, at) {
            return bodyRowNode(votes, columns, alternate, row, at);
          })
        )
      )
    );
  }

  // ExpandFrame is the framed host one pane moves into while it is enlarged.
  function ExpandFrame(props) {
    if (!isPlainObject(props.model)) {
      return null;
    }
    var expand = objectField(props.model, EXPAND);
    var style = styleOf(expand[STYLE_SHEET]);
    merged(style, marginStyle(expand, MARGINS_PX));
    style.display = FLEX;
    style.flexDirection = COLUMN_WAY;
    var frameProps = { style: style, hidden: expand[OPEN] !== true };
    frameProps[PART_ATTR] = EXPAND_PART;
    frameProps[OPEN_ATTR] = String(expand[OPEN] === true);
    frameProps[CLAIM_ATTR] = text(expand[CLAIM_FIELD]);
    return element(DIV_TAG, frameProps, null);
  }

  // Visuals draws the pane, the chart's host, the table and the frame.
  function Visuals(props) {
    if (!isPlainObject(props.model)) {
      return null;
    }
    var screenProps = {
      style: { display: FLEX, flexDirection: COLUMN_WAY }
    };
    screenProps[PART_ATTR] = VISUALS_PART;
    return element(
      DIV_TAG,
      screenProps,
      element(Pane, { key: PANE_SLOT, model: props.model }),
      element(ChartMount, { key: CHART_SLOT, model: props.model }),
      element(VoteTable, { key: VOTES_SLOT, model: props.model }),
      element(ExpandFrame, { key: EXPAND_PART, model: props.model })
    );
  }


  function checkPresent(where, bag, names) {
    names.forEach(function (name) {
      if (!owns(bag, name)) {
        note(where, name, MISSING_FAULT, null);
        return;
      }
      if (bag[name] === null) {
        note(where, name, NULL_FAULT, null);
      }
    });
  }

  function checkTopFields(model) {
    checkPresent(null, model, DECLARED_FIELDS);
    [PANE, ROW, CHART, VOTES, EXPAND].forEach(function (name) {
      if (owns(model, name) && !isPlainObject(model[name])) {
        note(name, name, NOT_AN_OBJECT_FAULT, kindOf(model[name]));
      }
    });
  }

  // checkAgainst holds one value against the type of a published default.
  function checkAgainst(where, field, value, wanted) {
    if (wanted === undefined) {
      return;
    }
    if (kindOf(value) !== kindOf(wanted)) {
      note(where, field, WRONG_TYPE_FAULT, kindOf(value));
    }
  }

  // WANTED_LISTS names every field this module walks as a list.
  var WANTED_LISTS = {};
  WANTED_LISTS[PANE] = [ITEMS, SYMBOLS, MARGINS_PX, HOST_MARGINS_PX, ROW_MARGINS_PX];
  WANTED_LISTS[CHART] = [PROGRAM, SYMBOLS, SIZE_POLICY];
  WANTED_LISTS[VOTES] = [ROWS, COLUMNS];
  WANTED_LISTS[EXPAND] = [MARGINS_PX];

  // WANTED_BAGS names every field this module walks by its own key names.
  var WANTED_BAGS = {};
  WANTED_BAGS[ROW] = [ROWS, BANKS, LIGHT_COLOURS];

  // checkShapes refuses a scalar standing where a list or a bag is walked.
  function checkShapes(model) {
    Object.keys(WANTED_LISTS).forEach(function (panel) {
      var bag = objectField(model, panel);
      WANTED_LISTS[panel].forEach(function (name) {
        if (owns(bag, name) && !Array.isArray(bag[name])) {
          note(panel, name, NOT_A_LIST_FAULT, kindOf(bag[name]));
        }
      });
    });
    Object.keys(WANTED_BAGS).forEach(function (panel) {
      var bag = objectField(model, panel);
      WANTED_BAGS[panel].forEach(function (name) {
        if (owns(bag, name) && !isPlainObject(bag[name])) {
          note(panel, name, NOT_AN_OBJECT_FAULT, kindOf(bag[name]));
        }
      });
    });
  }

  function checkPane(model) {
    var pane = objectField(model, PANE);
    checkPresent(PANE, pane, PANE_FIELDS);
    var wanted = objectField(model, CHART)[FOCUS];
    listField(pane, SYMBOLS).forEach(function (one, at) {
      checkAgainst(PANE + PATH_SPLIT + String(at), SYMBOLS, one, wanted);
    });
    listField(pane, ITEMS).forEach(function (item, at) {
      var where = PANE + PATH_SPLIT + String(at);
      if (!isPlainObject(item)) {
        note(where, ITEMS, NOT_AN_OBJECT_FAULT, kindOf(item));
        return;
      }
      if (!owns(DRAWN_KINDS, item[KIND])) {
        note(where, KIND, UNKNOWN_KIND_FAULT, kindOf(item[KIND]));
        return;
      }
      if (item[KIND] !== KIND_ROW) {
        return;
      }
      checkAgainst(where, SYMBOL, item[SYMBOL], wanted);
      if (!owns(objectField(objectField(model, ROW), ROWS), item[SYMBOL])) {
        note(where, SYMBOL, UNKNOWN_SYMBOL_FAULT, text(item[SYMBOL]));
      }
    });
  }

  // declaredLamps names every light the two banks declare, in draw order.
  function declaredLamps(chrome) {
    var wanted = [];
    var banks = objectField(chrome, BANKS);
    Object.keys(banks).forEach(function (name) {
      listField(banks, name).forEach(function (one) {
        wanted.push({ bank: name, label: one });
      });
    });
    return wanted;
  }

  function checkLampOrder(where, chrome, row) {
    var wanted = declaredLamps(chrome);
    var carried = listField(row, LIGHTS);
    if (carried.length !== wanted.length) {
      note(where, LIGHTS, LAMP_COUNT_FAULT, carried.length);
    }
    wanted.forEach(function (one, at) {
      var lamp = at < carried.length ? carried[at] : {};
      if (!isPlainObject(lamp)) {
        note(where + PATH_SPLIT + String(at), LIGHTS, NOT_AN_OBJECT_FAULT, kindOf(lamp));
        return;
      }
      if (lamp[BANK] !== one.bank || lamp[LABEL] !== one.label) {
        note(
          where + PATH_SPLIT + String(at),
          LIGHTS,
          LAMP_ORDER_FAULT,
          text(lamp[BANK]) + PATH_SPLIT + text(lamp[LABEL])
        );
      }
    });
  }

  // checkLampPaint holds each light's colour against the state it declares.
  function checkLampPaint(where, chrome, row) {
    var byState = objectField(chrome, LIGHT_COLOURS);
    listField(row, LIGHTS).forEach(function (lamp, at) {
      if (!isPlainObject(lamp)) {
        return;
      }
      checkPresent(where + PATH_SPLIT + String(at), lamp, LIGHT_FIELDS);
      if (!owns(byState, lamp[STATE])) {
        note(where + PATH_SPLIT + String(at), STATE, UNKNOWN_KIND_FAULT, text(lamp[STATE]));
        return;
      }
      if (byState[lamp[STATE]] !== lamp[COLOUR]) {
        note(
          where + PATH_SPLIT + String(at),
          COLOUR,
          LAMP_COLOUR_FAULT,
          text(lamp[COLOUR])
        );
      }
    });
  }

  // checkLampProgram walks the program beside the lights it names.
  function checkLampProgram(where, chrome, row) {
    var pending = listField(row, LIGHTS).slice();
    listField(row, PROGRAM).forEach(function (op, at) {
      if (!isPlainObject(op)) {
        note(where + PATH_SPLIT + String(at), PROGRAM, NOT_AN_OBJECT_FAULT, kindOf(op));
        return;
      }
      var next = pending.length ? pending[ZERO] : {};
      if (op[OP] === OP_ELLIPSE) {
        if (op[BRUSH] !== next[COLOUR]) {
          note(where + PATH_SPLIT + String(at), BRUSH, LAMP_COLOUR_FAULT, text(op[BRUSH]));
        }
        pending.shift();
        return;
      }
      if (op[OP] === OP_TEXT && op[PEN] === chrome[LABEL_COLOUR]) {
        if (op[TEXT_FIELD] !== next[LABEL]) {
          note(
            where + PATH_SPLIT + String(at),
            TEXT_FIELD,
            LAMP_LABEL_FAULT,
            text(op[TEXT_FIELD])
          );
        }
      }
    });
    if (pending.length) {
      note(where, PROGRAM, LAMP_COUNT_FAULT, pending.length);
    }
  }

  function checkRows(model) {
    var chrome = objectField(model, ROW);
    checkPresent(ROW, chrome, ROW_FIELDS);
    var rows = objectField(chrome, ROWS);
    Object.keys(rows).forEach(function (name) {
      var where = ROW + PATH_SPLIT + name;
      var row = rows[name];
      if (!isPlainObject(row)) {
        note(where, ROWS, NOT_AN_OBJECT_FAULT, kindOf(row));
        return;
      }
      if (!Array.isArray(row[LIGHTS])) {
        note(where, LIGHTS, NOT_A_LIST_FAULT, kindOf(row[LIGHTS]));
      }
      if (!Array.isArray(row[PROGRAM])) {
        note(where, PROGRAM, NOT_A_LIST_FAULT, kindOf(row[PROGRAM]));
      }
      checkLampOrder(where, chrome, row);
      checkLampPaint(where, chrome, row);
      checkLampProgram(where, chrome, row);
    });
  }

  function checkChart(model) {
    var chart = objectField(model, CHART);
    checkPresent(CHART, chart, CHART_FIELDS);
    var wanted = chart[FOCUS];
    listField(chart, SYMBOLS).forEach(function (one, at) {
      checkAgainst(CHART + PATH_SPLIT + String(at), SYMBOLS, one, wanted);
    });
    listField(chart, PROGRAM).forEach(function (op, at) {
      var where = CHART + PATH_SPLIT + String(at);
      if (!isPlainObject(op)) {
        note(where, PROGRAM, NOT_AN_OBJECT_FAULT, kindOf(op));
        return;
      }
      if (!owns(op, OP)) {
        note(where, OP, MISSING_FAULT, null);
      }
    });
  }

  function checkVotes(model) {
    var votes = objectField(model, VOTES);
    checkPresent(VOTES, votes, VOTE_FIELDS);
    var columns = listField(votes, COLUMNS);
    var wanted = votes[PLACEHOLDER];
    if (votes[COLUMN_MODE] !== MODE_STRETCH) {
      note(VOTES, COLUMN_MODE, UNKNOWN_MODE_FAULT, text(votes[COLUMN_MODE]));
    }
    if (votes[SYMBOL_COLUMN_MODE] !== MODE_TO_CONTENTS) {
      note(VOTES, SYMBOL_COLUMN_MODE, UNKNOWN_MODE_FAULT, text(votes[SYMBOL_COLUMN_MODE]));
    }
    if (votes[EDIT_TRIGGERS] !== NO_EDIT_TRIGGERS) {
      note(VOTES, EDIT_TRIGGERS, UNKNOWN_MODE_FAULT, text(votes[EDIT_TRIGGERS]));
    }
    if (votes[SELECTION_BEHAVIOUR] !== SELECT_ROWS) {
      note(VOTES, SELECTION_BEHAVIOUR, UNKNOWN_MODE_FAULT, text(votes[SELECTION_BEHAVIOUR]));
    }
    listField(votes, ROWS).forEach(function (row, at) {
      var where = VOTES + PATH_SPLIT + String(at);
      if (!isPlainObject(row)) {
        note(where, ROWS, NOT_AN_OBJECT_FAULT, kindOf(row));
        return;
      }
      if (!Array.isArray(row[CELLS])) {
        note(where, CELLS, NOT_A_LIST_FAULT, kindOf(row[CELLS]));
      }
      if (listField(row, CELLS).length !== columns.length) {
        note(where, CELLS, COLUMN_COUNT_FAULT, listField(row, CELLS).length);
      }
      listField(row, CELLS).forEach(function (one, column) {
        checkAgainst(where + PATH_SPLIT + String(column), CELLS, one, wanted);
      });
      if (row[DIRECTION_COLOUR] !== null && row[DIRECTION_COLOUR] !== undefined) {
        checkAgainst(where, DIRECTION_COLOUR, row[DIRECTION_COLOUR], wanted);
      }
    });
  }

  function checkExpand(model) {
    checkPresent(EXPAND, objectField(model, EXPAND), EXPAND_FIELDS);
  }

  // paints answers whether one declaration survives into a CSS style.
  function paints(one) {
    var alone = String(one.property) + COLON + GAP + String(one.value);
    return Boolean(Object.keys(styleOf(alone)).length);
  }

  function checkSheet(where, field, sheet) {
    declarations(sheet).forEach(function (one) {
      if (qtColour(one.value) !== undefined) {
        note(where, field, QT_COLOUR_FAULT, one.property);
        return;
      }
      if (!paints(one)) {
        note(where, field, NOT_CSS_FAULT, one.property);
      }
    });
    stateRules(sheet).forEach(function (block) {
      declarations(block.body).forEach(function (one) {
        if (qtColour(one.value) !== undefined) {
          note(where, field, QT_COLOUR_FAULT, one.property);
        }
      });
    });
  }

  function checkColour(where, field, value) {
    if (typeof value !== STRING_KIND) {
      return;
    }
    if (qtColour(value) !== undefined) {
      note(where, field, QT_COLOUR_FAULT, value);
    }
  }

  function checkSheets(model) {
    if (sheetApi() === undefined) {
      note(null, STYLE_SHEET, NO_SHEET_SOURCE_FAULT, null);
      return;
    }
    var pane = objectField(model, PANE);
    checkSheet(PANE, SCROLL_STYLE, pane[SCROLL_STYLE]);
    checkSheet(PANE, EMPTY_STYLE, pane[EMPTY_STYLE]);
    checkSheet(PANE, LABEL_STYLE, pane[LABEL_STYLE]);
    checkSheet(CHART, STYLE_SHEET, objectField(model, CHART)[STYLE_SHEET]);
    checkSheet(VOTES, STYLE_SHEET, objectField(model, VOTES)[STYLE_SHEET]);
    checkSheet(EXPAND, STYLE_SHEET, objectField(model, EXPAND)[STYLE_SHEET]);
  }

  function checkColours(model) {
    var chrome = objectField(model, ROW);
    checkColour(ROW, LABEL_COLOUR, chrome[LABEL_COLOUR]);
    checkColour(ROW, MARKER_COLOUR, chrome[MARKER_COLOUR]);
    var byState = objectField(chrome, LIGHT_COLOURS);
    Object.keys(byState).forEach(function (name) {
      checkColour(ROW, LIGHT_COLOURS, byState[name]);
    });
    var votes = objectField(model, VOTES);
    checkColour(VOTES, ALTERNATE_ROW_COLOUR, votes[ALTERNATE_ROW_COLOUR]);
    listField(votes, ROWS).forEach(function (row, at) {
      if (isPlainObject(row)) {
        checkColour(VOTES + PATH_SPLIT + String(at), DIRECTION_COLOUR, row[DIRECTION_COLOUR]);
      }
    });
    Object.keys(objectField(chrome, ROWS)).forEach(function (name) {
      listField(objectField(chrome, ROWS)[name], PROGRAM).forEach(function (op) {
        if (isPlainObject(op)) {
          checkColour(ROW + PATH_SPLIT + name, PEN, op[PEN]);
          checkColour(ROW + PATH_SPLIT + name, BRUSH, op[BRUSH]);
        }
      });
    });
  }


  function heldFieldCount(model) {
    return DECLARED_FIELDS.filter(function (name) {
      return owns(model, name);
    }).length;
  }

  function drawnLamps(model) {
    var count = ZERO;
    var rows = objectField(objectField(model, ROW), ROWS);
    Object.keys(rows).forEach(function (name) {
      count += listField(rows[name], LIGHTS).length;
    });
    return count;
  }

  function declaredLampCount(model) {
    var wanted = declaredLamps(objectField(model, ROW)).length;
    return wanted * Object.keys(objectField(objectField(model, ROW), ROWS)).length;
  }

  function paneRowItems(model) {
    return listField(objectField(model, PANE), ITEMS).filter(function (item) {
      return isPlainObject(item) && item[KIND] === KIND_ROW;
    });
  }

  function report() {
    var model = held.model;
    return {
      declared: {
        fields: DECLARED_FIELDS.length,
        rows: listField(objectField(model, PANE), SYMBOLS).length,
        lamps: declaredLampCount(model),
        columns: listField(objectField(model, VOTES), COLUMNS).length,
        votes: listField(objectField(model, VOTES), ROWS).length,
        ops: listField(objectField(model, CHART), PROGRAM).length
      },
      held: {
        fields: heldFieldCount(model),
        rows: paneRowItems(model).length,
        lamps: drawnLamps(model),
        columns: listField(objectField(model, VOTES), COLUMNS).length,
        votes: listField(objectField(model, VOTES), ROWS).length,
        ops: listField(objectField(model, CHART), PROGRAM).length
      },
      faults: visualFaults.slice()
    };
  }

  function setVisuals(model) {
    if (!isPlainObject(model)) {
      held = null;
      visualFaults = [fault(null, null, NOT_AN_OBJECT_FAULT, kindOf(model))];
      return { declared: null, held: null, faults: visualFaults.slice() };
    }
    held = { model: model };
    visualFaults = [];
    checkTopFields(model);
    checkShapes(model);
    checkPane(model);
    checkRows(model);
    checkChart(model);
    checkVotes(model);
    checkExpand(model);
    checkSheets(model);
    checkColours(model);
    return report();
  }

  // loadVisuals asks once and forgets a refused ask.
  function loadVisuals(params) {
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
        setVisuals(model);
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

  function pane() {
    return bag(PANE);
  }

  function chrome() {
    return bag(ROW);
  }

  function chart() {
    return bag(CHART);
  }

  function votes() {
    return bag(VOTES);
  }

  function expand() {
    return bag(EXPAND);
  }

  function items() {
    return held === null ? [] : listField(objectField(held.model, PANE), ITEMS).slice();
  }

  // rowOrder takes its order from the pane's list, never from the row bag.
  function rowOrder() {
    return paneRowItems(held === null ? {} : held.model).map(function (item) {
      return item[SYMBOL];
    });
  }

  function lampsFor(name) {
    if (held === null) {
      return [];
    }
    var rows = objectField(objectField(held.model, ROW), ROWS);
    return owns(rows, name) ? listField(rows[name], LIGHTS).slice() : [];
  }

  function programFor(name) {
    if (held === null) {
      return [];
    }
    var rows = objectField(objectField(held.model, ROW), ROWS);
    return owns(rows, name) ? listField(rows[name], PROGRAM).slice() : [];
  }

  function chartProgram() {
    return held === null ? [] : listField(objectField(held.model, CHART), PROGRAM).slice();
  }

  function voteRows() {
    return held === null ? [] : listField(objectField(held.model, VOTES), ROWS).slice();
  }

  function columnNames() {
    return held === null ? [] : listField(objectField(held.model, VOTES), COLUMNS).slice();
  }

  function actions() {
    return bag(ACTIONS);
  }

  function timers() {
    return bag(TIMERS);
  }

  function timerDelays() {
    return list(TIMER_DELAYS_MS);
  }

  function busTopics() {
    return list(BUS_TOPICS);
  }

  function busEmits() {
    return list(BUS_EMITS);
  }

  function signals() {
    return list(SIGNALS);
  }

  function callNames() {
    return list(CALL_NAMES);
  }

  function method() {
    return field(METHOD_FIELD);
  }

  function declaredFields() {
    return DECLARED_FIELDS.slice();
  }

  function declaredNames() {
    return DECLARED_FIELDS.concat(
      PANE_FIELDS,
      ROW_FIELDS,
      CHART_FIELDS,
      VOTE_FIELDS,
      EXPAND_FIELDS,
      LIGHT_FIELDS,
      [KIND, VISIBLE, SYMBOL, LIGHTS, PROGRAM, CELLS, DIRECTION_COLOUR],
      [OP, PEN, BRUSH, RECT, ALIGN, TEXT_FIELD],
      [LINE_FIELD, WIDTH_FIELD, STYLE_FIELD, AT_FIELD]
    );
  }

  function slots() {
    return [PANE_SLOT, CHART_SLOT, VOTES_SLOT];
  }

  // kinds reports the JavaScript type of every payload value by dotted path.
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
    return visualFaults.slice();
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

  // draw runs flushSync so the document is current when it answers.
  function draw(target, node) {
    var root = rootFor(target);
    global.ReactDOM.flushSync(function () {
      root.render(node);
    });
    return target;
  }

  function payloadOr(model) {
    if (isPlainObject(model)) {
      return model;
    }
    return held === null ? null : held.model;
  }

  function renderVisuals(target, model) {
    return draw(target, element(Visuals, { model: payloadOr(model) }));
  }

  function renderPane(target, model) {
    return draw(target, element(Pane, { model: payloadOr(model) }));
  }

  function renderChartMount(target, model) {
    return draw(target, element(ChartMount, { model: payloadOr(model) }));
  }

  function renderVoteTable(target, model) {
    return draw(target, element(VoteTable, { model: payloadOr(model) }));
  }

  function forget() {
    held = null;
    visualFaults = [];
    loadFault = null;
    asked = null;
  }

  global.acervatorSetSimVisuals = setVisuals;
  global.acervatorLoadSimVisuals = loadVisuals;
  global.acervatorSimVisuals = {
    method: METHOD,
    Visuals: Visuals,
    Pane: Pane,
    PaneRow: PaneRow,
    LampRow: LampRow,
    Lamp: Lamp,
    Caption: Caption,
    ChartMount: ChartMount,
    VoteTable: VoteTable,
    ExpandFrame: ExpandFrame,
    field: field,
    pane: pane,
    chrome: chrome,
    chart: chart,
    votes: votes,
    expand: expand,
    items: items,
    rowOrder: rowOrder,
    lampsFor: lampsFor,
    programFor: programFor,
    chartProgram: chartProgram,
    voteRows: voteRows,
    columnNames: columnNames,
    actions: actions,
    timers: timers,
    timerDelays: timerDelays,
    busTopics: busTopics,
    busEmits: busEmits,
    signals: signals,
    callNames: callNames,
    methodName: method,
    declaredFields: declaredFields,
    declaredNames: declaredNames,
    declaredLamps: declaredLamps,
    slots: slots,
    declarations: declarations,
    stateRules: stateRules,
    styleOf: styleOf,
    stateStyle: stateStyle,
    keptSheet: keptSheet,
    qtColour: qtColour,
    variableFor: variableFor,
    colour: colour,
    pixels: pixels,
    points: points,
    kinds: kinds,
    faults: faults,
    loadError: loadError,
    isLoaded: isLoaded,
    renderVisuals: renderVisuals,
    renderPane: renderPane,
    renderChartMount: renderChartMount,
    renderVoteTable: renderVoteTable,
    forget: forget
  };
})(window);
