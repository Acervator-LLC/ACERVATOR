// The Positions Held tab, drawn into one global function.
(function (global) {
  "use strict";

  var METHOD = "positions_held_tab.state";

  var ACCESSIBLE_NAME = "accessible_name";
  var ACTIONS = "actions";
  var ATTRIBUTES = "attributes";
  var BOXES = "boxes";
  var BUS_TOPICS = "bus_topics";
  var BUTTON_VALUES = "button_values";
  var CALLS = "calls";
  var CALL_NAMES = "call_names";
  var COLORS = "colors";
  var CONTAINER = "container";
  var DEFAULTS = "defaults";
  var EMPTY_LABEL = "empty_label";
  var FIRE_BUTTON = "fire_button";
  var FIRE_OUTCOME = "fire_outcome";
  var FOOTER_LABEL = "footer_label";
  var FORMATS = "formats";
  var ICONS = "icons";
  var KEYS = "keys";
  var LABELS = "labels";
  var NO_CELL_COLOR = "no_cell_color";
  var NO_OUTCOME = "no_outcome";
  var OUTCOMES = "outcomes";
  var POOL_COLOR = "pool_color";
  var POOL_COLOR_HEX = "pool_color_hex";
  var POOL_COLOR_MAP = "pool_color_map";
  var POOL_FALLBACK = "pool_fallback";
  var POOL_LABEL = "pool_label";
  var POOL_NAMES = "pool_names";
  var POOL_UNKNOWN_HEX = "pool_unknown_hex";
  var POSITIONS_TABLE = "positions_table";
  var STATE_NAMES = "state_names";
  var SUMMARY_FORM = "summary_form";
  var SUMMARY_GROUP = "summary_group";
  var SUMMARY_ROWS = "summary_rows";
  var TEXTS = "texts";
  var TIMERS = "timers";
  var TIMER_DELAYS_MS = "timer_delays_ms";
  var TITLES = "titles";

  // Every top-level name the positions_held_tab.state payload carries.
  var DECLARED_FIELDS = [
    ACCESSIBLE_NAME,
    ACTIONS,
    ATTRIBUTES,
    BOXES,
    BUS_TOPICS,
    BUTTON_VALUES,
    CALLS,
    CALL_NAMES,
    COLORS,
    CONTAINER,
    DEFAULTS,
    EMPTY_LABEL,
    FIRE_BUTTON,
    FIRE_OUTCOME,
    FOOTER_LABEL,
    FORMATS,
    ICONS,
    KEYS,
    LABELS,
    NO_CELL_COLOR,
    NO_OUTCOME,
    OUTCOMES,
    POOL_COLOR,
    POOL_COLOR_HEX,
    POOL_COLOR_MAP,
    POOL_FALLBACK,
    POOL_LABEL,
    POOL_NAMES,
    POOL_UNKNOWN_HEX,
    POSITIONS_TABLE,
    STATE_NAMES,
    SUMMARY_FORM,
    SUMMARY_GROUP,
    SUMMARY_ROWS,
    TEXTS,
    TIMERS,
    TIMER_DELAYS_MS,
    TITLES
  ];

  var DECLARED_BAGS = [
    ACTIONS,
    ATTRIBUTES,
    BUTTON_VALUES,
    COLORS,
    CONTAINER,
    DEFAULTS,
    EMPTY_LABEL,
    FIRE_BUTTON,
    FOOTER_LABEL,
    FORMATS,
    ICONS,
    KEYS,
    LABELS,
    POOL_COLOR_MAP,
    POOL_LABEL,
    POSITIONS_TABLE,
    SUMMARY_FORM,
    SUMMARY_GROUP,
    TEXTS,
    TIMERS,
    TITLES
  ];

  var DECLARED_LISTS = [
    BOXES,
    BUS_TOPICS,
    CALLS,
    CALL_NAMES,
    OUTCOMES,
    POOL_NAMES,
    STATE_NAMES,
    SUMMARY_ROWS,
    TIMER_DELAYS_MS
  ];

  // Three fields the surface leaves empty until a position is closed.
  var NULLABLE_FIELDS = [FIRE_OUTCOME, NO_CELL_COLOR, NO_OUTCOME];

  var TEXT_FIELD = "text";
  var STYLE_SHEET = "style_sheet";
  var WORD_WRAP = "word_wrap";
  var SHOWN = "shown";
  var TITLE_FIELD = "title";
  var SPACING_PX = "spacing_px";
  var MARGINS_SET = "margins_set";
  var CONFIGURED_BY_HOST = "configured_by_host";
  var CONFIGURED = "configured";

  var COLUMNS = "columns";
  var COLUMN_COUNT = "column_count";
  var CELL_COLUMN_COUNT = "cell_column_count";
  var ROWS = "rows";
  var ROW_COLORS = "row_colors";
  var ROW_COUNT = "row_count";
  var STATE_COLUMN = "state_column";
  var DELTA_COLUMN = "delta_column";
  var FIRE_COLUMN = "fire_column";
  var CELL_ALIGNMENT = "cell_alignment";
  var ALTERNATING_ROW_COLORS = "alternating_row_colors";
  var HEADER_RESIZE_MODE = "header_resize_mode";
  var VERTICAL_HEADER_VISIBLE = "vertical_header_visible";
  var EDIT_TRIGGERS = "edit_triggers";
  var SELECTION_BEHAVIOR = "selection_behavior";

  var FIXED_HEIGHT_PX = "fixed_height_px";
  var PAIRS = "pairs";

  var BOX_ICON = "icon";
  var BOX_TITLE = "title";
  var BOX_TEXT = "text";
  var BUTTONS_VALUE = "buttons_value";
  var DEFAULT_BUTTON_VALUE = "default_button_value";
  var BOX_FIELDS = [BOX_ICON, BOX_TITLE, BOX_TEXT, BUTTONS_VALUE, DEFAULT_BUTTON_VALUE];

  // The three answers a box offers, as a list, so a bag key order is never asked.
  var YES_NAME = "yes";
  var NO_NAME = "no";
  var OK_NAME = "ok";
  var ANSWER_NAMES = [YES_NAME, NO_NAME, OK_NAME];
  var CONFIRM_BUTTONS = "confirm_buttons";
  var CONFIRM_DEFAULT = "confirm_default";
  var CONFIRM_OFFERS = [YES_NAME, NO_NAME];

  // The wired action names, as a list, because a bag key order is the only other.
  var FIRE_CLICKED = "fire_button.clicked";
  var ACTION_NAMES = [FIRE_CLICKED];

  var POOL_ROW_LABEL = "pool_row";
  // The three money row labels, as a list, so the written order is the drawn order.
  var ROW_FORMAT_NAMES = ["chunk_size_row", "chunk_free_row", "extracted_row"];

  var MISSING_FAULT = "missing";
  var NULL_FAULT = "null";
  var NOT_AN_OBJECT_FAULT = "not-an-object";
  var NOT_A_BAG_FAULT = "not-a-bag";
  var NOT_A_LIST_FAULT = "not-a-list";
  var SHORT_LIST_FAULT = "short-list";
  var SWAPPED_ALPHA_FAULT = "swapped-alpha";
  var BYTE_ALPHA_FAULT = "byte-alpha";
  var REORDERED_KEY_FAULT = "reordered-key";
  var DISAGREES_FAULT = "disagrees";
  var UNKNOWN_ACTION_FAULT = "unknown-action";
  var UNNAMED_ROW_FAULT = "unnamed-row";
  var DUPLICATE_NAME_FAULT = "duplicate-name";
  var NOT_CSS_FAULT = "not-css";

  var ROW_AT = "row:";
  var BOX_AT = "box:";
  var SUMMARY_AT = "summary:";
  var PATH_SPLIT = ".";
  var EMPTY = "";
  var BRACE_OPEN = "{";
  var COMMA = ",";
  var CLOSE = ")";
  var DOT = ".";
  var PERCENT = "%";

  var NO_BRIDGE = "the preload bridge is not present";

  // Qt paints qlineargradient by name and no browser stylesheet runs it.
  var QT_ONLY = "qlineargradient";

  // HASH_ESCAPE decodes to the mark every colour opens with.
  var HASH_ESCAPE = "%23";
  var HEX_MARK = decodeURIComponent(HASH_ESCAPE);
  // Qt reads an eight-digit hex colour alpha first, and CSS reads it last.
  var HEX_ARGB = "AARRGGBB";
  var SWAPPED_LENGTH = HEX_MARK.length + HEX_ARGB.length;
  // Qt counts an rgba alpha in whole bytes, and CSS counts it as a fraction.
  var RGBA_OPEN = "rgba(";
  var HEX_PREFIX = "0x";
  var HEX_BYTE_MAX = "ff";
  var ALPHA_SCALE = Number(HEX_PREFIX + HEX_BYTE_MAX);

  var DIGITS = "0123456789";
  var HEX_LETTERS = "abcdefABCDEF";

  var PX = "px";
  var FLEX = "flex";
  var COLUMN_DIRECTION = "column";
  var AUTO = "auto";
  var PRE = "pre";
  var PRE_WRAP = "pre-wrap";
  var NOWRAP = "nowrap";
  var COLLAPSE = "collapse";
  var CENTER = "center";

  var TAB_CLASS = "acervator-positions-held";

  var DIV_TAG = "div";
  var SPAN_TAG = "span";
  var BUTTON_TAG = "button";
  var BUTTON_TYPE = "button";
  var TABLE_TAG = "table";
  var HEAD_TAG = "thead";
  var BODY_TAG = "tbody";
  var ROW_TAG = "tr";
  var HEAD_CELL_TAG = "th";
  var CELL_TAG = "td";

  var TAB_PART = "positions-held-tab";
  var SUMMARY_GROUP_PART = "summary-group";
  var SUMMARY_TITLE_PART = "summary-group-title";
  var SUMMARY_ROW_PART = "summary-row";
  var SUMMARY_LABEL_PART = "summary-label";
  var SUMMARY_VALUE_PART = "summary-value";
  var EMPTY_NOTE_PART = "empty-note";
  var TABLE_PART = "positions-table";
  var HEAD_PART = "table-head";
  var HEAD_ROW_PART = "head-row";
  var HEAD_CELL_PART = "head-cell";
  var BODY_PART = "table-body";
  var POSITION_ROW_PART = "position-row";
  var POSITION_CELL_PART = "position-cell";
  var FIRE_BUTTON_PART = "fire-button";
  var FOOTER_NOTE_PART = "footer-note";
  var MESSAGE_BOX_PART = "message-box";
  var BOX_TITLE_PART = "box-title";
  var BOX_TEXT_PART = "box-text";
  var BOX_BUTTON_PART = "box-button";
  var OUTCOME_PART = "outcome";

  // PAGE_PART is the space the Live Bot Settings window leaves for this tab.
  var PAGE_PART = "positions-held-page";

  var PART_ATTR = "data-part";
  var KEY_ATTR = "data-key";
  var NAME_ATTR = "data-name";
  var INDEX_ATTR = "data-index";
  var COLUMN_ATTR = "data-column";
  var COUNT_ATTR = "data-count";
  var VALUE_ATTR = "data-value";
  var ICON_ATTR = "data-icon";
  var ACTION_ATTR = "data-action";
  var DEFAULT_ATTR = "data-default";
  var SHOWN_ATTR = "data-shown";
  var WRAP_ATTR = "data-word-wrap";
  var STYLED_ATTR = "data-styled";
  var PAINTED_ATTR = "data-painted";
  var HOST_ATTR = "data-configured-by-host";
  var MATCHED_ATTR = "data-matched";
  var MARGINS_ATTR = "data-margins-set";
  var ALIGNMENT_ATTR = "data-alignment";
  var ALTERNATING_ATTR = "data-alternating";
  var RESIZE_ATTR = "data-resize-mode";
  var SIDE_HEAD_ATTR = "data-side-head";
  var EDIT_ATTR = "data-edit-triggers";
  var SELECT_ATTR = "data-selection";
  var ARIA_LABEL = "aria-label";

  var SELECT_OPEN = "[";
  var SELECT_IS = "=\"";
  var SELECT_CLOSE = "\"]";

  var ZERO = Number(EMPTY);
  var STEP = Number(true);

  var held = null;
  var tabFaults = [];
  var loadFault = null;
  var asked = null;
  var roots = [];
  var lastPress = null;

  function isPlainObject(value) {
    return value !== null && typeof value === "object" && !Array.isArray(value);
  }

  function owns(bag, name) {
    return Object.prototype.hasOwnProperty.call(bag, name);
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

  function objectField(model, field) {
    return isPlainObject(model) && isPlainObject(model[field]) ? model[field] : {};
  }

  function listField(model, field) {
    return isPlainObject(model) && Array.isArray(model[field]) ? model[field] : [];
  }

  function fault(where, field, kind, detail) {
    return { where: where, field: field, fault: kind, detail: detail };
  }

  function text(value) {
    return value === null || value === undefined ? undefined : String(value);
  }

  function label(value) {
    return typeof value === "string" && value.length ? value : undefined;
  }

  function length(value) {
    return value === null || value === undefined ? undefined : String(value) + PX;
  }

  function afterFirst(value, splitter) {
    var parts = String(value).split(splitter);
    parts.shift();
    return parts;
  }

  function carries(value, splitter) {
    return Boolean(afterFirst(value, splitter).length);
  }

  // The reciprocal of the alpha scale, so a fraction needs no division.
  var ALPHA_RECIPROCAL = Math.pow(ALPHA_SCALE, ZERO - STEP);

  // The fraction CSS wants from an alpha Qt counted in whole bytes.
  function alphaFraction(bytes) {
    var found = Number(bytes);
    return (found === found ? found : ZERO) * ALPHA_RECIPROCAL;
  }

  // True for a colour written with eight hex digits, which Qt reads alpha first.
  function isSwappedAlpha(value) {
    return (
      typeof value === "string" &&
      value.length === SWAPPED_LENGTH &&
      value.charAt(ZERO) === HEX_MARK
    );
  }

  // The alpha byte an rgba value carries when it counts in bytes, not fractions.
  function byteAlpha(value) {
    var parts = afterFirst(value, RGBA_OPEN);
    if (!parts.length) {
      return undefined;
    }
    var fields = String(parts.shift()).split(CLOSE).shift().split(COMMA);
    fields.shift();
    fields.shift();
    fields.shift();
    var alpha = fields.shift();
    if (alpha === undefined) {
      return undefined;
    }
    if (carries(alpha, DOT) || carries(alpha, PERCENT)) {
      return undefined;
    }
    return alphaFraction(alpha);
  }

  function isHexLetter(letter) {
    return DIGITS.indexOf(letter) >= ZERO || HEX_LETTERS.indexOf(letter) >= ZERO;
  }

  // Every colour written anywhere in one raw sheet, a hover sub-block included.
  function hexRuns(sheet) {
    var found = [];
    if (sheet === null || sheet === undefined) {
      return found;
    }
    String(sheet)
      .split(HEX_MARK)
      .slice(STEP)
      .forEach(function (piece) {
        var run = EMPTY;
        var at = ZERO;
        while (at < piece.length && isHexLetter(piece.charAt(at))) {
          run += piece.charAt(at);
          at += STEP;
        }
        found.push(HEX_MARK + run);
      });
    return found;
  }

  // Every rgba value written anywhere in one raw sheet, a sub-block included.
  function rgbaRuns(sheet) {
    if (sheet === null || sheet === undefined) {
      return [];
    }
    return afterFirst(sheet, RGBA_OPEN).map(function (piece) {
      return RGBA_OPEN + String(piece).split(CLOSE).shift() + CLOSE;
    });
  }

  // True for a key a browser lists before every worded key of the same bag.
  function isReorderedKey(key) {
    var printed = String(key);
    if (!printed.length) {
      return false;
    }
    var digitsOnly = true;
    printed.split(EMPTY).forEach(function (letter) {
      if (DIGITS.indexOf(letter) < ZERO) {
        digitsOnly = false;
      }
    });
    return digitsOnly;
  }

  // header_strip.js owns the rule that turns a Qt style sheet into CSS.
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

  // table_cells.js owns the rule that paints a colour through its own token.
  function colour(value) {
    var api = global.acervatorCells;
    if (!api || typeof api.colour !== "function") {
      return text(value);
    }
    return api.colour(value);
  }

  function model() {
    return held === null ? null : held.model;
  }

  function tableBag() {
    return objectField(model(), POSITIONS_TABLE);
  }

  function fireBag() {
    return objectField(model(), FIRE_BUTTON);
  }

  function summaryRows() {
    return listField(model(), SUMMARY_ROWS);
  }

  // Every drawn summary row named by its own label, in the order the rows arrived.
  function drawnLabels() {
    return summaryRows().map(function (row) {
      return Array.isArray(row) && row.length ? row[ZERO] : undefined;
    });
  }

  // The fixed head of one row format, which is the text before its placeholder.
  function formatHead(written) {
    return String(written).split(BRACE_OPEN).shift();
  }

  // The pool label and the three money row heads, in the order they are drawn.
  function publishedLabels() {
    var labels = objectField(model(), LABELS);
    var formats = objectField(model(), FORMATS);
    var found = [];
    if (owns(labels, POOL_ROW_LABEL)) {
      found.push(labels[POOL_ROW_LABEL]);
    }
    ROW_FORMAT_NAMES.forEach(function (name) {
      if (owns(formats, name)) {
        found.push(formatHead(formats[name]));
      }
    });
    return found;
  }

  // The published label one drawn label answers to, by name and never by place.
  function labelNamed(drawn) {
    var found;
    publishedLabels().forEach(function (name) {
      if (!String(name).length) {
        return;
      }
      if (drawn === name || String(drawn).indexOf(String(name)) === ZERO) {
        if (found === undefined || String(name).length > String(found).length) {
          found = name;
        }
      }
    });
    return found;
  }

  // One summary row found by its own label, never by where it sits.
  function summaryRowNamed(name) {
    var found;
    summaryRows().forEach(function (row) {
      if (Array.isArray(row) && row.length && row[ZERO] === name) {
        found = row;
      }
    });
    return found;
  }

  function summaryValue(name) {
    var row = summaryRowNamed(name);
    return Array.isArray(row) && row.length > STEP ? row[STEP] : undefined;
  }

  // The pool row alone publishes a whole sheet, and the money rows publish none.
  function summaryStyleNamed(name) {
    var labels = objectField(model(), LABELS);
    if (owns(labels, POOL_ROW_LABEL) && labels[POOL_ROW_LABEL] === name) {
      return objectField(model(), POOL_LABEL)[STYLE_SHEET];
    }
    return undefined;
  }

  function columnNames() {
    return listField(tableBag(), COLUMNS);
  }

  function columnNamed(at) {
    return columnNames()[at];
  }

  // The two columns Qt paints, named by their own headings and not their places.
  function stateColumnName() {
    return columnNamed(tableBag()[STATE_COLUMN]);
  }

  function deltaColumnName() {
    return columnNamed(tableBag()[DELTA_COLUMN]);
  }

  function tableRows() {
    return listField(tableBag(), ROWS);
  }

  function rowCells(at) {
    var row = tableRows()[at];
    return Array.isArray(row) ? row : [];
  }

  function rowColors(at) {
    var painted = listField(tableBag(), ROW_COLORS)[at];
    return Array.isArray(painted) ? painted : [];
  }

  function noCellColour() {
    var found = model();
    return isPlainObject(found) ? found[NO_CELL_COLOR] : null;
  }

  function cellColour(at, column) {
    var value = rowColors(at)[column];
    return value === noCellColour() ? undefined : value;
  }

  function firePairs() {
    return listField(fireBag(), PAIRS);
  }

  // Every drawn table row named by the pair it closes, never by its own place.
  function rowIdentities() {
    return tableRows().map(function (cells, at) {
      return { at: at, name: firePairs()[at] };
    });
  }

  function rowNamed(name) {
    var found;
    rowIdentities().forEach(function (one) {
      if (one.name === name) {
        found = rowCells(one.at);
      }
    });
    return found;
  }

  // One cell of one row read by its own column name, never by its place.
  function cellNamed(at, name) {
    var column = columnNames().indexOf(name);
    return column < ZERO ? undefined : rowCells(at)[column];
  }

  function action(name) {
    var found = objectField(model(), ACTIONS);
    return owns(found, name) ? found[name] : undefined;
  }

  function buttonValue(name) {
    var found = objectField(model(), BUTTON_VALUES);
    return owns(found, name) ? found[name] : undefined;
  }

  function boxes() {
    return listField(model(), BOXES);
  }

  // A mask offers one answer when it carries the whole value of that answer.
  function offers(mask, value) {
    if (typeof mask !== "number" || typeof value !== "number") {
      return false;
    }
    return value !== ZERO && (mask & value) === value;
  }

  // The answers one box offers, read from the mask Qt built them with.
  function boxAnswers(box) {
    var mask = isPlainObject(box) ? box[BUTTONS_VALUE] : undefined;
    return ANSWER_NAMES.filter(function (name) {
      return offers(mask, buttonValue(name));
    });
  }

  function boxDefault(box) {
    return isPlainObject(box) ? box[DEFAULT_BUTTON_VALUE] : undefined;
  }

  function colourNamed(name) {
    var found = objectField(model(), COLORS);
    return owns(found, name) ? found[name] : undefined;
  }

  function poolNames() {
    return listField(model(), POOL_NAMES);
  }

  function outcomes() {
    return listField(model(), OUTCOMES);
  }

  function calls() {
    return listField(model(), CALLS).slice();
  }

  // Every style sheet the tab applies, each beside the field carrying it.
  function sheets() {
    var found = model();
    return [
      { field: POOL_LABEL, sheet: objectField(found, POOL_LABEL)[STYLE_SHEET] },
      { field: EMPTY_LABEL, sheet: objectField(found, EMPTY_LABEL)[STYLE_SHEET] },
      { field: FOOTER_LABEL, sheet: objectField(found, FOOTER_LABEL)[STYLE_SHEET] },
      { field: FIRE_BUTTON, sheet: objectField(found, FIRE_BUTTON)[STYLE_SHEET] }
    ];
  }

  // Every bare colour the table paints one cell with, beside the row holding it.
  function cellColours() {
    var found = [];
    listField(tableBag(), ROW_COLORS).forEach(function (painted, at) {
      if (!Array.isArray(painted)) {
        return;
      }
      painted.forEach(function (value) {
        if (value !== noCellColour()) {
          found.push({ field: ROW_COLORS, where: ROW_AT + String(at), value: value });
        }
      });
    });
    return found;
  }

  function checkFields(found) {
    DECLARED_FIELDS.forEach(function (name) {
      if (!owns(found, name)) {
        tabFaults.push(fault(null, name, MISSING_FAULT, null));
        return;
      }
      if (found[name] === null && NULLABLE_FIELDS.indexOf(name) < ZERO) {
        tabFaults.push(fault(null, name, NULL_FAULT, null));
      }
    });
    DECLARED_BAGS.forEach(function (name) {
      if (owns(found, name) && !isPlainObject(found[name])) {
        tabFaults.push(fault(null, name, NOT_A_BAG_FAULT, kindOf(found[name])));
      }
    });
    DECLARED_LISTS.forEach(function (name) {
      if (owns(found, name) && !Array.isArray(found[name])) {
        tabFaults.push(fault(null, name, NOT_A_LIST_FAULT, kindOf(found[name])));
      }
    });
  }

  function checkActions(found) {
    var bag = objectField(found, ACTIONS);
    ACTION_NAMES.forEach(function (name) {
      if (!owns(bag, name)) {
        tabFaults.push(fault(null, ACTIONS, MISSING_FAULT, name));
      }
    });
    Object.keys(bag).forEach(function (name) {
      if (ACTION_NAMES.indexOf(name) < ZERO) {
        tabFaults.push(fault(null, ACTIONS, UNKNOWN_ACTION_FAULT, name));
      }
    });
  }

  function checkAnswers(found) {
    var bag = objectField(found, BUTTON_VALUES);
    ANSWER_NAMES.concat([CONFIRM_BUTTONS, CONFIRM_DEFAULT]).forEach(function (name) {
      if (!owns(bag, name)) {
        tabFaults.push(fault(null, BUTTON_VALUES, MISSING_FAULT, name));
      }
    });
    CONFIRM_OFFERS.forEach(function (name) {
      if (!offers(bag[CONFIRM_BUTTONS], bag[name])) {
        tabFaults.push(fault(null, CONFIRM_BUTTONS, DISAGREES_FAULT, name));
      }
    });
    if (!offers(bag[CONFIRM_BUTTONS], bag[CONFIRM_DEFAULT])) {
      tabFaults.push(fault(null, CONFIRM_DEFAULT, DISAGREES_FAULT, bag[CONFIRM_DEFAULT]));
    }
  }

  // The nine column names are counted against the eight cells one row carries.
  function checkCounts(found) {
    var table = objectField(found, POSITIONS_TABLE);
    var names = listField(table, COLUMNS);
    var cells = table[CELL_COLUMN_COUNT];
    var drawn = listField(table, ROWS);
    if (names.length !== table[COLUMN_COUNT]) {
      tabFaults.push(fault(null, COLUMN_COUNT, DISAGREES_FAULT, table[COLUMN_COUNT]));
    }
    if (table[FIRE_COLUMN] !== cells) {
      tabFaults.push(fault(null, FIRE_COLUMN, DISAGREES_FAULT, table[FIRE_COLUMN]));
    }
    if (drawn.length !== table[ROW_COUNT]) {
      tabFaults.push(fault(null, ROW_COUNT, DISAGREES_FAULT, table[ROW_COUNT]));
    }
    if (listField(objectField(found, FIRE_BUTTON), PAIRS).length !== drawn.length) {
      tabFaults.push(fault(null, PAIRS, SHORT_LIST_FAULT, drawn.length));
    }
    if (listField(table, ROW_COLORS).length !== drawn.length) {
      tabFaults.push(fault(null, ROW_COLORS, SHORT_LIST_FAULT, drawn.length));
    }
    drawn.forEach(function (row, at) {
      var where = ROW_AT + String(at);
      if (!Array.isArray(row)) {
        tabFaults.push(fault(where, ROWS, NOT_A_LIST_FAULT, kindOf(row)));
      } else if (row.length !== cells) {
        tabFaults.push(fault(where, ROWS, SHORT_LIST_FAULT, row.length));
      }
      var painted = listField(table, ROW_COLORS)[at];
      if (!Array.isArray(painted)) {
        tabFaults.push(fault(where, ROW_COLORS, NOT_A_LIST_FAULT, kindOf(painted)));
      } else if (painted.length !== cells) {
        tabFaults.push(fault(where, ROW_COLORS, SHORT_LIST_FAULT, painted.length));
      }
    });
  }

  // Each drawn summary row must answer to a label the payload publishes.
  function checkLabels(found) {
    listField(found, SUMMARY_ROWS).forEach(function (row, at) {
      var where = SUMMARY_AT + String(at);
      if (!Array.isArray(row)) {
        tabFaults.push(fault(where, SUMMARY_ROWS, NOT_A_LIST_FAULT, kindOf(row)));
        return;
      }
      if (row.length <= STEP) {
        tabFaults.push(fault(where, SUMMARY_ROWS, SHORT_LIST_FAULT, row.length));
      }
      if (labelNamed(row[ZERO]) === undefined) {
        tabFaults.push(fault(where, LABELS, UNNAMED_ROW_FAULT, row[ZERO]));
      }
    });
  }

  // Two positions on one pair cannot be told apart by the pair a button closes.
  function checkRowNames() {
    var seen = [];
    rowIdentities().forEach(function (one) {
      if (one.name === undefined) {
        tabFaults.push(fault(ROW_AT + String(one.at), PAIRS, MISSING_FAULT, null));
        return;
      }
      if (seen.indexOf(one.name) >= ZERO) {
        tabFaults.push(
          fault(ROW_AT + String(one.at), PAIRS, DUPLICATE_NAME_FAULT, one.name)
        );
      }
      seen.push(one.name);
    });
  }

  function checkColour(where, field, value) {
    if (isSwappedAlpha(value)) {
      tabFaults.push(fault(where, field, SWAPPED_ALPHA_FAULT, value));
    }
    if (byteAlpha(value) !== undefined) {
      tabFaults.push(fault(where, field, BYTE_ALPHA_FAULT, value));
    }
  }

  function checkColours(found) {
    [COLORS, POOL_COLOR_MAP].forEach(function (name) {
      var bag = objectField(found, name);
      Object.keys(bag).forEach(function (key) {
        checkColour(null, name, bag[key]);
      });
    });
    [POOL_COLOR_HEX, POOL_UNKNOWN_HEX].forEach(function (name) {
      checkColour(null, name, found[name]);
    });
    cellColours().forEach(function (one) {
      checkColour(one.where, one.field, one.value);
    });
    sheets().forEach(function (one) {
      hexRuns(one.sheet).forEach(function (value) {
        checkColour(null, one.field, value);
      });
      rgbaRuns(one.sheet).forEach(function (value) {
        checkColour(null, one.field, value);
      });
      declarations(one.sheet).forEach(function (written) {
        if (carries(written.value, QT_ONLY)) {
          tabFaults.push(fault(null, one.field, NOT_CSS_FAULT, written.property));
        }
      });
    });
  }

  function checkBagOrder(found) {
    DECLARED_BAGS.forEach(function (name) {
      Object.keys(objectField(found, name)).forEach(function (key) {
        if (isReorderedKey(key)) {
          tabFaults.push(fault(null, name, REORDERED_KEY_FAULT, key));
        }
      });
    });
  }

  function checkBoxes(found) {
    var titles = objectField(found, TITLES);
    var named = Object.keys(titles).map(function (name) {
      return titles[name];
    });
    listField(found, BOXES).forEach(function (box, at) {
      var where = BOX_AT + String(at);
      if (!isPlainObject(box)) {
        tabFaults.push(fault(where, BOXES, NOT_AN_OBJECT_FAULT, kindOf(box)));
        return;
      }
      BOX_FIELDS.forEach(function (name) {
        if (!owns(box, name)) {
          tabFaults.push(fault(where, BOXES, MISSING_FAULT, name));
        }
      });
      if (named.indexOf(box[BOX_TITLE]) < ZERO) {
        tabFaults.push(fault(where, TITLES, UNNAMED_ROW_FAULT, box[BOX_TITLE]));
      }
      if (!boxAnswers(box).length) {
        tabFaults.push(fault(where, BUTTONS_VALUE, SHORT_LIST_FAULT, box[BUTTONS_VALUE]));
      }
    });
  }

  // The drawn pool colour must be the one the published map gives that name.
  function checkPool(found) {
    var map = objectField(found, POOL_COLOR_MAP);
    var name = found[POOL_COLOR];
    var wanted = owns(map, name) ? map[name] : found[POOL_UNKNOWN_HEX];
    if (found[POOL_COLOR_HEX] !== wanted) {
      tabFaults.push(fault(null, POOL_COLOR_HEX, DISAGREES_FAULT, found[POOL_COLOR_HEX]));
    }
    if (listField(found, POOL_NAMES).indexOf(found[POOL_FALLBACK]) < ZERO) {
      tabFaults.push(fault(null, POOL_FALLBACK, DISAGREES_FAULT, found[POOL_FALLBACK]));
    }
  }

  function checkOutcome(found) {
    var value = found[FIRE_OUTCOME];
    if (value === found[NO_OUTCOME]) {
      return;
    }
    if (listField(found, OUTCOMES).indexOf(value) < ZERO) {
      tabFaults.push(fault(null, FIRE_OUTCOME, DISAGREES_FAULT, value));
    }
  }

  function element() {
    return global.React.createElement.apply(null, arguments);
  }

  // A summary sheet is written CSS, so an empty sheet paints nothing at all.
  function paintedStyle(sheet) {
    return declarations(sheet).length ? styleOf(sheet) : {};
  }

  function SummaryRow(props) {
    var row = Array.isArray(props.row) ? props.row : [];
    var name = row.length ? row[ZERO] : undefined;
    var sheet = summaryStyleNamed(name);
    var rowProps = { className: TAB_CLASS, style: { display: FLEX } };
    rowProps[PART_ATTR] = SUMMARY_ROW_PART;
    rowProps[KEY_ATTR] = text(name);
    rowProps[INDEX_ATTR] = text(props.at);
    rowProps[NAME_ATTR] = text(labelNamed(name));
    var labelProps = { className: TAB_CLASS };
    labelProps[PART_ATTR] = SUMMARY_LABEL_PART;
    labelProps[KEY_ATTR] = text(name);
    var style = paintedStyle(sheet);
    style.whiteSpace = PRE;
    var valueProps = { className: TAB_CLASS, style: style };
    valueProps[PART_ATTR] = SUMMARY_VALUE_PART;
    valueProps[KEY_ATTR] = text(name);
    valueProps[STYLED_ATTR] = String(Boolean(declarations(sheet).length));
    return element(
      DIV_TAG,
      rowProps,
      element(SPAN_TAG, labelProps, text(name)),
      element(SPAN_TAG, valueProps, text(row.length > STEP ? row[STEP] : undefined))
    );
  }

  function SummaryGroup(props) {
    var group = objectField(props.model, SUMMARY_GROUP);
    var form = objectField(props.model, SUMMARY_FORM);
    var groupProps = {
      className: TAB_CLASS,
      style: { display: FLEX, flexDirection: COLUMN_DIRECTION }
    };
    groupProps[PART_ATTR] = SUMMARY_GROUP_PART;
    groupProps[COUNT_ATTR] = text(summaryRows().length);
    groupProps[HOST_ATTR] = text(form[CONFIGURED_BY_HOST]);
    groupProps[MATCHED_ATTR] = text(form[CONFIGURED]);
    var titleProps = { className: TAB_CLASS };
    titleProps[PART_ATTR] = SUMMARY_TITLE_PART;
    var drawn = [element(SPAN_TAG, titleProps, text(group[TITLE_FIELD]))];
    summaryRows().forEach(function (row, at) {
      drawn.push(
        element(SummaryRow, { key: SUMMARY_ROW_PART + String(at), row: row, at: at })
      );
    });
    return element(DIV_TAG, groupProps, drawn);
  }

  function Note(props) {
    var note = objectField(props.model, props.field);
    var style = styleOf(note[STYLE_SHEET]);
    style.whiteSpace = note[WORD_WRAP] === true ? PRE_WRAP : PRE;
    var noteProps = {
      className: TAB_CLASS,
      style: style,
      hidden: note[SHOWN] !== true
    };
    noteProps[PART_ATTR] = props.part;
    noteProps[SHOWN_ATTR] = text(note[SHOWN]);
    noteProps[WRAP_ATTR] = text(note[WORD_WRAP]);
    return element(DIV_TAG, noteProps, text(note[TEXT_FIELD]));
  }

  function HeadCell(props) {
    var headProps = {
      className: TAB_CLASS,
      style: { whiteSpace: NOWRAP, textAlign: CENTER }
    };
    headProps[PART_ATTR] = HEAD_CELL_PART;
    headProps[COLUMN_ATTR] = text(props.at);
    headProps[KEY_ATTR] = text(props.name);
    headProps[ARIA_LABEL] = label(props.name);
    return element(HEAD_CELL_TAG, headProps, text(props.name));
  }

  function FireButton(props) {
    var fire = fireBag();
    var style = styleOf(fire[STYLE_SHEET]);
    style.height = length(fire[FIXED_HEIGHT_PX]);
    var buttonProps = {
      className: TAB_CLASS,
      style: style,
      type: BUTTON_TYPE,
      onClick: function () {
        press(FIRE_CLICKED, props.pair);
        if (typeof props.onFire === "function") {
          props.onFire(props.pair);
        }
      }
    };
    buttonProps[PART_ATTR] = FIRE_BUTTON_PART;
    buttonProps[NAME_ATTR] = text(props.pair);
    buttonProps[INDEX_ATTR] = text(props.at);
    buttonProps[ACTION_ATTR] = label(action(FIRE_CLICKED));
    buttonProps[ARIA_LABEL] = label(fire[TEXT_FIELD]);
    return element(BUTTON_TAG, buttonProps, text(fire[TEXT_FIELD]));
  }

  // The last column carries one button, and every column before it carries text.
  function cellChild(props) {
    if (props.column === tableBag()[FIRE_COLUMN]) {
      return element(FireButton, {
        at: props.at,
        pair: firePairs()[props.at],
        onFire: props.onFire
      });
    }
    return text(rowCells(props.at)[props.column]);
  }

  function PositionCell(props) {
    var painted = cellColour(props.at, props.column);
    var style = { whiteSpace: NOWRAP, textAlign: CENTER };
    if (painted !== undefined) {
      style.color = colour(painted);
    }
    var cellProps = { className: TAB_CLASS, style: style };
    cellProps[PART_ATTR] = POSITION_CELL_PART;
    cellProps[COLUMN_ATTR] = text(props.column);
    cellProps[KEY_ATTR] = text(columnNamed(props.column));
    cellProps[VALUE_ATTR] = text(painted);
    cellProps[PAINTED_ATTR] = String(painted !== undefined);
    return element(CELL_TAG, cellProps, cellChild(props));
  }

  function PositionRow(props) {
    var drawn = columnNames().map(function (name, column) {
      return element(PositionCell, {
        key: String(column),
        at: props.at,
        column: column,
        onFire: props.onFire
      });
    });
    var rowProps = { className: TAB_CLASS };
    rowProps[PART_ATTR] = POSITION_ROW_PART;
    rowProps[INDEX_ATTR] = text(props.at);
    rowProps[NAME_ATTR] = text(firePairs()[props.at]);
    rowProps[COUNT_ATTR] = text(rowCells(props.at).length);
    return element(ROW_TAG, rowProps, drawn);
  }

  function PositionsTable(props) {
    var table = objectField(props.model, POSITIONS_TABLE);
    var style = { borderCollapse: COLLAPSE, overflow: AUTO };
    var tableProps = {
      className: TAB_CLASS,
      style: style,
      hidden: table[SHOWN] !== true
    };
    tableProps[PART_ATTR] = TABLE_PART;
    tableProps[SHOWN_ATTR] = text(table[SHOWN]);
    tableProps[COUNT_ATTR] = text(table[ROW_COUNT]);
    tableProps[COLUMN_ATTR] = text(table[COLUMN_COUNT]);
    tableProps[VALUE_ATTR] = text(table[CELL_COLUMN_COUNT]);
    tableProps[ALIGNMENT_ATTR] = text(table[CELL_ALIGNMENT]);
    tableProps[ALTERNATING_ATTR] = text(table[ALTERNATING_ROW_COLORS]);
    tableProps[RESIZE_ATTR] = text(table[HEADER_RESIZE_MODE]);
    tableProps[SIDE_HEAD_ATTR] = text(table[VERTICAL_HEADER_VISIBLE]);
    tableProps[EDIT_ATTR] = text(table[EDIT_TRIGGERS]);
    tableProps[SELECT_ATTR] = text(table[SELECTION_BEHAVIOR]);
    tableProps[NAME_ATTR] = text(stateColumnName());
    tableProps[DEFAULT_ATTR] = text(deltaColumnName());
    var headProps = { className: TAB_CLASS };
    headProps[PART_ATTR] = HEAD_PART;
    var headRowProps = { className: TAB_CLASS };
    headRowProps[PART_ATTR] = HEAD_ROW_PART;
    var bodyProps = { className: TAB_CLASS };
    bodyProps[PART_ATTR] = BODY_PART;
    return element(
      TABLE_TAG,
      tableProps,
      element(
        HEAD_TAG,
        headProps,
        element(
          ROW_TAG,
          headRowProps,
          columnNames().map(function (name, at) {
            return element(HeadCell, { key: String(at), name: name, at: at });
          })
        )
      ),
      element(
        BODY_TAG,
        bodyProps,
        tableRows().map(function (cells, at) {
          return element(PositionRow, { key: String(at), at: at, onFire: props.onFire });
        })
      )
    );
  }

  function BoxButton(props) {
    var value = buttonValue(props.name);
    var buttonProps = {
      className: TAB_CLASS,
      type: BUTTON_TYPE,
      onClick: function () {
        press(props.name, value);
        if (typeof props.onAnswer === "function") {
          props.onAnswer(value);
        }
      }
    };
    buttonProps[PART_ATTR] = BOX_BUTTON_PART;
    buttonProps[NAME_ATTR] = props.name;
    buttonProps[VALUE_ATTR] = text(value);
    buttonProps[DEFAULT_ATTR] = String(value === props.fallback);
    buttonProps[ARIA_LABEL] = props.name;
    return element(BUTTON_TAG, buttonProps, props.name);
  }

  function MessageBox(props) {
    var box = isPlainObject(props.box) ? props.box : {};
    var offered = boxAnswers(box);
    var boxProps = { className: TAB_CLASS };
    boxProps[PART_ATTR] = MESSAGE_BOX_PART;
    boxProps[INDEX_ATTR] = text(props.at);
    boxProps[ICON_ATTR] = text(box[BOX_ICON]);
    boxProps[KEY_ATTR] = text(box[BOX_TITLE]);
    boxProps[VALUE_ATTR] = text(box[BUTTONS_VALUE]);
    boxProps[DEFAULT_ATTR] = text(boxDefault(box));
    boxProps[COUNT_ATTR] = text(offered.length);
    var titleProps = { className: TAB_CLASS };
    titleProps[PART_ATTR] = BOX_TITLE_PART;
    var textProps = { className: TAB_CLASS, style: { whiteSpace: PRE_WRAP } };
    textProps[PART_ATTR] = BOX_TEXT_PART;
    var drawn = offered.map(function (name) {
      return element(BoxButton, {
        key: name,
        name: name,
        fallback: boxDefault(box),
        onAnswer: props.onAnswer
      });
    });
    return element(
      DIV_TAG,
      boxProps,
      element(SPAN_TAG, titleProps, text(box[BOX_TITLE])),
      element(DIV_TAG, textProps, text(box[BOX_TEXT])),
      drawn
    );
  }

  // Tab draws nothing for a payload that is not an object.
  function Tab(props) {
    if (!isPlainObject(props.model)) {
      return null;
    }
    var found = props.model;
    var box = objectField(found, CONTAINER);
    var tabProps = {
      id: props.id,
      className: TAB_CLASS,
      style: {
        display: FLEX,
        flexDirection: COLUMN_DIRECTION,
        gap: length(box[SPACING_PX]),
        minWidth: ZERO
      }
    };
    tabProps[PART_ATTR] = TAB_PART;
    tabProps[KEY_ATTR] = text(found[POOL_COLOR]);
    tabProps[NAME_ATTR] = text(found[FIRE_OUTCOME]);
    tabProps[MARGINS_ATTR] = text(box[MARGINS_SET]);
    tabProps[ARIA_LABEL] = label(found[ACCESSIBLE_NAME]);
    var outcomeProps = { className: TAB_CLASS };
    outcomeProps[PART_ATTR] = OUTCOME_PART;
    outcomeProps[VALUE_ATTR] = text(found[FIRE_OUTCOME]);
    var drawn = [
      element(SummaryGroup, { key: SUMMARY_GROUP_PART, model: found }),
      element(Note, {
        key: EMPTY_NOTE_PART,
        model: found,
        field: EMPTY_LABEL,
        part: EMPTY_NOTE_PART
      }),
      element(PositionsTable, {
        key: TABLE_PART,
        model: found,
        onFire: props.onFire
      }),
      element(Note, {
        key: FOOTER_NOTE_PART,
        model: found,
        field: FOOTER_LABEL,
        part: FOOTER_NOTE_PART
      }),
      element(SPAN_TAG, outcomeProps, text(found[FIRE_OUTCOME]))
    ];
    listField(found, BOXES).forEach(function (one, at) {
      drawn.push(
        element(MessageBox, {
          key: MESSAGE_BOX_PART + String(at),
          box: one,
          at: at,
          onAnswer: props.onAnswer
        })
      );
    });
    return element(DIV_TAG, tabProps, drawn);
  }

  // press records the last thing pressed and the argument it answered with.
  function press(name, argument) {
    lastPress = { name: name, argument: argument, action: action(name) };
    return lastPress;
  }

  function pressed() {
    return lastPress;
  }

  function heldFieldCount(found) {
    return DECLARED_FIELDS.filter(function (name) {
      return owns(found, name);
    }).length;
  }

  // Counts fields, columns, rows, labels, answers and outcomes against those held.
  function report() {
    var found = held.model;
    var table = objectField(found, POSITIONS_TABLE);
    var drawn = drawnLabels();
    return {
      declared: {
        fields: DECLARED_FIELDS.length,
        columns: table[COLUMN_COUNT],
        cells: table[CELL_COLUMN_COUNT],
        rows: table[ROW_COUNT],
        labels: publishedLabels().length,
        actions: ACTION_NAMES.length,
        answers: ANSWER_NAMES.length,
        outcomes: listField(found, OUTCOMES).length
      },
      held: {
        fields: heldFieldCount(found),
        columns: listField(table, COLUMNS).length,
        cells: rowCells(ZERO).length,
        rows: listField(table, ROWS).length,
        labels: drawn.filter(function (name) {
          return labelNamed(name) !== undefined;
        }).length,
        actions: Object.keys(objectField(found, ACTIONS)).length,
        answers: ANSWER_NAMES.filter(function (name) {
          return owns(objectField(found, BUTTON_VALUES), name);
        }).length,
        outcomes: listField(found, OUTCOMES).filter(function (name) {
          return typeof name === "string";
        }).length
      },
      faults: tabFaults.slice()
    };
  }

  function setTab(found) {
    if (!isPlainObject(found)) {
      held = null;
      tabFaults = [fault(null, null, NOT_AN_OBJECT_FAULT, kindOf(found))];
      return { declared: null, held: null, faults: tabFaults.slice() };
    }
    held = { model: found };
    tabFaults = [];
    checkFields(found);
    checkActions(found);
    checkAnswers(found);
    checkCounts(found);
    checkLabels(found);
    checkRowNames();
    checkColours(found);
    checkBagOrder(found);
    checkBoxes(found);
    checkPool(found);
    checkOutcome(found);
    return report();
  }

  // Asks METHOD once, clearing asked so a refused first ask is retried.
  function loadTab(params) {
    if (asked !== null) {
      return asked;
    }
    if (!global.acervator || typeof global.acervator.call !== "function") {
      loadFault = NO_BRIDGE;
      return Promise.resolve(null);
    }
    asked = global.acervator
      .call(METHOD, isPlainObject(params) ? params : {})
      .then(function (found) {
        loadFault = null;
        setTab(found);
        return found;
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

  function declaredNames() {
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

  function bagKeys(name) {
    return Object.keys(bag(name));
  }

  function actionNames() {
    return ACTION_NAMES.slice();
  }

  function answerNames() {
    return ANSWER_NAMES.slice();
  }

  function walkPayload(visit) {
    function descend(path, value) {
      if (isPlainObject(value)) {
        walk(path, value);
        return;
      }
      if (Array.isArray(value)) {
        value.forEach(function (one, at) {
          var inner = path + PATH_SPLIT + String(at);
          visit(inner, one);
          descend(inner, one);
        });
      }
    }
    function walk(prefix, node) {
      Object.keys(node).forEach(function (name) {
        var path = prefix ? prefix + PATH_SPLIT + name : name;
        visit(path, node[name]);
        descend(path, node[name]);
      });
    }
    if (held !== null) {
      walk(EMPTY, held.model);
    }
  }

  function kinds() {
    var found = {};
    walkPayload(function (path, value) {
      found[path] = kindOf(value);
    });
    return found;
  }

  // Every path whose value is not a string, number, flag, list, bag or null.
  function notPlainData() {
    var found = [];
    walkPayload(function (path, value) {
      var kind = kindOf(value);
      var plain =
        kind === NULL_FAULT ||
        kind === "string" ||
        kind === "number" ||
        kind === "boolean" ||
        isPlainObject(value) ||
        Array.isArray(value);
      if (!plain) {
        found.push({ path: path, kind: kind });
      }
    });
    return found;
  }

  function faults() {
    return tabFaults.slice();
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

  // flushSync makes the document current before draw returns.
  function draw(target, node) {
    var root = rootFor(target);
    global.ReactDOM.flushSync(function () {
      root.render(node);
    });
    return target;
  }

  // A payload given here is set first, so every drawn piece reads one model.
  function renderTab(target, found, handlers) {
    if (isPlainObject(found)) {
      setTab(found);
    }
    var wired = isPlainObject(handlers) ? handlers : {};
    return draw(
      target,
      element(Tab, {
        model: held === null ? null : held.model,
        onFire: wired.onFire,
        onAnswer: wired.onAnswer
      })
    );
  }

  // The named empty space the Live Bot Settings window left, or root itself.
  function spaceIn(root) {
    if (!root || typeof root.getAttribute !== "function") {
      return null;
    }
    if (root.getAttribute(PART_ATTR) === PAGE_PART) {
      return root;
    }
    if (typeof root.querySelector !== "function") {
      return null;
    }
    return root.querySelector(
      SELECT_OPEN + PART_ATTR + SELECT_IS + PAGE_PART + SELECT_CLOSE
    );
  }

  function fill(root, found, handlers) {
    var space = spaceIn(root);
    return space === null ? null : renderTab(space, found, handlers);
  }

  function forget() {
    held = null;
    tabFaults = [];
    loadFault = null;
    asked = null;
    lastPress = null;
  }

  global.acervatorSetPositionsHeld = setTab;
  global.acervatorLoadPositionsHeld = loadTab;
  global.acervatorPositionsHeld = {
    method: METHOD,
    spacePart: PAGE_PART,
    Tab: Tab,
    SummaryGroup: SummaryGroup,
    PositionsTable: PositionsTable,
    MessageBox: MessageBox,
    payload: payload,
    declaredNames: declaredNames,
    field: field,
    bag: bag,
    list: list,
    bagKeys: bagKeys,
    actionNames: actionNames,
    answerNames: answerNames,
    summaryRows: summaryRows,
    summaryRowNamed: summaryRowNamed,
    summaryValue: summaryValue,
    summaryStyleNamed: summaryStyleNamed,
    drawnLabels: drawnLabels,
    publishedLabels: publishedLabels,
    labelNamed: labelNamed,
    formatHead: formatHead,
    columnNames: columnNames,
    columnNamed: columnNamed,
    stateColumnName: stateColumnName,
    deltaColumnName: deltaColumnName,
    tableRows: tableRows,
    rowCells: rowCells,
    rowColors: rowColors,
    cellColour: cellColour,
    cellColours: cellColours,
    cellNamed: cellNamed,
    rowIdentities: rowIdentities,
    rowNamed: rowNamed,
    firePairs: firePairs,
    noCellColour: noCellColour,
    action: action,
    buttonValue: buttonValue,
    offers: offers,
    boxes: boxes,
    boxAnswers: boxAnswers,
    boxDefault: boxDefault,
    colourNamed: colourNamed,
    poolNames: poolNames,
    outcomes: outcomes,
    calls: calls,
    sheets: sheets,
    press: press,
    pressed: pressed,
    paintedStyle: paintedStyle,
    alphaFraction: alphaFraction,
    isSwappedAlpha: isSwappedAlpha,
    byteAlpha: byteAlpha,
    hexRuns: hexRuns,
    rgbaRuns: rgbaRuns,
    isReorderedKey: isReorderedKey,
    kinds: kinds,
    notPlainData: notPlainData,
    faults: faults,
    loadError: loadError,
    isLoaded: isLoaded,
    renderTab: renderTab,
    spaceIn: spaceIn,
    fill: fill,
    forget: forget
  };
})(window);
