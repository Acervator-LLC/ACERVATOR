// Draws the Simulator Extractor bot table from the
// sim_extractor_bot_table.state payload, holding no colour, width or text of
// its own. Forked from extractor_bot_table.js.
(function (global) {
  "use strict";

  var METHOD = "sim_extractor_bot_table.state";

  var ACCESSIBLE_NAME = "accessible_name";
  var ACTIONS = "actions";
  var ALIGNMENT = "alignment";
  var ALIGNMENT_VALUE = "alignment_value";
  var BOT_IDS = "bot_ids";
  var BUILT_ROW_COUNT = "built_row_count";
  var BUTTON_COLUMNS = "button_columns";
  var BUTTON_HEIGHT = "button_height";
  var BUTTON_KIND = "button_kind";
  var BUTTONS = "buttons";
  var CALLS = "calls";
  var COLUMN_COUNT = "column_count";
  var COLUMN_FIXED_WIDTHS = "column_fixed_widths";
  var COLUMN_LABELS = "column_labels";
  var COLUMN_TOOLTIPS = "column_tooltips";
  var CURRENT_ROW = "current_row";
  var DETAIL_LABEL = "detail_label";
  var DETAIL_STYLE_SHEET = "detail_style_sheet";
  var EMPTY_TIP = "empty_tip";
  var FIRE_LABEL = "fire_label";
  var FIRE_FOCUS_POLICY = "fire_focus_policy";
  var FIRE_STYLE_SHEET = "fire_style_sheet";
  var ICON_COLUMN = "icon_column";
  var ITEMS_PER_SELECTED_ROW = "items_per_selected_row";
  var MISSING_TEXT = "missing_text";
  var NO_ROW = "no_row";
  var POOL_COLORS = "pool_colors";
  var ROW_COUNT = "row_count";
  var ROWS = "rows";
  var SELECTED_BOT_ID = "selected_bot_id";
  var SELECTED_ITEM_COUNT = "selected_item_count";
  var SELECTED_ROW = "selected_row";
  var SET_BRUSH = "set_brush";
  var STATE_COLORS = "state_colors";
  var TABLE_KIND = "table_kind";
  var TABLE_STYLE_SHEET = "table_style_sheet";
  var UNSET_ITEM_TYPE = "unset_item_type";
  var EXCHANGE_ID = "exchange_id";
  var EXCHANGE_ID_PARAM_FIELD = "exchange_id_param";
  var ACTION_PARAM_FIELD = "action_param";
  var BOT_ID_PARAM_FIELD = "bot_id_param";
  var DETAIL_ACTION_FIELD = "detail_action";
  // MODEL_KEY names the payload each drawn host keeps beside its React root.
  var MODEL_KEY = "model";

  // DECLARED_FIELDS lists every top-level name the payload carries.
  var DECLARED_FIELDS = [
    ACCESSIBLE_NAME,
    ACTIONS,
    "action_param",
    ALIGNMENT,
    ALIGNMENT_VALUE,
    "base_kind",
    BOT_IDS,
    "bot_id_param",
    "bot_statuses_param",
    "bridge_actions",
    BUILT_ROW_COUNT,
    "bus_topics",
    BUTTON_COLUMNS,
    BUTTON_HEIGHT,
    BUTTON_KIND,
    BUTTONS,
    CALLS,
    "coloured_columns",
    COLUMN_COUNT,
    COLUMN_FIXED_WIDTHS,
    COLUMN_LABELS,
    COLUMN_TOOLTIPS,
    CURRENT_ROW,
    "default_pool_color_name",
    DETAIL_ACTION_FIELD,
    "detail_calls",
    "detail_enabled",
    "detail_focus_policy",
    DETAIL_LABEL,
    "detail_path",
    "detail_paths",
    DETAIL_STYLE_SHEET,
    "detail_tooltip",
    EMPTY_TIP,
    EXCHANGE_ID,
    EXCHANGE_ID_PARAM_FIELD,
    "fire_enabled",
    FIRE_FOCUS_POLICY,
    FIRE_LABEL,
    FIRE_STYLE_SHEET,
    "fire_tooltip",
    "first_column",
    "has_parent",
    ICON_COLUMN,
    ITEMS_PER_SELECTED_ROW,
    "liquid_tip_format",
    "logger_name",
    "method",
    "missing_amount",
    "missing_count",
    MISSING_TEXT,
    "mode_text",
    "mode_tip_format",
    "no_bot",
    "no_deployment",
    NO_ROW,
    "no_value_text",
    POOL_COLORS,
    "pool_fallback_color",
    "pool_text_format",
    "reset_param",
    ROW_COUNT,
    ROWS,
    "select_action",
    "select_path",
    "select_paths",
    SELECTED_BOT_ID,
    SELECTED_ITEM_COUNT,
    SELECTED_ROW,
    SET_BRUSH,
    "skin",
    STATE_COLORS,
    "state_fallback_color",
    "status_keys",
    "stretch_columns",
    TABLE_KIND,
    TABLE_STYLE_SHEET,
    "text_columns",
    "timer_delays_ms",
    "timers",
    "trades_key",
    "unknown_state_text",
    "update_action",
    "unset_brush",
    "unset_color",
    UNSET_ITEM_TYPE
  ];

  // Bags whose published key order JavaScript re-sorts, so a list names it.
  var COLUMN_KEYED_BAGS = [BUTTONS, COLUMN_FIXED_WIDTHS, COLUMN_TOOLTIPS];

  var DECLARED_BAGS = [
    ACTIONS,
    BUTTONS,
    COLUMN_FIXED_WIDTHS,
    COLUMN_TOOLTIPS,
    POOL_COLORS,
    "skin",
    STATE_COLORS,
    "timers"
  ];

  var DECLARED_LISTS = [
    BOT_IDS,
    "bridge_actions",
    BUTTON_COLUMNS,
    CALLS,
    "coloured_columns",
    COLUMN_LABELS,
    "detail_calls",
    "detail_paths",
    ROWS,
    "select_paths",
    "status_keys",
    "stretch_columns",
    "text_columns",
    "timer_delays_ms",
    "bus_topics"
  ];

  var BOT_ID = "bot_id";
  var VALUES = "values";
  var TEXTS = "texts";
  var TYPES = "types";
  var ALIGNMENTS = "alignments";
  var COLORS = "colors";
  var BRUSHES = "brushes";
  var TOOLTIPS = "tooltips";
  var ICONS = "icons";
  var ICON_COLORS = "icon_colors";
  var ICON_LETTERS = "icon_letters";
  var ICON_SIZE = "icon_size";
  var STATE = "state";
  var POOL_COLOR_NAME = "pool_color_name";

  var ROW_FIELDS = [
    BOT_ID,
    VALUES,
    TEXTS,
    TYPES,
    ALIGNMENTS,
    COLORS,
    BRUSHES,
    TOOLTIPS,
    ICONS,
    ICON_COLORS,
    ICON_LETTERS,
    BUTTONS,
    STATE,
    POOL_COLOR_NAME,
    "chunk_size_usd",
    "chunk_free_base",
    "chunk_size_base",
    "deployed_base",
    "free_usd",
    "deployed_usd",
    "n_positions",
    "n_drawdown"
  ];

  // Each of these row lists carries one entry per column.
  var PER_COLUMN_LISTS = [
    VALUES,
    TEXTS,
    TYPES,
    ALIGNMENTS,
    COLORS,
    BRUSHES,
    TOOLTIPS,
    ICONS,
    ICON_COLORS,
    ICON_LETTERS
  ];

  var KIND = "kind";
  var TEXT = "text";
  var ENABLED = "enabled";
  var HEIGHT = "height";
  var STYLE_SHEET = "style_sheet";
  var TOOLTIP = "tooltip";
  var FOCUS_POLICY = "focus_policy";
  var ACTION = "action";

  var BUTTON_FIELDS = [
    KIND,
    TEXT,
    ENABLED,
    HEIGHT,
    STYLE_SHEET,
    TOOLTIP,
    FOCUS_POLICY,
    ACTION
  ];

  var DETAIL_CLICKED = "detail.clicked";

  var MISSING_FAULT = "missing";
  var NULL_FAULT = "null";
  var NOT_AN_OBJECT_FAULT = "not-an-object";
  var NOT_A_LIST_FAULT = "not-a-list";
  var WRONG_TYPE_FAULT = "wrong-type";
  var SHORT_LIST_FAULT = "short-list";
  var DISAGREES_FAULT = "disagrees";
  var SWAPPED_ALPHA_FAULT = "swapped-alpha";
  var NOT_CSS_FAULT = "not-css";
  var MISMATCH_FAULT = "mismatch";

  var ROW_AT = "row:";
  var CELL_AT = "-cell:";
  var BUTTON_AT = "-button:";
  var PATH_SPLIT = ".";
  var EMPTY = "";

  var NO_BRIDGE = "the preload bridge is not present";

  // Qt paints this gradient by name and no browser stylesheet runs it.
  var QT_ONLY = "qlineargradient";

  var TABLE_CLASS = "acervator-extractor-table";

  var TABLE_TAG = "table";
  var HEAD_TAG = "thead";
  var BODY_TAG = "tbody";
  var ROW_TAG = "tr";
  var HEAD_CELL_TAG = "th";
  var CELL_TAG = "td";
  var BUTTON_TAG = "button";
  var BUTTON_TYPE = "button";
  var DISC_TAG = "span";

  var TABLE_PART = "table";
  var HEAD_PART = "head";
  var HEAD_ROW_PART = "head-row";
  var HEADER_PART = "header";
  var BODY_PART = "body";
  var ROW_PART = "row";
  var CELL_PART = "cell";
  var FIRE_PART = "fire-button";
  var DETAIL_PART = "detail-button";
  var DISC_PART = "coin-icon";

  // The exchange screen leaves this named space for the table to fill.
  var EMPTY_SPACE_PART = "extractor-table";

  var PART_ATTR = "data-part";
  var KIND_ATTR = "data-kind";
  var ROWS_ATTR = "data-rows";
  var DRAWN_ATTR = "data-drawn";
  var HELD_ATTR = "data-held";
  var SELECTED_ATTR = "data-selected";
  var INDEX_ATTR = "data-index";
  var COLUMNS_ATTR = "data-columns";
  var HELD_COLUMNS_ATTR = "data-held-columns";
  var ROW_ATTR = "data-row";
  var BOT_ID_ATTR = "data-bot-id";
  var BUILT_ATTR = "data-built";
  var CURRENT_ATTR = "data-current";
  var COLUMN_ATTR = "data-column";
  var BRUSH_ATTR = "data-brush";
  var ITEM_TYPE_ATTR = "data-item-type";
  var ICON_ATTR = "data-icon";
  var ICON_SIZE_ATTR = "data-icon-size";
  var ALIGNMENT_ATTR = "data-alignment";
  var ALIGNMENT_VALUE_ATTR = "data-alignment-value";
  var FOCUS_ATTR = "data-focus-policy";
  var ACTION_ATTR = "data-action";
  var ARIA_LABEL = "aria-label";

  var SELECT_OPEN = "[";
  var SELECT_IS = "=\"";
  var SELECT_CLOSE = "\"]";

  var HEX_MARK = "#";
  // SWAPPED_LENGTH is the width a colour written with eight hex digits takes.
  var SWAPPED_LENGTH = HEX_MARK.length + "aabbccdd".length;

  var PX = "px";
  // QFont point size in _get_coin_icon: int(size * 0.45).
  var DISC_LETTER_SHARE = 0.45;
  var FIXED = "fixed";
  var FULL = "100%";
  var COLLAPSE = "collapse";
  var NOWRAP = "nowrap";
  var HIDDEN = "hidden";
  var ELLIPSIS = "ellipsis";

  // ALIGNMENT_STYLE turns each alignment word the surface writes into CSS.
  var ALIGNMENT_STYLE = { AlignCenter: { textAlign: "center" } };

  var ZERO = Number(EMPTY);
  var STEP = Number(true);
  // NOT_FOCUSABLE is the tab index the NoFocus policy leaves a button with.
  var NOT_FOCUSABLE = ZERO - STEP;

  var held = null;
  var tableFaults = [];
  var loadFault = null;
  var asked = null;
  var roots = [];
  var dispatched = [];
  // One payload per exchange, so a re-mount redraws that screen's own rows
  // rather than whichever exchange answered last.
  var models = {};

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

  // Returns value when it is a non-empty string, else undefined.
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

  // True for a colour written with eight hex digits, which Qt and CSS read apart.
  function isSwappedAlpha(value) {
    return (
      typeof value === "string" &&
      value.length === SWAPPED_LENGTH &&
      value.charAt(ZERO) === HEX_MARK
    );
  }

  // acervatorSimCells owns the rule that one carrier name resolves a colour.
  function variableFor(value) {
    var api = global.acervatorSimCells;
    if (!api || typeof api.variableFor !== "function") {
      return undefined;
    }
    return api.variableFor(value);
  }

  function colour(value) {
    var api = global.acervatorSimCells;
    if (!api || typeof api.colour !== "function") {
      return text(value);
    }
    return api.colour(value);
  }

  function length(value) {
    return value === null || value === undefined ? undefined : String(value) + PX;
  }

  // `header_strip.js` owns the rule that turns a Qt style sheet into CSS.
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

  // The column order comes from a list, never from the keys of a bag.
  function columnOrder(model) {
    return listField(model, COLUMN_LABELS).map(function (name, column) {
      return column;
    });
  }

  function buttonColumns(model) {
    return listField(model, BUTTON_COLUMNS).slice();
  }

  function fixedWidthOf(model, column) {
    var widths = objectField(model, COLUMN_FIXED_WIDTHS);
    var name = String(column);
    return owns(widths, name) ? widths[name] : undefined;
  }

  function buttonOf(row, column) {
    var bag = objectField(row, BUTTONS);
    var name = String(column);
    return owns(bag, name) ? bag[name] : undefined;
  }

  function isFirstButton(model, column) {
    return buttonColumns(model)[ZERO] === column;
  }

  function rowIsBuilt(row) {
    return isPlainObject(row);
  }

  function element() {
    return global.React.createElement.apply(null, arguments);
  }

  function HeaderCell(props) {
    var model = props.model;
    var column = props.column;
    var style = { whiteSpace: NOWRAP, overflow: HIDDEN, textOverflow: ELLIPSIS };
    var width = fixedWidthOf(model, column);
    if (width !== undefined) {
      style.width = length(width);
    }
    var headProps = {
      className: TABLE_CLASS,
      style: style,
      title: label(objectField(model, COLUMN_TOOLTIPS)[String(column)])
    };
    headProps[PART_ATTR] = HEADER_PART;
    headProps[COLUMN_ATTR] = text(column);
    headProps[ARIA_LABEL] = label(listField(model, COLUMN_LABELS)[column]);
    return element(
      HEAD_CELL_TAG,
      headProps,
      text(listField(model, COLUMN_LABELS)[column])
    );
  }

  function ActionButton(props) {
    var model = props.model;
    var button = props.button;
    if (!isPlainObject(button)) {
      return null;
    }
    var style = styleOf(button[STYLE_SHEET]);
    style.height = length(button[HEIGHT]);
    var buttonProps = {
      className: TABLE_CLASS,
      style: style,
      title: label(button[TOOLTIP]),
      type: BUTTON_TYPE,
      disabled: button[ENABLED] !== true,
      onClick: function () {
        sendDetail(model, props.botId);
      }
    };
    if (button[FOCUS_POLICY] === model[FIRE_FOCUS_POLICY]) {
      buttonProps.tabIndex = NOT_FOCUSABLE;
    }
    buttonProps[PART_ATTR] = props.part;
    buttonProps[BOT_ID_ATTR] = text(props.botId);
    buttonProps[COLUMN_ATTR] = text(props.column);
    buttonProps[FOCUS_ATTR] = text(button[FOCUS_POLICY]);
    buttonProps[KIND_ATTR] = text(button[KIND]);
    buttonProps[ARIA_LABEL] = label(button[TEXT]);
    buttonProps[ACTION_ATTR] = label(button[ACTION]);
    return element(BUTTON_TAG, buttonProps, text(button[TEXT]));
  }

  // The button a column holds, or undefined where the column holds text.
  function buttonAt(model, row, column, botId) {
    if (!contains(buttonColumns(model), column)) {
      return undefined;
    }
    return element(ActionButton, {
      model: model,
      button: buttonOf(row, column),
      botId: botId,
      column: column,
      part: isFirstButton(model, column) ? FIRE_PART : DETAIL_PART
    });
  }

  // The disc _get_coin_icon paints: colour fills it, letter names it and size
  // sizes it.
  function CoinDisc(props) {
    var size = Number(props.size);
    var style = { background: colour(props.colour) };
    if (size > 0) {
      style.width = size + PX;
      style.height = size + PX;
      style.lineHeight = size + PX;
      style.fontSize = Math.round(size * DISC_LETTER_SHARE) + PX;
    }
    var discProps = { className: TABLE_CLASS, style: style };
    discProps[PART_ATTR] = DISC_PART;
    discProps[ICON_SIZE_ATTR] = text(props.size);
    return element(DISC_TAG, discProps, text(props.letter));
  }

  function BodyCell(props) {
    var model = props.model;
    var row = props.row;
    var column = props.column;
    var style = { whiteSpace: NOWRAP, overflow: HIDDEN, textOverflow: ELLIPSIS };
    var brush = listField(row, BRUSHES)[column];
    var painted = brush === model[SET_BRUSH];
    if (painted) {
      style.color = colour(listField(row, COLORS)[column]);
    }
    withAlignment(style, model[ALIGNMENT]);
    var cellProps = {
      className: TABLE_CLASS,
      style: style,
      title: label(listField(row, TOOLTIPS)[column])
    };
    cellProps[PART_ATTR] = CELL_PART;
    cellProps[COLUMN_ATTR] = text(column);
    cellProps[BRUSH_ATTR] = text(brush);
    cellProps[ITEM_TYPE_ATTR] = text(listField(row, TYPES)[column]);
    cellProps[ICON_ATTR] = text(listField(row, ICONS)[column]);
    cellProps[ALIGNMENT_ATTR] = text(model[ALIGNMENT]);
    cellProps[ALIGNMENT_VALUE_ATTR] = text(listField(row, ALIGNMENTS)[column]);
    var button = buttonAt(model, row, column, row[BOT_ID]);
    if (button !== undefined) {
      return element(CELL_TAG, cellProps, button);
    }
    var disc = listField(row, ICON_COLORS)[column];
    if (isFilledText(disc)) {
      return element(
        CELL_TAG,
        cellProps,
        element(CoinDisc, {
          key: DISC_PART,
          colour: disc,
          letter: listField(row, ICON_LETTERS)[column],
          size: model[ICON_SIZE]
        }),
        text(listField(row, TEXTS)[column])
      );
    }
    return element(CELL_TAG, cellProps, text(listField(row, TEXTS)[column]));
  }

  function BotRow(props) {
    var model = props.model;
    var row = isPlainObject(props.row) ? props.row : {};
    var at = props.at;
    var drawn = columnOrder(model).map(function (column) {
      return element(BodyCell, {
        key: String(column),
        model: model,
        row: row,
        column: column
      });
    });
    var rowProps = { className: TABLE_CLASS };
    rowProps[PART_ATTR] = ROW_PART;
    rowProps[ROW_ATTR] = text(at);
    rowProps[BOT_ID_ATTR] = text(row[BOT_ID]);
    rowProps[BUILT_ATTR] = String(rowIsBuilt(props.row));
    rowProps[SELECTED_ATTR] = String(at === model[SELECTED_ROW]);
    rowProps[CURRENT_ATTR] = String(at === model[CURRENT_ROW]);
    rowProps[HELD_COLUMNS_ATTR] = String(drawn.length);
    return element(ROW_TAG, rowProps, drawn);
  }

  // `Table` draws nothing for a payload that is not an object.
  function Table(props) {
    if (!isPlainObject(props.model)) {
      return null;
    }
    var model = props.model;
    var rows = listField(model, ROWS);
    var columns = columnOrder(model);
    var style = styleOf(model[TABLE_STYLE_SHEET]);
    style.tableLayout = FIXED;
    style.width = FULL;
    style.borderCollapse = COLLAPSE;
    var tableProps = { id: props.id, className: TABLE_CLASS, style: style };
    tableProps[PART_ATTR] = TABLE_PART;
    tableProps[KIND_ATTR] = text(model[TABLE_KIND]);
    tableProps[ROWS_ATTR] = text(model[ROW_COUNT]);
    tableProps[DRAWN_ATTR] = text(model[BUILT_ROW_COUNT]);
    tableProps[HELD_ATTR] = String(listField(model, BOT_IDS).length);
    tableProps[SELECTED_ATTR] = text(model[SELECTED_BOT_ID]);
    tableProps[INDEX_ATTR] = text(model[CURRENT_ROW]);
    tableProps[COLUMNS_ATTR] = text(model[COLUMN_COUNT]);
    tableProps[HELD_COLUMNS_ATTR] = String(columns.length);
    tableProps[ARIA_LABEL] = label(model[ACCESSIBLE_NAME]);
    var headProps = { className: TABLE_CLASS };
    headProps[PART_ATTR] = HEAD_ROW_PART;
    var headWrap = { className: TABLE_CLASS };
    headWrap[PART_ATTR] = HEAD_PART;
    var bodyWrap = { className: TABLE_CLASS };
    bodyWrap[PART_ATTR] = BODY_PART;
    return element(
      TABLE_TAG,
      tableProps,
      element(
        HEAD_TAG,
        headWrap,
        element(
          ROW_TAG,
          headProps,
          columns.map(function (column) {
            return element(HeaderCell, {
              key: String(column),
              model: model,
              column: column
            });
          })
        )
      ),
      element(
        BODY_TAG,
        bodyWrap,
        rows.map(function (row, at) {
          return element(BotRow, { key: String(at), model: model, row: row, at: at });
        })
      )
    );
  }

  function checkFields(model) {
    DECLARED_FIELDS.forEach(function (field) {
      if (!owns(model, field)) {
        tableFaults.push(fault(null, field, MISSING_FAULT, null));
        return;
      }
      if (model[field] === null) {
        tableFaults.push(fault(null, field, NULL_FAULT, null));
      }
    });
  }

  function checkShapes(model) {
    DECLARED_BAGS.forEach(function (field) {
      if (owns(model, field) && !isPlainObject(model[field])) {
        tableFaults.push(fault(null, field, NOT_AN_OBJECT_FAULT, kindOf(model[field])));
      }
    });
    DECLARED_LISTS.forEach(function (field) {
      if (owns(model, field) && !Array.isArray(model[field])) {
        tableFaults.push(fault(null, field, NOT_A_LIST_FAULT, kindOf(model[field])));
      }
    });
  }

  // Each count the payload publishes is held against the list it counts.
  function checkCounts(model) {
    var rows = listField(model, ROWS);
    var ids = listField(model, BOT_IDS);
    if (owns(model, ROW_COUNT) && rows.length !== model[ROW_COUNT]) {
      tableFaults.push(fault(null, ROWS, DISAGREES_FAULT, rows.length));
    }
    if (owns(model, ROW_COUNT) && ids.length !== model[ROW_COUNT]) {
      tableFaults.push(fault(null, BOT_IDS, DISAGREES_FAULT, ids.length));
    }
    var built = rows.filter(rowIsBuilt).length;
    if (owns(model, BUILT_ROW_COUNT) && built !== model[BUILT_ROW_COUNT]) {
      tableFaults.push(fault(null, BUILT_ROW_COUNT, DISAGREES_FAULT, built));
    }
    var columns = listField(model, COLUMN_LABELS);
    if (owns(model, COLUMN_COUNT) && columns.length !== model[COLUMN_COUNT]) {
      tableFaults.push(fault(null, COLUMN_LABELS, DISAGREES_FAULT, columns.length));
    }
  }

  // A selection past the last row names itself rather than drawing nowhere.
  function checkSelection(model) {
    var rows = listField(model, ROWS);
    [SELECTED_ROW, CURRENT_ROW].forEach(function (field) {
      var at = model[field];
      if (typeof at !== "number" || at === model[NO_ROW]) {
        return;
      }
      if (at < ZERO || at >= rows.length) {
        tableFaults.push(fault(null, field, DISAGREES_FAULT, rows.length));
      }
    });
    var count = model[SELECTED_ITEM_COUNT];
    var wanted = rowIsBuilt(rows[model[SELECTED_ROW]])
      ? model[ITEMS_PER_SELECTED_ROW]
      : ZERO;
    if (owns(model, SELECTED_ITEM_COUNT) && count !== wanted) {
      tableFaults.push(fault(null, SELECTED_ITEM_COUNT, DISAGREES_FAULT, wanted));
    }
  }

  // A bag keyed by a column loses its written order, so a list must name it.
  function checkBagOrder(model) {
    COLUMN_KEYED_BAGS.forEach(function (field) {
      var keys = Object.keys(objectField(model, field));
      var sorted = keys.slice().sort(function (one, other) {
        return Number(one) - Number(other);
      });
      if (keys.join(EMPTY) !== sorted.join(EMPTY)) {
        tableFaults.push(fault(null, field, DISAGREES_FAULT, keys.slice()));
      }
    });
  }

  function checkColour(where, field, value) {
    if (isSwappedAlpha(value)) {
      tableFaults.push(fault(where, field, SWAPPED_ALPHA_FAULT, value));
    }
  }

  function checkColours(model) {
    [STATE_COLORS, POOL_COLORS].forEach(function (field) {
      var bag = objectField(model, field);
      Object.keys(bag).forEach(function (name) {
        checkColour(field, name, bag[name]);
      });
    });
    ["state_fallback_color", "pool_fallback_color", "unset_color"].forEach(
      function (field) {
        checkColour(null, field, model[field]);
      }
    );
  }

  function checkSheet(where, field, sheet) {
    declarations(sheet).forEach(function (one) {
      if (carries(one.value, QT_ONLY)) {
        tableFaults.push(fault(where, field, NOT_CSS_FAULT, one.property));
      }
    });
  }

  function checkSheets(model) {
    [FIRE_STYLE_SHEET, DETAIL_STYLE_SHEET, TABLE_STYLE_SHEET].forEach(function (
      field
    ) {
      checkSheet(null, field, model[field]);
    });
  }

  function checkButton(model, where, column, button) {
    var at = where + BUTTON_AT + String(column);
    if (!isPlainObject(button)) {
      tableFaults.push(fault(at, null, NOT_AN_OBJECT_FAULT, kindOf(button)));
      return;
    }
    BUTTON_FIELDS.forEach(function (name) {
      if (!owns(button, name)) {
        tableFaults.push(fault(at, name, MISSING_FAULT, null));
      }
    });
    if (owns(button, KIND) && button[KIND] !== model[BUTTON_KIND]) {
      tableFaults.push(fault(at, KIND, MISMATCH_FAULT, button[KIND]));
    }
    var declared = objectField(model, BUTTONS)[String(column)];
    if (!isPlainObject(declared)) {
      return;
    }
    BUTTON_FIELDS.forEach(function (name) {
      if (owns(button, name) && button[name] !== declared[name]) {
        tableFaults.push(
          fault(at, name, MISMATCH_FAULT, {
            declared: declared[name],
            held: button[name]
          })
        );
      }
    });
  }

  function checkRowLists(model, where, row) {
    PER_COLUMN_LISTS.forEach(function (name) {
      if (!Array.isArray(row[name])) {
        tableFaults.push(fault(where, name, NOT_A_LIST_FAULT, kindOf(row[name])));
        return;
      }
      if (row[name].length !== model[COLUMN_COUNT]) {
        tableFaults.push(fault(where, name, SHORT_LIST_FAULT, row[name].length));
      }
    });
  }

  function checkRowCells(model, where, row) {
    listField(row, TEXTS).forEach(function (value, column) {
      if (kindOf(value) !== kindOf(model[MISSING_TEXT])) {
        tableFaults.push(
          fault(where + CELL_AT + String(column), TEXTS, WRONG_TYPE_FAULT, kindOf(value))
        );
      }
    });
    listField(row, TYPES).forEach(function (value, column) {
      if (kindOf(value) !== kindOf(model[UNSET_ITEM_TYPE])) {
        tableFaults.push(
          fault(where + CELL_AT + String(column), TYPES, WRONG_TYPE_FAULT, kindOf(value))
        );
      }
    });
    listField(row, COLORS).forEach(function (value, column) {
      checkColour(where + CELL_AT + String(column), COLORS, value);
    });
    listField(row, ALIGNMENTS).forEach(function (value, column) {
      if (value !== model[ALIGNMENT_VALUE]) {
        tableFaults.push(
          fault(where + CELL_AT + String(column), ALIGNMENTS, MISMATCH_FAULT, value)
        );
      }
    });
  }

  function checkRows(model) {
    listField(model, ROWS).forEach(function (row, at) {
      if (row === null) {
        return;
      }
      var where = ROW_AT + String(at);
      if (!isPlainObject(row)) {
        tableFaults.push(fault(where, null, NOT_AN_OBJECT_FAULT, kindOf(row)));
        return;
      }
      ROW_FIELDS.forEach(function (name) {
        if (!owns(row, name)) {
          tableFaults.push(fault(where, name, MISSING_FAULT, null));
        }
      });
      checkRowLists(model, where, row);
      checkRowCells(model, where, row);
      buttonColumns(model).forEach(function (column) {
        checkButton(model, where, column, buttonOf(row, column));
      });
      if (row[BOT_ID] !== listField(model, BOT_IDS)[at]) {
        tableFaults.push(fault(where, BOT_ID, MISMATCH_FAULT, row[BOT_ID]));
      }
    });
  }

  function heldFieldCount() {
    return DECLARED_FIELDS.filter(function (field) {
      return held !== null && owns(held.model, field);
    }).length;
  }

  // Counts fields, rows, columns and buttons declared against those held.
  function report() {
    var model = held.model;
    var rows = listField(model, ROWS);
    return {
      declared: {
        fields: DECLARED_FIELDS.length,
        rows: model[ROW_COUNT],
        columns: model[COLUMN_COUNT],
        drawn: model[BUILT_ROW_COUNT],
        buttons: buttonColumns(model).length
      },
      held: {
        fields: heldFieldCount(),
        rows: rows.length,
        columns: listField(model, COLUMN_LABELS).length,
        drawn: rows.filter(rowIsBuilt).length,
        buttons: Object.keys(objectField(model, BUTTONS)).length
      },
      faults: tableFaults.slice()
    };
  }

  function setTable(model) {
    if (!isPlainObject(model)) {
      held = null;
      tableFaults = [fault(null, null, NOT_AN_OBJECT_FAULT, kindOf(model))];
      return { declared: null, held: null, faults: tableFaults.slice() };
    }
    held = { model: model };
    if (isFilledText(model[EXCHANGE_ID])) {
      models[model[EXCHANGE_ID]] = model;
    }
    tableFaults = [];
    checkFields(model);
    checkShapes(model);
    checkCounts(model);
    checkSelection(model);
    checkBagOrder(model);
    checkColours(model);
    checkSheets(model);
    checkRows(model);
    return report();
  }

  // Asks METHOD once per distinct request, clearing asked so a refused first
  // ask is retried and so a second screen is not answered with the first
  // screen's rows.
  function loadTable(params) {
    var wanted = isPlainObject(params) ? params : {};
    var key = JSON.stringify(wanted);
    if (asked !== null && asked.key === key) {
      return asked.wait;
    }
    if (!global.acervator || typeof global.acervator.call !== "function") {
      loadFault = NO_BRIDGE;
      return Promise.resolve(null);
    }
    asked = {
      key: key,
      wait: global.acervator
        .call(METHOD, wanted)
        .then(function (model) {
          loadFault = null;
          setTable(model);
          return model;
        })
        .catch(function (err) {
          loadFault = err.message;
          asked = null;
          return null;
        })
    };
    return asked.wait;
  }

  // -- driving the table's own controls --------------------------------

  // One request, keyed by the names the surface publishes for those fields
  // and naming the exchange the clicked screen was drawn for.
  function request(model, action, botId) {
    var params = {};
    params[String(model[ACTION_PARAM_FIELD])] = action;
    params[String(model[BOT_ID_PARAM_FIELD])] = botId;
    params[String(model[EXCHANGE_ID_PARAM_FIELD])] = text(model[EXCHANGE_ID]);
    return params;
  }

  // The answer replaces only the screens drawn for that same exchange, so a
  // click on one exchange's table leaves another exchange's rows alone.
  function dispatch(model, action, botId) {
    var exchange = text(model[EXCHANGE_ID]);
    var params = request(model, action, botId);
    dispatched.push({ action: action, params: params, exchange: exchange });
    if (!global.acervator || typeof global.acervator.call !== "function") {
      return null;
    }
    return global.acervator.call(METHOD, params).then(function (answer) {
      setTable(answer);
      roots.forEach(function (pair) {
        if (text(objectField(pair, MODEL_KEY)[EXCHANGE_ID]) === exchange) {
          pair.model = answer;
          draw(pair.node, element(Table, { model: answer }));
        }
      });
      return answer;
    });
  }

  function sendDetail(model, botId) {
    return dispatch(model, model[DETAIL_ACTION_FIELD], botId);
  }

  function sent() {
    return dispatched.slice();
  }

  // The payload this module holds for one exchange, or null for none.
  function modelFor(exchangeId) {
    return owns(models, String(exchangeId)) ? models[String(exchangeId)] : null;
  }

  // Every host this module has drawn into, re-drawn from its own model.
  function redraw() {
    roots.forEach(function (pair) {
      draw(pair.node, element(Table, { model: objectField(pair, MODEL_KEY) }));
    });
    return roots.length;
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

  function rows() {
    return list(ROWS);
  }

  function row(at) {
    return rows()[at];
  }

  function botIds() {
    return list(BOT_IDS);
  }

  // The bot name each row carries, which is what a row is identified by.
  function rowBotIds() {
    return rows().map(function (found) {
      return isPlainObject(found) ? found[BOT_ID] : undefined;
    });
  }

  // The bot name each row carries beside its cell texts, so no check reads by position.
  function rowTexts() {
    return rows().map(function (found) {
      return {
        bot_id: isPlainObject(found) ? found[BOT_ID] : undefined,
        texts: listField(found, TEXTS).slice()
      };
    });
  }

  function cellAt(at, column) {
    var found = row(at);
    if (!isPlainObject(found)) {
      return undefined;
    }
    return {
      text: listField(found, TEXTS)[column],
      type: listField(found, TYPES)[column],
      color: listField(found, COLORS)[column],
      brush: listField(found, BRUSHES)[column],
      tooltip: listField(found, TOOLTIPS)[column],
      icon: listField(found, ICONS)[column],
      alignment: listField(found, ALIGNMENTS)[column]
    };
  }

  function buttonFor(at, column) {
    var found = row(at);
    return isPlainObject(found) ? buttonOf(found, column) : undefined;
  }

  function selectedBotId() {
    return field(SELECTED_BOT_ID);
  }

  // The bot the highlight sits on, read through the row rather than the index.
  function selectedRowBotId() {
    var at = field(SELECTED_ROW);
    var found = rows()[at];
    return isPlainObject(found) ? found[BOT_ID] : undefined;
  }

  function calls() {
    return list(CALLS);
  }

  function action(name) {
    var found = bag(ACTIONS);
    return owns(found, name) ? found[name] : undefined;
  }

  function detailAction() {
    return action(DETAIL_CLICKED);
  }

  function stateColour(name) {
    var found = bag(STATE_COLORS);
    return owns(found, name) ? found[name] : undefined;
  }

  function poolColour(name) {
    var found = bag(POOL_COLORS);
    return owns(found, name) ? found[name] : undefined;
  }

  function columnTooltip(column) {
    var found = bag(COLUMN_TOOLTIPS);
    return owns(found, String(column)) ? found[String(column)] : undefined;
  }

  function fixedWidth(column) {
    return held === null ? undefined : fixedWidthOf(held.model, column);
  }

  function columns() {
    return held === null ? [] : columnOrder(held.model);
  }

  function buttonColumnList() {
    return held === null ? [] : buttonColumns(held.model);
  }

  // The keys of one bag in the order this engine reads them back.
  function bagKeys(name) {
    return Object.keys(bag(name));
  }

  function alignmentWords() {
    return Object.keys(ALIGNMENT_STYLE);
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

  // The JavaScript type of every value in the payload, by dotted path.
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
    return tableFaults.slice();
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

  function payloadOr(model) {
    if (isPlainObject(model)) {
      return model;
    }
    return held === null ? null : held.model;
  }

  function renderTable(target, model) {
    var drawn = payloadOr(model);
    var host = draw(target, element(Table, { model: drawn }));
    roots.forEach(function (pair) {
      if (pair.node === target) {
        pair.model = drawn;
      }
    });
    return host;
  }

  // The named empty space the exchange screen left, inside `root` or `root` itself.
  function spaceIn(root) {
    if (!root || typeof root.getAttribute !== "function") {
      return null;
    }
    if (root.getAttribute(PART_ATTR) === EMPTY_SPACE_PART) {
      return root;
    }
    if (typeof root.querySelector !== "function") {
      return null;
    }
    return root.querySelector(
      SELECT_OPEN + PART_ATTR + SELECT_IS + EMPTY_SPACE_PART + SELECT_CLOSE
    );
  }

  function fill(root, model) {
    var space = spaceIn(root);
    return space === null ? null : renderTable(space, model);
  }

  function forget() {
    held = null;
    tableFaults = [];
    loadFault = null;
    asked = null;
    dispatched = [];
    models = {};
  }

  global.acervatorSetSimExtractorTable = setTable;
  global.acervatorLoadSimExtractorTable = loadTable;
  global.acervatorSimExtractorTable = {
    method: METHOD,
    spacePart: EMPTY_SPACE_PART,
    Table: Table,
    BotRow: BotRow,
    BodyCell: BodyCell,
    HeaderCell: HeaderCell,
    ActionButton: ActionButton,
    payload: payload,
    declaredNames: declaredNames,
    field: field,
    bag: bag,
    list: list,
    rows: rows,
    row: row,
    botIds: botIds,
    rowBotIds: rowBotIds,
    rowTexts: rowTexts,
    cellAt: cellAt,
    buttonFor: buttonFor,
    selectedBotId: selectedBotId,
    selectedRowBotId: selectedRowBotId,
    calls: calls,
    action: action,
    detailAction: detailAction,
    stateColour: stateColour,
    poolColour: poolColour,
    columnTooltip: columnTooltip,
    fixedWidth: fixedWidth,
    columns: columns,
    buttonColumns: buttonColumnList,
    bagKeys: bagKeys,
    alignmentWords: alignmentWords,
    isSwappedAlpha: isSwappedAlpha,
    styleOf: styleOf,
    declarations: declarations,
    variableFor: variableFor,
    colour: colour,
    length: length,
    kinds: kinds,
    notPlainData: notPlainData,
    faults: faults,
    loadError: loadError,
    isLoaded: isLoaded,
    renderTable: renderTable,
    fill: fill,
    redraw: redraw,
    modelFor: modelFor,
    sendDetail: sendDetail,
    sent: sent,
    forget: forget
  };
})(window);
