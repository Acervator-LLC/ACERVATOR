// Draws the Journal tab from the journal_tab.state payload, holding no
// colour, size or text of its own.
(function (global) {
  "use strict";

  var METHOD = "journal_tab.state";


  var ACCESSIBLE_NAME = "accessible_name";
  var ACTIONS = "actions";
  var BOTTOM_SPLITTER = "bottom_splitter";
  var BOT_FILTER = "bot_filter";
  var BOT_LABEL = "bot_label";
  var BUTTON_ROW_ORDER = "button_row_order";
  var CALLS = "calls";
  var COLORS = "colors";
  var CONTAINER = "container";
  var DEFAULT_TEXTS = "default_texts";
  var DETAIL_GROUP = "detail_group";
  var DETAIL_VIEW = "detail_view";
  var ENTRY_COUNT = "entry_count";
  var HEADER_ORDER = "header_order";
  var JOURNAL_FILES_LABEL = "journal_files_label";
  var JOURNAL_GROUP = "journal_group";
  var JOURNAL_TABLE = "journal_table";
  var NO_TEXT = "no_text";
  var ORPHANS_LABEL = "orphans_label";
  var PERIOD_FILTER = "period_filter";
  var PERIOD_LABEL = "period_label";
  var RECON_BUTTON = "recon_button";
  var RECON_LABEL = "recon_label";
  var RECOVERY_GROUP = "recovery_group";
  var RECOVERY_ORDER = "recovery_order";
  var SKIN = "skin";
  var SNAPSHOT_BUTTON = "snapshot_button";
  var SNAPSHOT_LABEL = "snapshot_label";
  var SPLITTER = "splitter";
  var STATS_LABEL = "stats_label";

  // DECLARED_FIELDS lists every top-level field of the payload.
  var DECLARED_FIELDS = [
    ACCESSIBLE_NAME,
    ACTIONS,
    "all_bots_item",
    "bearish",
    BOTTOM_SPLITTER,
    BOT_FILTER,
    BOT_LABEL,
    "bullish",
    "bus_topics",
    BUTTON_ROW_ORDER,
    "call_names",
    CALLS,
    COLORS,
    CONTAINER,
    DEFAULT_TEXTS,
    "defaults",
    DETAIL_GROUP,
    DETAIL_VIEW,
    ENTRY_COUNT,
    "entry_query",
    "formats",
    HEADER_ORDER,
    JOURNAL_FILES_LABEL,
    JOURNAL_GROUP,
    JOURNAL_TABLE,
    "labels",
    "no_cell_color",
    "no_data",
    "no_detail_html",
    "no_selection_index",
    NO_TEXT,
    ORPHANS_LABEL,
    "period_items",
    PERIOD_FILTER,
    PERIOD_LABEL,
    RECON_BUTTON,
    RECON_LABEL,
    RECOVERY_GROUP,
    RECOVERY_ORDER,
    "seconds_per_minute",
    SKIN,
    "slices",
    SNAPSHOT_BUTTON,
    SNAPSHOT_LABEL,
    "snapshot_minute_cutoff_s",
    SPLITTER,
    STATS_LABEL,
    "timer_delays_ms",
    "timers",
    "titles"
  ];

  // NULLABLE_FIELDS names the fields the surface publishes as nothing.
  var NULLABLE_FIELDS = ["no_cell_color", "no_data"];

  // SLOT_FIELDS names every field one published order list may point at.
  var SLOT_FIELDS = [
    STATS_LABEL,
    BOT_LABEL,
    BOT_FILTER,
    PERIOD_LABEL,
    PERIOD_FILTER,
    JOURNAL_GROUP,
    BOTTOM_SPLITTER,
    DETAIL_GROUP,
    RECOVERY_GROUP,
    SNAPSHOT_LABEL,
    RECON_LABEL,
    ORPHANS_LABEL,
    JOURNAL_FILES_LABEL,
    RECON_BUTTON,
    SNAPSHOT_BUTTON
  ];


  var TEXT = "text";
  var STYLE_SHEET = "style_sheet";
  var TITLE = "title";
  var ENABLED = "enabled";

  var MARGINS = "margins_px";
  var SPACING = "spacing_px";

  var ITEMS = "items";
  var INDEX = "index";
  var SIGNALS_BLOCKED = "signals_blocked";
  var MINIMUM_WIDTH = "minimum_width_px";

  var ORIENTATION = "orientation";
  var HANDLE_WIDTH = "handle_width_px";
  var CHILDREN_COLLAPSIBLE = "children_collapsible";
  var REQUESTED_SIZES = "requested_sizes_px";
  var CHILDREN = "children";

  var COLUMNS = "columns";
  var COLUMN_COUNT = "column_count";
  var HEADER_RESIZE_MODE = "header_resize_mode";
  var ALTERNATING_ROW_COLORS = "alternating_row_colors";
  var EDIT_TRIGGERS = "edit_triggers";
  var VERTICAL_HEADER_VISIBLE = "vertical_header_visible";
  var SELECTION_BEHAVIOR = "selection_behavior";
  var CELL_ALIGNMENT = "cell_alignment";
  var CELL_ALIGNMENT_VALUE = "cell_alignment_value";
  var ROW_COUNT = "row_count";
  var ROWS = "rows";
  var ROW_COLORS = "row_colors";

  var READ_ONLY = "read_only";
  var FONT_FAMILY = "font_family";
  var FONT_POINT_SIZE = "font_point_size";
  var LINE_DEFAULTS = "line_defaults";

  var INDENT = "indent";
  var LABEL_FIELD = "label";
  var LABEL_COLOR = "label_color";
  var GAP = "gap";
  var VALUE = "value";
  var VALUE_COLOR = "value_color";
  var BOLD = "bold";

  var LINE_FIELDS = [INDENT, LABEL_FIELD, LABEL_COLOR, GAP, VALUE, VALUE_COLOR, BOLD];

  var CELL_CHANGED = "journal_table.currentCellChanged";
  var BOT_FILTER_CHANGED = "bot_filter.currentIndexChanged";
  var PERIOD_FILTER_CHANGED = "period_filter.currentIndexChanged";

  var STRETCH_SLOT = "stretch";
  var BUTTON_ROW_SLOT = "button_row";


  var MISSING_FAULT = "missing";
  var NULL_FAULT = "null";
  var NOT_AN_OBJECT_FAULT = "not-an-object";
  var WRONG_TYPE_FAULT = "wrong-type";
  var SHORT_LIST_FAULT = "short-list";
  var UNSLOTTED_FAULT = "unslotted";
  var NOT_CSS_FAULT = "not-css";
  var QT_COLOUR_FAULT = "qt-colour";

  var ROW_AT = "row:";
  var CELL_AT = "/cell:";
  var LINE_AT = "line:";
  var PATH_SPLIT = ".";
  var EMPTY = "";

  var NO_BRIDGE = "the preload bridge is not present";

  // STEP and ZERO are counted rather than written, so no number is spelled.
  var STEP = Number(true);
  var ZERO = Number(EMPTY);

  // QT_ONLY names the Qt paint function no stylesheet can run.
  var QT_ONLY = "qlineargradient";
  // Qt reads an eight-digit hex colour alpha first; CSS reads it last.
  var HEX_ARGB = "AARRGGBB";
  // Qt counts an rgba alpha in bytes; CSS counts it as a fraction.
  var RGBA_OPEN = "rgba(";
  var HEX_DIGITS = "0123456789abcdefABCDEF";
  var HOVER_STATE = ":hover";
  // The colon is taken off HOVER_STATE, since the surface publishes one.
  var COLON = HOVER_STATE.charAt(ZERO);
  var SEMICOLON = ";";
  var HASH = "#";
  var PERCENT = "%";


  var TAB_CLASS = "acervator-journal-tab";

  var DIV_TAG = "div";
  var SPAN_TAG = "span";
  var TABLE_TAG = "table";
  var HEAD_TAG = "thead";
  var BODY_TAG = "tbody";
  var ROW_TAG = "tr";
  var HEAD_CELL_TAG = "th";
  var CELL_TAG = "td";
  var BUTTON_TAG = "button";
  var BUTTON_TYPE = "button";
  var SELECT_TAG = "select";
  var OPTION_TAG = "option";
  var LABEL_TAG = "label";

  var PART_ATTR = "data-part";
  var SLOT_ATTR = "data-slot";
  var INDEX_ATTR = "data-index";
  var ROW_ATTR = "data-row";
  var COLUMN_ATTR = "data-column";
  var LINE_ATTR = "data-line";
  var ACTION_ATTR = "data-action";
  var ITEM_DATA_ATTR = "data-item-data";
  var ALIGNMENT_ATTR = "data-alignment";
  var ALIGNMENT_VALUE_ATTR = "data-alignment-value";
  var ALTERNATING_ATTR = "data-alternating";
  var EDIT_TRIGGERS_ATTR = "data-edit-triggers";
  var SELECTION_ATTR = "data-selection-behavior";
  var RESIZE_MODE_ATTR = "data-resize-mode";
  var COLLAPSIBLE_ATTR = "data-collapsible";
  var ORIENTATION_ATTR = "data-orientation";
  var BLOCKED_ATTR = "data-signals-blocked";
  var HOVERED_ATTR = "data-hovered";
  var DECLARED_ROWS_ATTR = "data-declared-rows";
  var HELD_ROWS_ATTR = "data-held-rows";
  var DECLARED_COLUMNS_ATTR = "data-declared-columns";
  var HELD_COLUMNS_ATTR = "data-held-columns";
  var DECLARED_PANES_ATTR = "data-declared-panes";
  var HELD_PANES_ATTR = "data-held-panes";
  var DECLARED_LINES_ATTR = "data-declared-lines";
  var ARIA_LABEL = "aria-label";
  var ARIA_ORIENTATION = "aria-orientation";
  var ARIA_READONLY = "aria-readonly";
  var SEPARATOR_ROLE = "separator";

  var TAB_PART = "tab";
  var HEADER_PART = "header";
  var STRETCH_PART = "stretch";
  var LABEL_PART = "label";
  var FILTER_PART = "filter";
  var SPLITTER_PART = "splitter";
  var HANDLE_PART = "handle";
  var PANE_PART = "pane";
  var GROUP_PART = "group";
  var GROUP_TITLE_PART = "group-title";
  var GROUP_BODY_PART = "group-body";
  var TABLE_PART = "table";
  var TABLE_SCROLL_PART = "table-scroll";
  var HEAD_ROW_PART = "head-row";
  var COLUMN_PART = "column";
  var ROW_PART = "row";
  var CELL_PART = "cell";
  var DETAIL_PART = "detail-pane";
  var DETAIL_LINE_PART = "detail-line";
  var DETAIL_LABEL_PART = "detail-label";
  var DETAIL_VALUE_PART = "detail-value";
  var RECOVERY_PART = "recovery";
  var BUTTON_ROW_PART = "button-row";
  var BUTTON_PART = "button";

  var ROW = "row";
  var COLUMN = "column";
  var FLEX = "flex";
  var NONE = "none";
  var AUTO = "auto";
  var HIDDEN = "hidden";
  var FIXED = "fixed";
  var COLLAPSE = "collapse";
  var BORDER_BOX = "border-box";
  var FULL = "100%";
  var NOWRAP = "nowrap";
  var PRE_WRAP = "pre-wrap";
  var ELLIPSIS = "ellipsis";
  var CENTER = "center";
  var HORIZONTAL = "horizontal";
  var COL_RESIZE = "col-resize";
  var ROW_RESIZE = "row-resize";
  var SELECT_TEXT = "text";
  var BOLD_WEIGHT = "bold";
  var MOUSE_MOVE = "mousemove";
  var MOUSE_UP = "mouseup";

  var PX = "px";
  var PT = "pt";
  var COMMA = ",";
  var VAR_OPEN = "var(--";
  var VAR_CLOSE = ")";
  var CALC_OPEN = "calc(";
  // The unit factor that turns a unitless token into a CSS length.
  var PX_FACTOR = " * 1px)";

  // ALIGNMENT_STYLE maps each published alignment word to CSS.
  var ALIGNMENT_STYLE = { AlignCenter: { textAlign: CENTER } };

  var held = null;
  var journalFaults = [];
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

  function isFilledText(value) {
    return typeof value === "string" && value.length ? true : false;
  }

  function fault(where, name, kind, detail) {
    return { where: where, field: name, fault: kind, detail: detail };
  }

  // text returns String(value), or undefined for null and undefined.
  function text(value) {
    return value === null || value === undefined ? undefined : String(value);
  }

  // label returns value when it is filled text, else undefined.
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


  // `table_cells.js` owns the one-carrier rule that names a token.
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

  // A token holds a bare number, so `calc` scales it to a CSS length.
  function length(value) {
    if (value === null || value === undefined) {
      return undefined;
    }
    var name = variableFor(value);
    if (name === undefined) {
      return String(value) + PX;
    }
    return CALC_OPEN + VAR_OPEN + name + COMMA + String(value) + VAR_CLOSE + PX_FACTOR;
  }

  // Qt sizes the detail font in points, so the pane asks for points.
  function points(value) {
    return value === null || value === undefined ? undefined : String(value) + PT;
  }

  // `header_strip.js` owns the Qt style-sheet rule.
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

  // The hex word after the first hash, empty when the value carries none.
  function hexWord(value) {
    var parts = afterFirst(value, HASH);
    if (!parts.length) {
      return EMPTY;
    }
    var rest = String(parts.shift());
    var at = ZERO;
    while (at < rest.length && carries(HEX_DIGITS, rest.charAt(at))) {
      at += STEP;
    }
    return rest.slice(ZERO, at);
  }

  // Whether one value counts its alpha in bytes, as Qt does and CSS not.
  function byteAlpha(value) {
    var parts = afterFirst(value, RGBA_OPEN);
    if (!parts.length) {
      return false;
    }
    var fields = String(parts.shift()).split(VAR_CLOSE).shift().split(COMMA);
    fields.shift();
    fields.shift();
    fields.shift();
    var alpha = fields.shift();
    if (alpha === undefined) {
      return false;
    }
    return !carries(alpha, PATH_SPLIT) && !carries(alpha, PERCENT);
  }

  // The reason CSS would read one declared value as a different colour.
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

  // The style one named Qt state paints, which no inline style can hold.
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

  function merged(first, second) {
    var found = copyOf(first);
    Object.keys(second).forEach(function (name) {
      found[name] = second[name];
    });
    return found;
  }


  function withAlignment(style, word) {
    if (!owns(ALIGNMENT_STYLE, word)) {
      return style;
    }
    var aligned = ALIGNMENT_STYLE[word];
    Object.keys(aligned).forEach(function (name) {
      style[name] = aligned[name];
    });
    return style;
  }

  // The four published margins, left, top, right and bottom in order.
  var PADDING_SIDES = ["paddingLeft", "paddingTop", "paddingRight", "paddingBottom"];

  function containerStyle(model) {
    var box = objectField(model, CONTAINER);
    var style = {
      display: FLEX,
      flexDirection: COLUMN,
      height: FULL,
      boxSizing: BORDER_BOX,
      overflow: HIDDEN
    };
    listField(box, MARGINS).forEach(function (one, at) {
      if (at < PADDING_SIDES.length) {
        style[PADDING_SIDES[at]] = length(one);
      }
    });
    if (owns(box, SPACING)) {
      style.gap = length(box[SPACING]);
    }
    return style;
  }

  function element() {
    return global.React.createElement.apply(null, arguments);
  }

  function hooks() {
    return global.React;
  }


  // Stretch takes the room Qt's addStretch takes in the same row.
  function Stretch() {
    var props = { className: TAB_CLASS, style: { flex: AUTO } };
    props[PART_ATTR] = STRETCH_PART;
    props[SLOT_ATTR] = STRETCH_SLOT;
    return element(DIV_TAG, props, null);
  }

  function TextLabel(props) {
    var declared = isPlainObject(props.declared) ? props.declared : {};
    var style = styleOf(declared[STYLE_SHEET]);
    style.flex = NONE;
    style.whiteSpace = NOWRAP;
    var labelProps = { className: TAB_CLASS, style: style, htmlFor: props.htmlFor };
    labelProps[PART_ATTR] = LABEL_PART;
    labelProps[SLOT_ATTR] = props.slot;
    labelProps[ARIA_LABEL] = label(declared[TEXT]);
    return element(
      props.htmlFor === undefined ? DIV_TAG : LABEL_TAG,
      labelProps,
      text(declared[TEXT])
    );
  }

  // A drop list draws one option per published item, chosen by position.
  function Filter(props) {
    var declared = isPlainObject(props.declared) ? props.declared : {};
    var items = listField(declared, ITEMS);
    var selectProps = {
      className: TAB_CLASS,
      style: { minWidth: length(declared[MINIMUM_WIDTH]), flex: NONE },
      id: props.slot,
      value: String(declared[INDEX]),
      onChange: typeof props.onPick === "function" ? props.onPick : function () {}
    };
    selectProps[PART_ATTR] = FILTER_PART;
    selectProps[SLOT_ATTR] = props.slot;
    selectProps[INDEX_ATTR] = text(declared[INDEX]);
    selectProps[BLOCKED_ATTR] = text(declared[SIGNALS_BLOCKED]);
    selectProps[ACTION_ATTR] = text(props.action);
    selectProps[ARIA_LABEL] = label(props.name);
    return element(
      SELECT_TAG,
      selectProps,
      items.map(function (item, at) {
        var pair = Array.isArray(item) ? item : [];
        var optionProps = { key: String(at), value: String(at) };
        optionProps[INDEX_ATTR] = String(at);
        optionProps[ITEM_DATA_ATTR] = text(pair[STEP]);
        return element(OPTION_TAG, optionProps, text(pair[ZERO]));
      })
    );
  }

  // A group box draws its title above its body, as Qt's frame does.
  function GroupBox(props) {
    var declared = isPlainObject(props.declared) ? props.declared : {};
    var style = styleOf(declared[STYLE_SHEET]);
    style.display = FLEX;
    style.flexDirection = COLUMN;
    style.flex = AUTO;
    style.overflow = HIDDEN;
    style.boxSizing = BORDER_BOX;
    var groupProps = { className: TAB_CLASS, style: style };
    groupProps[PART_ATTR] = GROUP_PART;
    groupProps[SLOT_ATTR] = props.slot;
    groupProps[ARIA_LABEL] = label(declared[TITLE]);
    var titleProps = { className: TAB_CLASS, style: { flex: NONE } };
    titleProps[PART_ATTR] = GROUP_TITLE_PART;
    titleProps[SLOT_ATTR] = props.slot;
    var bodyProps = {
      className: TAB_CLASS,
      style: { display: FLEX, flexDirection: COLUMN, flex: AUTO, overflow: HIDDEN }
    };
    bodyProps[PART_ATTR] = GROUP_BODY_PART;
    bodyProps[SLOT_ATTR] = props.slot;
    return element(
      DIV_TAG,
      groupProps,
      element(DIV_TAG, titleProps, text(declared[TITLE])),
      element(DIV_TAG, bodyProps, props.children)
    );
  }

  function HeaderCell(props) {
    var cellProps = {
      className: TAB_CLASS,
      style: { textAlign: CENTER, whiteSpace: NOWRAP }
    };
    cellProps[PART_ATTR] = COLUMN_PART;
    cellProps[COLUMN_ATTR] = String(props.at);
    cellProps[ARIA_LABEL] = label(props.name);
    return element(HEAD_CELL_TAG, cellProps, text(props.name));
  }

  function BodyCell(props) {
    var table = props.table;
    var style = { whiteSpace: NOWRAP, overflow: HIDDEN, textOverflow: ELLIPSIS };
    if (isFilledText(props.color)) {
      style.color = colour(props.color);
    }
    withAlignment(style, table[CELL_ALIGNMENT]);
    var cellProps = { className: TAB_CLASS, style: style };
    cellProps[PART_ATTR] = CELL_PART;
    cellProps[COLUMN_ATTR] = String(props.at);
    cellProps[ALIGNMENT_ATTR] = text(table[CELL_ALIGNMENT]);
    cellProps[ALIGNMENT_VALUE_ATTR] = text(table[CELL_ALIGNMENT_VALUE]);
    cellProps[ARIA_LABEL] = label(listField(table, COLUMNS)[props.at]);
    return element(CELL_TAG, cellProps, text(props.value));
  }

  function EntryRow(props) {
    var table = props.table;
    var cells = Array.isArray(props.cells) ? props.cells : [];
    var colors = Array.isArray(props.colors) ? props.colors : [];
    var rowProps = { className: TAB_CLASS };
    rowProps[PART_ATTR] = ROW_PART;
    rowProps[ROW_ATTR] = String(props.at);
    rowProps[ACTION_ATTR] = text(props.action);
    rowProps[DECLARED_COLUMNS_ATTR] = text(table[COLUMN_COUNT]);
    rowProps[HELD_COLUMNS_ATTR] = String(cells.length);
    return element(
      ROW_TAG,
      rowProps,
      cells.map(function (one, at) {
        return element(BodyCell, {
          key: String(at),
          table: table,
          value: one,
          color: colors[at],
          at: at
        });
      })
    );
  }

  // The trade table stretches every column, as Qt's Stretch mode does.
  function JournalTable(props) {
    var model = isPlainObject(props.model) ? props.model : {};
    var table = objectField(model, JOURNAL_TABLE);
    var rows = listField(table, ROWS);
    var colors = listField(table, ROW_COLORS);
    var names = listField(table, COLUMNS);
    var tableProps = {
      className: TAB_CLASS,
      style: {
        tableLayout: FIXED,
        width: FULL,
        borderCollapse: COLLAPSE,
        userSelect: NONE
      }
    };
    tableProps[PART_ATTR] = TABLE_PART;
    tableProps[ARIA_LABEL] = label(objectField(model, JOURNAL_GROUP)[TITLE]);
    tableProps[RESIZE_MODE_ATTR] = text(table[HEADER_RESIZE_MODE]);
    tableProps[ALTERNATING_ATTR] = text(table[ALTERNATING_ROW_COLORS]);
    tableProps[EDIT_TRIGGERS_ATTR] = text(table[EDIT_TRIGGERS]);
    tableProps[SELECTION_ATTR] = text(table[SELECTION_BEHAVIOR]);
    tableProps[DECLARED_ROWS_ATTR] = text(table[ROW_COUNT]);
    tableProps[HELD_ROWS_ATTR] = String(rows.length);
    tableProps[DECLARED_COLUMNS_ATTR] = text(table[COLUMN_COUNT]);
    tableProps[HELD_COLUMNS_ATTR] = String(names.length);
    var headProps = { className: TAB_CLASS };
    headProps[PART_ATTR] = HEAD_ROW_PART;
    headProps[SLOT_ATTR] = COLUMNS;
    var action = objectField(model, ACTIONS)[CELL_CHANGED];
    var scrollProps = {
      className: TAB_CLASS,
      style: { flex: AUTO, overflow: AUTO },
      tabIndex: ZERO
    };
    scrollProps[PART_ATTR] = TABLE_SCROLL_PART;
    scrollProps[SLOT_ATTR] = JOURNAL_TABLE;
    return element(
      DIV_TAG,
      scrollProps,
      element(
        TABLE_TAG,
        tableProps,
        table[VERTICAL_HEADER_VISIBLE] === true
          ? null
          : element(
              HEAD_TAG,
              null,
              element(
                ROW_TAG,
                headProps,
                names.map(function (name, at) {
                  return element(HeaderCell, { key: String(at), name: name, at: at });
                })
              )
            ),
        element(
          BODY_TAG,
          null,
          rows.map(function (row, at) {
            return element(EntryRow, {
              key: String(at),
              table: table,
              cells: row,
              colors: colors[at],
              action: action,
              at: at
            });
          })
        )
      )
    );
  }

  // One detail line draws its label and its value as text, never markup.
  function DetailLine(props) {
    var line = isPlainObject(props.line) ? props.line : {};
    var lineProps = { className: TAB_CLASS, style: { whiteSpace: PRE_WRAP } };
    lineProps[PART_ATTR] = DETAIL_LINE_PART;
    lineProps[LINE_ATTR] = String(props.at);
    var drawn = [];
    if (isFilledText(line[INDENT])) {
      drawn.push(line[INDENT]);
    }
    if (isFilledText(line[LABEL_FIELD])) {
      var labelStyle = {};
      if (isFilledText(line[LABEL_COLOR])) {
        labelStyle.color = colour(line[LABEL_COLOR]);
      }
      var labelProps = { key: DETAIL_LABEL_PART, className: TAB_CLASS };
      labelProps.style = labelStyle;
      labelProps[PART_ATTR] = DETAIL_LABEL_PART;
      labelProps[LINE_ATTR] = String(props.at);
      drawn.push(element(SPAN_TAG, labelProps, text(line[LABEL_FIELD])));
    }
    if (isFilledText(line[GAP])) {
      drawn.push(line[GAP]);
    }
    var valueStyle = {};
    if (isFilledText(line[VALUE_COLOR])) {
      valueStyle.color = colour(line[VALUE_COLOR]);
    }
    if (line[BOLD] === true) {
      valueStyle.fontWeight = BOLD_WEIGHT;
    }
    var valueProps = { key: DETAIL_VALUE_PART, className: TAB_CLASS };
    valueProps.style = valueStyle;
    valueProps[PART_ATTR] = DETAIL_VALUE_PART;
    valueProps[LINE_ATTR] = String(props.at);
    drawn.push(element(SPAN_TAG, valueProps, text(line[VALUE])));
    return element(DIV_TAG, lineProps, drawn);
  }

  // The detail pane draws the published lines, not the marked-up string.
  function DetailPane(props) {
    var model = isPlainObject(props.model) ? props.model : {};
    var declared = objectField(model, DETAIL_VIEW);
    var lines = listField(declared, ROWS);
    var style = styleOf(declared[STYLE_SHEET]);
    style.fontFamily = text(declared[FONT_FAMILY]);
    style.fontSize = points(declared[FONT_POINT_SIZE]);
    style.flex = AUTO;
    style.overflow = AUTO;
    style.userSelect = SELECT_TEXT;
    style.whiteSpace = PRE_WRAP;
    var paneProps = { className: TAB_CLASS, style: style, tabIndex: ZERO };
    paneProps[PART_ATTR] = DETAIL_PART;
    paneProps[SLOT_ATTR] = DETAIL_VIEW;
    paneProps[ARIA_LABEL] = label(objectField(model, DETAIL_GROUP)[TITLE]);
    paneProps[ARIA_READONLY] = String(declared[READ_ONLY] === true);
    paneProps[DECLARED_LINES_ATTR] = String(lines.length);
    return element(
      DIV_TAG,
      paneProps,
      lines.map(function (line, at) {
        return element(DetailLine, { key: String(at), line: line, at: at });
      })
    );
  }

  // A button paints its hover style while the pointer rests on it.
  function ActionButton(props) {
    var declared = isPlainObject(props.declared) ? props.declared : {};
    var state = hooks().useState(false);
    var hovered = state.shift();
    var setHovered = state.shift();
    var base = styleOf(declared[STYLE_SHEET]);
    var style = hovered
      ? merged(base, stateStyle(declared[STYLE_SHEET], HOVER_STATE))
      : base;
    var buttonProps = {
      className: TAB_CLASS,
      style: style,
      type: BUTTON_TYPE,
      disabled: declared[ENABLED] === false,
      onMouseEnter: function () {
        setHovered(true);
      },
      onMouseLeave: function () {
        setHovered(false);
      }
    };
    buttonProps[PART_ATTR] = BUTTON_PART;
    buttonProps[SLOT_ATTR] = props.slot;
    buttonProps[HOVERED_ATTR] = String(hovered);
    buttonProps[ACTION_ATTR] = text(props.action);
    buttonProps[ARIA_LABEL] = label(declared[TEXT]);
    return element(BUTTON_TAG, buttonProps, text(declared[TEXT]));
  }

  function ButtonRow(props) {
    var model = props.model;
    var rowProps = {
      className: TAB_CLASS,
      style: { display: FLEX, flexDirection: ROW, flex: NONE }
    };
    rowProps[PART_ATTR] = BUTTON_ROW_PART;
    rowProps[SLOT_ATTR] = BUTTON_ROW_SLOT;
    return element(
      DIV_TAG,
      rowProps,
      listField(model, BUTTON_ROW_ORDER).map(function (slot) {
        return element(ActionButton, {
          key: slot,
          slot: slot,
          declared: objectField(model, slot),
          action: objectField(model, ACTIONS)[slot]
        });
      })
    );
  }

  // The recovery pane draws its lines and its buttons in published order.
  function RecoveryPane(props) {
    var model = props.model;
    var paneProps = {
      className: TAB_CLASS,
      style: { display: FLEX, flexDirection: COLUMN, flex: AUTO, overflow: AUTO }
    };
    paneProps[PART_ATTR] = RECOVERY_PART;
    paneProps[SLOT_ATTR] = RECOVERY_GROUP;
    return element(
      DIV_TAG,
      paneProps,
      listField(model, RECOVERY_ORDER).map(function (slot) {
        if (slot === STRETCH_SLOT) {
          return element(Stretch, { key: slot });
        }
        if (slot === BUTTON_ROW_SLOT) {
          return element(ButtonRow, { key: slot, model: model });
        }
        return element(TextLabel, {
          key: slot,
          slot: slot,
          declared: objectField(model, slot)
        });
      })
    );
  }

  function HeaderRow(props) {
    var model = props.model;
    var box = objectField(model, CONTAINER);
    var rowProps = {
      className: TAB_CLASS,
      style: {
        display: FLEX,
        flexDirection: ROW,
        alignItems: CENTER,
        flex: NONE,
        gap: length(box[SPACING])
      }
    };
    rowProps[PART_ATTR] = HEADER_PART;
    rowProps[SLOT_ATTR] = HEADER_ORDER;
    var changedBy = {};
    changedBy[BOT_FILTER] = BOT_FILTER_CHANGED;
    changedBy[PERIOD_FILTER] = PERIOD_FILTER_CHANGED;
    var namedBy = {};
    namedBy[BOT_FILTER] = BOT_LABEL;
    namedBy[PERIOD_FILTER] = PERIOD_LABEL;
    var pointsAt = {};
    pointsAt[BOT_LABEL] = BOT_FILTER;
    pointsAt[PERIOD_LABEL] = PERIOD_FILTER;
    return element(
      DIV_TAG,
      rowProps,
      listField(model, HEADER_ORDER).map(function (slot) {
        if (slot === STRETCH_SLOT) {
          return element(Stretch, { key: slot });
        }
        if (owns(changedBy, slot)) {
          return element(Filter, {
            key: slot,
            slot: slot,
            declared: objectField(model, slot),
            name: objectField(model, namedBy[slot])[TEXT],
            action: objectField(model, ACTIONS)[changedBy[slot]],
            onPick: props.onPick
          });
        }
        return element(TextLabel, {
          key: slot,
          slot: slot,
          declared: objectField(model, slot),
          htmlFor: pointsAt[slot]
        });
      })
    );
  }

  function isAcross(declared) {
    return declared[ORIENTATION] === HORIZONTAL;
  }

  function Handle(props) {
    var declared = props.declared;
    var across = isAcross(declared);
    var style = { flex: NONE, cursor: across ? COL_RESIZE : ROW_RESIZE };
    if (across) {
      style.width = length(declared[HANDLE_WIDTH]);
    } else {
      style.height = length(declared[HANDLE_WIDTH]);
    }
    var handleProps = {
      className: TAB_CLASS,
      style: style,
      role: SEPARATOR_ROLE,
      onMouseDown: props.onGrab
    };
    handleProps[PART_ATTR] = HANDLE_PART;
    handleProps[INDEX_ATTR] = String(props.at);
    handleProps[SLOT_ATTR] = props.slot;
    handleProps[ARIA_ORIENTATION] = text(declared[ORIENTATION]);
    return element(DIV_TAG, handleProps, null);
  }

  // A splitter draws one pane per child with a draggable handle between.
  function Splitter(props) {
    var declared = isPlainObject(props.declared) ? props.declared : {};
    var across = isAcross(declared);
    var state = hooks().useState(listField(declared, REQUESTED_SIZES));
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
        var lowest =
          declared[CHILDREN_COLLAPSIBLE] === false ? declared[HANDLE_WIDTH] : ZERO;

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

    var splitterProps = {
      className: TAB_CLASS,
      style: {
        display: FLEX,
        flexDirection: across ? ROW : COLUMN,
        flex: AUTO,
        overflow: HIDDEN
      }
    };
    splitterProps[PART_ATTR] = SPLITTER_PART;
    splitterProps[SLOT_ATTR] = props.slot;
    splitterProps[ORIENTATION_ATTR] = text(declared[ORIENTATION]);
    splitterProps[COLLAPSIBLE_ATTR] = text(declared[CHILDREN_COLLAPSIBLE]);
    splitterProps[DECLARED_PANES_ATTR] = String(listField(declared, CHILDREN).length);
    splitterProps[HELD_PANES_ATTR] = String(props.panes.length);
    var drawn = [];
    props.panes.forEach(function (child, at) {
      if (drawn.length) {
        drawn.push(
          element(Handle, {
            key: HANDLE_PART + String(at),
            at: at - STEP,
            slot: props.slot,
            declared: declared,
            onGrab: grab(at - STEP)
          })
        );
      }
      var paneProps = {
        key: PANE_PART + String(at),
        className: TAB_CLASS,
        style: {
          display: FLEX,
          flexDirection: COLUMN,
          overflow: HIDDEN,
          flex: String(at < sizes.length ? sizes[at] : EMPTY)
        },
        ref: keep(at)
      };
      paneProps[PART_ATTR] = PANE_PART;
      paneProps[INDEX_ATTR] = String(at);
      paneProps[SLOT_ATTR] = child.slot;
      drawn.push(element(DIV_TAG, paneProps, child.node));
    });
    return element(DIV_TAG, splitterProps, drawn);
  }

  // `Tab` draws nothing for a payload that is not an object.
  function Tab(props) {
    if (!isPlainObject(props.model)) {
      return null;
    }
    var model = props.model;
    var bottom = element(Splitter, {
      slot: BOTTOM_SPLITTER,
      declared: objectField(model, BOTTOM_SPLITTER),
      panes: [
        {
          slot: DETAIL_GROUP,
          node: element(
            GroupBox,
            { slot: DETAIL_GROUP, declared: objectField(model, DETAIL_GROUP) },
            element(DetailPane, { model: model })
          )
        },
        {
          slot: RECOVERY_GROUP,
          node: element(
            GroupBox,
            { slot: RECOVERY_GROUP, declared: objectField(model, RECOVERY_GROUP) },
            element(RecoveryPane, { model: model })
          )
        }
      ]
    });
    var outer = element(Splitter, {
      slot: SPLITTER,
      declared: objectField(model, SPLITTER),
      panes: [
        {
          slot: JOURNAL_GROUP,
          node: element(
            GroupBox,
            { slot: JOURNAL_GROUP, declared: objectField(model, JOURNAL_GROUP) },
            element(JournalTable, { model: model })
          )
        },
        { slot: BOTTOM_SPLITTER, node: bottom }
      ]
    });
    var tabProps = { id: props.id, className: TAB_CLASS, style: containerStyle(model) };
    tabProps[PART_ATTR] = TAB_PART;
    tabProps[ARIA_LABEL] = label(model[ACCESSIBLE_NAME]);
    return element(
      DIV_TAG,
      tabProps,
      element(HeaderRow, { model: model, onPick: props.onPick }),
      outer
    );
  }


  function checkFields(model) {
    DECLARED_FIELDS.forEach(function (name) {
      if (!owns(model, name)) {
        journalFaults.push(fault(null, name, MISSING_FAULT, null));
        return;
      }
      if (model[name] === null && !contains(NULLABLE_FIELDS, name)) {
        journalFaults.push(fault(null, name, NULL_FAULT, null));
      }
    });
  }

  // A wrong type is named only where the surface publishes a default of
  // the same meaning to measure it against.
  function checkTypeAgainst(where, bag, name, against) {
    if (against === null || against === undefined) {
      return;
    }
    if (!owns(bag, name)) {
      journalFaults.push(fault(where, name, MISSING_FAULT, null));
      return;
    }
    if (bag[name] === null) {
      journalFaults.push(fault(where, name, NULL_FAULT, null));
      return;
    }
    if (kindOf(bag[name]) !== kindOf(against)) {
      journalFaults.push(fault(where, name, WRONG_TYPE_FAULT, kindOf(bag[name])));
    }
  }

  function checkSlots(model, name) {
    listField(model, name).forEach(function (slot) {
      if (slot === STRETCH_SLOT || slot === BUTTON_ROW_SLOT) {
        return;
      }
      if (!contains(SLOT_FIELDS, slot)) {
        journalFaults.push(fault(name, slot, UNSLOTTED_FAULT, null));
      }
    });
  }

  function checkSheet(where, name, sheet) {
    declarations(sheet).forEach(function (one) {
      if (carries(one.value, QT_ONLY)) {
        journalFaults.push(fault(where, name, NOT_CSS_FAULT, one.property));
        return;
      }
      if (qtColour(one.value) !== undefined) {
        journalFaults.push(fault(where, name, QT_COLOUR_FAULT, one.property));
      }
    });
  }

  function checkSheets(model) {
    var sheets = objectField(model, SKIN);
    Object.keys(sheets).forEach(function (name) {
      checkSheet(SKIN, name, sheets[name]);
    });
  }

  function checkTable(model) {
    var table = objectField(model, JOURNAL_TABLE);
    var rows = listField(table, ROWS);
    var colors = listField(table, ROW_COLORS);
    if (colors.length !== rows.length) {
      journalFaults.push(
        fault(JOURNAL_TABLE, ROW_COLORS, SHORT_LIST_FAULT, colors.length)
      );
    }
    rows.forEach(function (row, at) {
      var where = ROW_AT + String(at);
      if (!Array.isArray(row)) {
        journalFaults.push(fault(where, null, NOT_AN_OBJECT_FAULT, kindOf(row)));
        return;
      }
      if (row.length !== table[COLUMN_COUNT]) {
        journalFaults.push(fault(where, ROWS, SHORT_LIST_FAULT, row.length));
      }
      row.forEach(function (one, column) {
        if (kindOf(one) !== kindOf(model[NO_TEXT])) {
          journalFaults.push(
            fault(where + CELL_AT + String(column), TEXT, WRONG_TYPE_FAULT, kindOf(one))
          );
        }
      });
    });
  }

  function checkLines(model) {
    var declared = objectField(model, DETAIL_VIEW);
    var against = objectField(declared, LINE_DEFAULTS);
    listField(declared, ROWS).forEach(function (line, at) {
      var where = LINE_AT + String(at);
      if (!isPlainObject(line)) {
        journalFaults.push(fault(where, null, NOT_AN_OBJECT_FAULT, kindOf(line)));
        return;
      }
      LINE_FIELDS.forEach(function (name) {
        if (!owns(line, name)) {
          journalFaults.push(fault(where, name, MISSING_FAULT, null));
        }
      });
      LINE_FIELDS.forEach(function (name) {
        checkTypeAgainst(where, line, name, against[name]);
      });
    });
  }

  function heldFieldCount() {
    return DECLARED_FIELDS.filter(function (name) {
      return held !== null && owns(held.model, name);
    }).length;
  }

  // Counts fields, table rows and detail lines declared against held.
  function report() {
    var model = held.model;
    var table = objectField(model, JOURNAL_TABLE);
    var declared = objectField(model, DETAIL_VIEW);
    return {
      declared: {
        fields: DECLARED_FIELDS.length,
        rows: table[ROW_COUNT],
        columns: table[COLUMN_COUNT],
        entries: model[ENTRY_COUNT]
      },
      held: {
        fields: heldFieldCount(),
        rows: listField(table, ROWS).length,
        columns: listField(table, COLUMNS).length,
        lines: listField(declared, ROWS).length
      },
      faults: journalFaults.slice()
    };
  }

  function setJournal(model) {
    if (!isPlainObject(model)) {
      held = null;
      journalFaults = [fault(null, null, NOT_AN_OBJECT_FAULT, kindOf(model))];
      return { declared: null, held: null, faults: journalFaults.slice() };
    }
    held = { model: model };
    journalFaults = [];
    checkFields(model);
    checkSlots(model, HEADER_ORDER);
    checkSlots(model, RECOVERY_ORDER);
    checkSlots(model, BUTTON_ROW_ORDER);
    checkTable(model);
    checkLines(model);
    checkSheets(model);
    return report();
  }

  // loadJournal asks METHOD once, clearing asked so a refusal retries.
  function loadJournal(params) {
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
        setJournal(model);
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

  function declaredNames() {
    return DECLARED_FIELDS.slice();
  }

  function nullableNames() {
    return NULLABLE_FIELDS.slice();
  }

  function slotNames() {
    return SLOT_FIELDS.slice();
  }

  function lineFields() {
    return LINE_FIELDS.slice();
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

  function table() {
    return bag(JOURNAL_TABLE);
  }

  function rows() {
    return listField(table(), ROWS).slice();
  }

  function row(at) {
    return rows()[at];
  }

  function rowColors(at) {
    return listField(table(), ROW_COLORS)[at];
  }

  function cellAt(at, column) {
    var found = row(at);
    return Array.isArray(found) ? found[column] : undefined;
  }

  function columns() {
    return listField(table(), COLUMNS).slice();
  }

  function pane() {
    return bag(DETAIL_VIEW);
  }

  function lines() {
    return listField(pane(), ROWS).slice();
  }

  function line(at) {
    return lines()[at];
  }

  // Each detail line's label beside its value, which is its identity.
  function lineTexts() {
    return lines().map(function (one) {
      return {
        label: isPlainObject(one) ? one[LABEL_FIELD] : undefined,
        value: isPlainObject(one) ? one[VALUE] : undefined
      };
    });
  }

  // Each table row's first cell beside every cell, which names the row.
  function rowTexts() {
    return rows().map(function (one) {
      var cells = Array.isArray(one) ? one : [];
      return { time: cells[ZERO], texts: cells.slice() };
    });
  }

  function filter(name) {
    return bag(name);
  }

  function filterItems(name) {
    return listField(filter(name), ITEMS).slice();
  }

  function calls() {
    return list(CALLS);
  }

  function action(name) {
    var found = bag(ACTIONS);
    return owns(found, name) ? found[name] : undefined;
  }

  function colourNamed(name) {
    var found = bag(COLORS);
    return owns(found, name) ? found[name] : undefined;
  }

  function defaultText(name) {
    var found = bag(DEFAULT_TEXTS);
    return owns(found, name) ? found[name] : undefined;
  }

  function skin(name) {
    var found = bag(SKIN);
    return owns(found, name) ? found[name] : undefined;
  }

  function alignmentWords() {
    return Object.keys(ALIGNMENT_STYLE);
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
    return journalFaults.slice();
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

  function renderTab(target, model, onPick) {
    var drawn = model;
    if (!isPlainObject(drawn)) {
      drawn = held === null ? null : held.model;
    }
    return draw(target, element(Tab, { model: drawn, onPick: onPick }));
  }

  function forget() {
    held = null;
    journalFaults = [];
    loadFault = null;
    asked = null;
  }

  global.acervatorSetJournal = setJournal;
  global.acervatorLoadJournal = loadJournal;
  global.acervatorJournal = {
    method: METHOD,
    Tab: Tab,
    Splitter: Splitter,
    Handle: Handle,
    GroupBox: GroupBox,
    HeaderRow: HeaderRow,
    Filter: Filter,
    TextLabel: TextLabel,
    JournalTable: JournalTable,
    EntryRow: EntryRow,
    BodyCell: BodyCell,
    HeaderCell: HeaderCell,
    DetailPane: DetailPane,
    DetailLine: DetailLine,
    RecoveryPane: RecoveryPane,
    ButtonRow: ButtonRow,
    ActionButton: ActionButton,
    Stretch: Stretch,
    payload: payload,
    declaredNames: declaredNames,
    slotNames: slotNames,
    nullableNames: nullableNames,
    lineFields: lineFields,
    field: field,
    table: table,
    rows: rows,
    row: row,
    rowColors: rowColors,
    cellAt: cellAt,
    columns: columns,
    pane: pane,
    lines: lines,
    line: line,
    lineTexts: lineTexts,
    rowTexts: rowTexts,
    filter: filter,
    filterItems: filterItems,
    calls: calls,
    action: action,
    colourNamed: colourNamed,
    defaultText: defaultText,
    skin: skin,
    alignmentWords: alignmentWords,
    styleOf: styleOf,
    stateStyle: stateStyle,
    keptSheet: keptSheet,
    qtColour: qtColour,
    declarations: declarations,
    variableFor: variableFor,
    colour: colour,
    length: length,
    points: points,
    kinds: kinds,
    faults: faults,
    loadError: loadError,
    isLoaded: isLoaded,
    renderTab: renderTab,
    forget: forget
  };
})(window);
