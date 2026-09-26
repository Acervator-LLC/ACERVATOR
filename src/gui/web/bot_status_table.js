// Draws the bot status table from the bot_status_table.state payload,
// holding no colour, size or text of its own.
(function (global) {
  "use strict";

  var METHOD = "bot_status_table.state";

  // -- the payload's own field names -----------------------------------

  var ACCESSIBLE_NAME = "accessible_name";
  var ACTIONS = "actions";
  var ALIGNMENT = "alignment";
  var ALIGNMENT_VALUE = "alignment_value";
  var BOT_ID_COLUMN = "bot_id_column";
  var BOT_IDS = "bot_ids";
  var BUTTON_HEIGHT = "button_height";
  var CALLS = "calls";
  var CELL_CLICK_PARAM = "cell_click_param";
  var COLUMN_COUNT = "column_count";
  var COLUMN_TOOLTIPS = "column_tooltips";
  var COLUMNS = "columns";
  var CURRENT_ROW = "current_row";
  var DEFAULT_STATE_COLOR = "default_state_color";
  var DETAIL_COLUMN = "detail_column";
  var DETAIL_LABEL = "detail_label";
  var DETAIL_STYLE = "detail_style";
  var DETAIL_PARAM = "detail_param";
  var DETAIL_TOOLTIP = "detail_tooltip";
  var EMPTY_TEXT = "empty_text";
  var EXCHANGE_ID = "exchange_id";
  var EXCHANGE_ID_PARAM_FIELD = "exchange_id_param";
  var FIRE_COLUMN = "fire_column";
  var FIRE_PARAM = "fire_param";
  var HEADER_CLICK_PARAM = "header_click_param";
  var HEADER_RESIZE_MODE = "header_resize_mode";
  var PRIVACY_TOGGLE_PARAM = "privacy_toggle_param";
  var SORT_COLUMN_PARAM = "sort_column_param";
  var SELECT_BOT_PARAM = "select_bot_param";
  var VIEW_BAND_PARAM = "view_band_param";
  var HEADER_LABEL_STYLE = "header_label_style";
  var HEADER_LABEL_WRAP = "header_label_wrap";
  var HEADER_DOT_STYLE = "header_dot_style";
  var HEADER_DOT_ROW_PX = "header_dot_row_px";
  var HEADER_CELL_PAD_PX = "header_cell_pad_px";
  var HEADER_SORT_MARK_STYLE = "header_sort_mark_style";
  var HEADER_SORT_MARK_BOX_PX = "header_sort_mark_box_px";
  var RESET_PARAM_FIELD = "reset_param";
  var STATUSES_PARAM_FIELD = "statuses_param";
  var FIRE_GLOWS = "fire_glows";
  var FIRE_LABEL = "fire_label";
  var FIRE_PATHS = "fire_paths";
  var FIRE_STYLE_HEAD = "fire_style_head";
  var FIRE_STYLES = "fire_styles";
  var FIXED_WIDTHS = "fixed_widths";
  var FOCUS_POLICY = "focus_policy";
  var GLOW_BLUR_RADIUS = "glow_blur_radius";
  var GLOW_OFFSET = "glow_offset";
  var HAS_SELECTION = "has_selection";
  var HEADERS = "headers";
  var POSITION_VALUE_COLUMN = "position_value_column";
  var PRIVACY_FIELD_BY_COL = "privacy_field_by_col";
  var ROW_COUNT = "row_count";
  var ROWS = "rows";
  var SELECTED_BOT_ID = "selected_bot_id";
  var SKIPPED_ROWS = "skipped_rows";
  var STATE_COLORS = "state_colors";
  var STYLE_SHEET = "style_sheet";

  // DECLARED_FIELDS lists every top-level field of the payload.
  var DECLARED_FIELDS = [
    ACCESSIBLE_NAME,
    ACTIONS,
    "active_states",
    ALIGNMENT,
    ALIGNMENT_VALUE,
    "alternating_row_colors",
    "ammo_column",
    "blockers_separator",
    "blockers_tip_format",
    BOT_ID_COLUMN,
    BOT_IDS,
    "browser_new_window",
    "bus_topics",
    "button_columns",
    CELL_CLICK_PARAM,
    BUTTON_HEIGHT,
    CALLS,
    "ceiling_approach_format",
    "ceiling_approach_ratio",
    "ceiling_hard_stop_ratio",
    "ceiling_normal_format",
    "ceiling_reached_format",
    "chart_open_failed_log",
    "chart_url_skipped_log",
    COLUMN_COUNT,
    COLUMN_TOOLTIPS,
    COLUMNS,
    CURRENT_ROW,
    "default_detonation_timeframe",
    "default_fold_taper",
    "default_quote_to_usd",
    DEFAULT_STATE_COLOR,
    "detail_clicks",
    DETAIL_COLUMN,
    DETAIL_PARAM,
    DETAIL_LABEL,
    DETAIL_STYLE,
    DETAIL_TOOLTIP,
    "detonation_format",
    "edit_triggers",
    EMPTY_TEXT,
    EXCHANGE_ID,
    EXCHANGE_ID_PARAM_FIELD,
    "fire_clicks",
    FIRE_COLUMN,
    FIRE_PARAM,
    FIRE_GLOWS,
    "fire_inactive_tooltip_format",
    FIRE_LABEL,
    "fire_mask_field",
    FIRE_PATHS,
    FIRE_STYLE_HEAD,
    FIRE_STYLES,
    "fire_tooltips",
    "fixed_resize_mode",
    FIXED_WIDTHS,
    FOCUS_POLICY,
    GLOW_BLUR_RADIUS,
    GLOW_OFFSET,
    "glows",
    HAS_SELECTION,
    HEADER_CLICK_PARAM,
    HEADER_CELL_PAD_PX,
    "header_cell_gap_px",
    "header_dot_action_mask",
    "header_dot_action_reveal",
    "header_dot_font_px",
    HEADER_DOT_ROW_PX,
    HEADER_DOT_STYLE,
    "header_dot_tip_format",
    "header_label_font_px",
    "header_label_min_font_px",
    HEADER_LABEL_STYLE,
    HEADER_LABEL_WRAP,
    HEADER_RESIZE_MODE,
    HEADER_SORT_MARK_BOX_PX,
    HEADER_SORT_MARK_STYLE,
    "header_state_tip_format",
    HEADERS,
    "icon_download",
    "icon_size",
    "link_color",
    "link_tip_format",
    "link_underline",
    "logger_name",
    "masked_glyph",
    "method",
    "mode_scrumming",
    "mode_tip_format",
    "no_blockers_text",
    "no_glow",
    "no_holdings",
    "no_price",
    "no_selection_bot_id",
    "no_selection_row",
    "no_target_text",
    "no_target_value",
    "no_trades",
    "opened_urls",
    "percent_scale",
    "position_blank_text",
    "position_paths",
    POSITION_VALUE_COLUMN,
    PRIVACY_FIELD_BY_COL,
    PRIVACY_TOGGLE_PARAM,
    "quote_btc",
    "quote_eth",
    RESET_PARAM_FIELD,
    "revealed_glyph",
    ROW_COUNT,
    ROWS,
    SELECTED_BOT_ID,
    "selection_behavior",
    "skin",
    "skip_bot_id_length",
    "skip_bot_id_missing",
    "skip_log_format",
    "skip_logger_name",
    SKIPPED_ROWS,
    "sort_ascending",
    "sort_column",
    SORT_COLUMN_PARAM,
    SELECT_BOT_PARAM,
    VIEW_BAND_PARAM,
    "sort_descending",
    "sort_descending_word",
    "sort_kind_by_col",
    "sort_mark_ascending",
    "sort_mark_descending",
    "sort_mark_none",
    "sort_unsorted",
    "sortable_columns",
    "sorting_enabled",
    "no_sort_column",
    "row_refused_log",
    STATE_COLORS,
    "state_masked",
    "state_revealed",
    STATUSES_PARAM_FIELD,
    STYLE_SHEET,
    "symbol_column",
    "symbol_separator",
    "target_btc_column",
    "target_eth_column",
    "timer_delays_ms",
    "timers",
    "unknown_state_text",
    "vertical_header_visible"
  ];

  // -- the field names one row, cell, button and header carry ----------

  var BOT_ID = "bot_id";
  var SKIPPED = "skipped";
  var CELLS = "cells";
  var FIRE = "fire";
  var DETAIL = "detail";

  var TEXT = "text";
  var COLOR = "color";
  var TOOLTIP = "tooltip";
  var ICON_ASSET = "icon_asset";
  var ICON_SIZE = "icon_size";
  var ICON_COLOR = "icon_color";
  var ICON_LETTER = "icon_letter";
  var CHART_URL = "chart_url";
  var UNDERLINE = "underline";

  var ENABLED = "enabled";
  var HEIGHT = "height";
  var PATH = "path";
  var GLOW = "glow";

  var FIELD_ID = "field_id";
  var MASKED = "masked";
  var DOT_TEXT = "dot_text";
  var DOT_TOOLTIP = "dot_tooltip";
  var SORTABLE = "sortable";
  var SORT_DIRECTION = "sort_direction";
  var SORT_MARK = "sort_mark";

  var ROW_FIELDS = [BOT_ID, SKIPPED, CELLS, FIRE, DETAIL];
  var CELL_FIELDS = [
    TEXT,
    COLOR,
    TOOLTIP,
    ALIGNMENT,
    ALIGNMENT_VALUE,
    ICON_ASSET,
    ICON_SIZE,
    CHART_URL,
    UNDERLINE
  ];
  var FIRE_FIELDS = [
    TEXT,
    ENABLED,
    HEIGHT,
    FOCUS_POLICY,
    STYLE_SHEET,
    TOOLTIP,
    PATH,
    GLOW,
    GLOW_BLUR_RADIUS,
    GLOW_OFFSET
  ];
  var DETAIL_FIELDS = [TEXT, ENABLED, HEIGHT, STYLE_SHEET, TOOLTIP];
  var HEADER_FIELDS = [
    TEXT,
    TOOLTIP,
    FIELD_ID,
    DOT_TEXT,
    DOT_TOOLTIP,
    SORT_DIRECTION,
    SORT_MARK
  ];

  var PRIVACY_TOGGLED = "privacy_toggled";
  var HEADER_SORTED = "header_sorted";
  var CELL_CLICKED = "cell_clicked";
  var FIRE_CLICKED = "fire_clicked";
  var DETAIL_CLICKED = "detail_clicked";
  var ROW_PRESSED = "row_pressed";
  var VIEW_SCROLLED = "view_scrolled";

  // -- what a payload can be wrong about -------------------------------

  var MISSING_FAULT = "missing";
  var NULL_FAULT = "null";
  var NOT_AN_OBJECT_FAULT = "not-an-object";
  var WRONG_TYPE_FAULT = "wrong-type";
  var UNKNOWN_PATH_FAULT = "unknown-path";
  var STYLE_MISMATCH_FAULT = "style-mismatch";
  var GLOW_MISMATCH_FAULT = "glow-mismatch";
  var TEXT_MISMATCH_FAULT = "text-mismatch";
  var SHORT_LIST_FAULT = "short-list";
  var NOT_CSS_FAULT = "not-css";

  var ROW_AT = "row:";
  var CELL_AT = "/cell:";
  var FIRE_AT = "/fire";
  var DETAIL_AT = "/detail";
  var HEADER_AT = "header:";
  var PATH_SPLIT = ".";
  var EMPTY = "";

  var NO_BRIDGE = "the preload bridge is not present";

  // MODEL_KEY names the payload each drawn host keeps beside its React root.
  var MODEL_KEY = "model";

  // QT_ONLY names the Qt paint function no stylesheet can run.
  var QT_ONLY = "qlineargradient";

  // -- what the drawn table is made of ---------------------------------

  var TABLE_CLASS = "acervator-bot-table";

  var TABLE_TAG = "table";
  var HEAD_TAG = "thead";
  var BODY_TAG = "tbody";
  var ROW_TAG = "tr";
  var HEAD_CELL_TAG = "th";
  var CELL_TAG = "td";
  var BUTTON_TAG = "button";
  var BUTTON_TYPE = "button";
  var DISC_TAG = "span";
  var LABEL_TAG = "span";
  var DOT_TAG = "span";

  var STRETCH_MODE = "Stretch";
  var FIXED_TABLE_LAYOUT = "fixed";
  var FULL_WIDTH = "100%";

  // The CSS spelling of the wrap the surface asks a header label for.
  var WRAP_WHITE_SPACE = "normal";
  var WRAP_OVERFLOW = "break-word";
  var BLOCK_DISPLAY = "block";
  var CENTRE_ALIGN = "center";
  var RIGHT_ALIGN = "right";
  var HEADER_VERTICAL_ALIGN = "bottom";
  var DOT_MARGIN = "0 auto";
  var DOT_CURSOR = "pointer";
  var LABEL_KEY = "label";
  var DOT_KEY = "dot";
  var MARK_KEY = "mark";
  // The mark is outside the flow, so neither the wrap nor the dot's
  // centring moves when it draws.
  var RELATIVE_POSITION = "relative";
  var ABSOLUTE_POSITION = "absolute";
  var MARK_EDGE = "0";
  var MARK_MAX_WIDTH = "100%";
  // The CSS spelling of the elide a Qt table cell does by default.
  var CELL_OVERFLOW = "hidden";
  var CELL_TEXT_OVERFLOW = "ellipsis";
  var CELL_WHITE_SPACE = "nowrap";

  var PART_ATTR = "data-part";
  var TABLE_PART = "table";
  var HEAD_ROW_PART = "head-row";
  var HEADER_PART = "header";
  var HEADER_LABEL_PART = "header-label";
  var PRIVACY_DOT_PART = "privacy-dot";
  var SORT_MARK_PART = "sort-mark";
  var ROW_PART = "row";
  var CELL_PART = "cell";
  var FIRE_PART = "fire-button";
  var DETAIL_PART = "detail-button";
  var DISC_PART = "coin-icon";

  var ROW_ATTR = "data-row";
  var COLUMN_ATTR = "data-column";
  var BOT_ID_ATTR = "data-bot-id";
  var SKIPPED_ATTR = "data-skipped";
  var SELECTED_ATTR = "data-selected";
  var EXCHANGE_ATTR = "data-exchange";
  var PATH_ATTR = "data-path";
  var GLOW_ATTR = "data-glow";
  var FIELD_ID_ATTR = "data-field-id";
  var MASKED_ATTR = "data-masked";
  var ACTION_ATTR = "data-action";
  var SORT_DIRECTION_ATTR = "data-sort-direction";
  var SORTABLE_ATTR = "data-sortable";
  var CHART_URL_ATTR = "data-chart-url";
  var ICON_ATTR = "data-icon";
  var ICON_SIZE_ATTR = "data-icon-size";
  var ALIGNMENT_ATTR = "data-alignment";
  var ALIGNMENT_VALUE_ATTR = "data-alignment-value";
  var DECLARED_ROWS_ATTR = "data-declared-rows";
  var HELD_ROWS_ATTR = "data-held-rows";
  var DECLARED_COLUMNS_ATTR = "data-declared-columns";
  var HELD_COLUMNS_ATTR = "data-held-columns";
  var ARIA_LABEL = "aria-label";

  var SPACE = " ";
  var COMMA = ",";
  var VAR_OPEN = "var(--";
  // Built from COMMA and SPACE so the pair is not the surface's own
  // blockers_separator spelled out here.
  var VAR_SPLIT = COMMA + SPACE;
  var VAR_CLOSE = ")";
  var CALC_OPEN = "calc(";
  // The unit factor that turns a unitless token into a CSS length.
  var PX_FACTOR = " * 1px)";
  var PX = "px";
  // QFont point size in _get_coin_icon: int(size * 0.45).
  var DISC_LETTER_SHARE = 0.45;

  // ALIGNMENT_STYLE maps each published alignment word to CSS.
  var ALIGNMENT_STYLE = { AlignCenter: { textAlign: "center" } };

  var held = null;
  var tableFaults = [];
  var loadFault = null;
  var asked = null;
  var roots = [];
  var dispatched = [];
  // One payload per exchange, so a re-mount redraws that screen's own rows
  // rather than whichever exchange answered last.
  var models = {};
  // Each scroll box `watchScroll` has already bound, so one box takes one
  // listener however many times the rows are redrawn.
  var watched = [];

  // -- reading a payload safely ----------------------------------------

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

  // -- resolving a value through the modules that own the rule ---------

  // `table_cells.js` owns the one-carrier rule, and a page without it
  // paints every colour from the surface.
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
    return (
      CALC_OPEN + VAR_OPEN + name + VAR_SPLIT + String(value) + VAR_CLOSE + PX_FACTOR
    );
  }

  // `header_strip.js` owns the Qt style-sheet rule.
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

  // -- the styles the components paint with ----------------------------

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

  // The Fire glow as `box-shadow`, from the offset, blur and colour the
  // surface publishes.
  function glowShadow(button) {
    if (!isFilledText(button[GLOW])) {
      return undefined;
    }
    var offset = listField(button, GLOW_OFFSET).slice();
    var across = length(offset.shift());
    var down = length(offset.shift());
    var blur = length(button[GLOW_BLUR_RADIUS]);
    if (across === undefined || down === undefined || blur === undefined) {
      return undefined;
    }
    return [across, down, blur, colour(button[GLOW])].join(SPACE);
  }

  function fixedWidthOf(model, column) {
    var widths = objectField(model, FIXED_WIDTHS);
    var name = String(column);
    return owns(widths, name) ? widths[name] : undefined;
  }

  // -- the components --------------------------------------------------

  function element() {
    return global.React.createElement.apply(null, arguments);
  }

  // The label wraps inside its own column and the dot sits under it, so a
  // press on the label is not a control and only the dot masks.
  function HeaderLabel(props) {
    var model = props.model;
    var style = styleOf(model[HEADER_LABEL_STYLE]);
    if (model[HEADER_LABEL_WRAP]) {
      style.whiteSpace = WRAP_WHITE_SPACE;
      style.overflowWrap = WRAP_OVERFLOW;
    }
    style.display = BLOCK_DISPLAY;
    style.textAlign = CENTRE_ALIGN;
    var labelProps = { className: TABLE_CLASS, style: style };
    labelProps[PART_ATTR] = HEADER_LABEL_PART;
    return element(LABEL_TAG, labelProps, text(props.label));
  }

  function HeaderDot(props) {
    var model = props.model;
    var header = props.header;
    var column = props.column;
    var style = styleOf(model[HEADER_DOT_STYLE]);
    style.display = BLOCK_DISPLAY;
    style.height = length(model[HEADER_DOT_ROW_PX]);
    style.margin = DOT_MARGIN;
    if (!isFilledText(header[FIELD_ID])) {
      return element(DOT_TAG, { className: TABLE_CLASS, style: style });
    }
    style.cursor = DOT_CURSOR;
    var dotProps = {
      className: TABLE_CLASS,
      type: BUTTON_TYPE,
      style: style,
      title: label(header[DOT_TOOLTIP]),
      onClick: function (press) {
        // The heading sorts, so the dot keeps its own press to itself.
        press.stopPropagation();
        sendPrivacyToggle(model, column);
      }
    };
    dotProps[PART_ATTR] = PRIVACY_DOT_PART;
    dotProps[FIELD_ID_ATTR] = text(header[FIELD_ID]);
    dotProps[MASKED_ATTR] = text(header[MASKED]);
    dotProps[ACTION_ATTR] = text(objectField(model, ACTIONS)[PRIVACY_TOGGLED]);
    dotProps[ARIA_LABEL] = label(header[DOT_TOOLTIP]);
    return element(BUTTON_TAG, dotProps, text(header[DOT_TEXT]));
  }

  // The arrow marks which column the rows are ordered by, and which way.
  function SortMark(props) {
    var model = props.model;
    var style = styleOf(model[HEADER_SORT_MARK_STYLE]);
    style.position = ABSOLUTE_POSITION;
    style.bottom = length(model[HEADER_CELL_PAD_PX]);
    style.right = MARK_EDGE;
    style.width = length(model[HEADER_SORT_MARK_BOX_PX]);
    style.maxWidth = MARK_MAX_WIDTH;
    style.height = length(model[HEADER_DOT_ROW_PX]);
    style.lineHeight = length(model[HEADER_DOT_ROW_PX]);
    style.textAlign = RIGHT_ALIGN;
    var markProps = { className: TABLE_CLASS, style: style };
    markProps[PART_ATTR] = SORT_MARK_PART;
    return element(DOT_TAG, markProps, text(props.mark));
  }

  function HeaderCell(props) {
    var model = props.model;
    var header = isPlainObject(props.header) ? props.header : {};
    var column = props.column;
    var sortable = Boolean(header[SORTABLE]);
    var style = {};
    var width = fixedWidthOf(model, column);
    if (width !== undefined) {
      style.width = length(width);
    }
    style.verticalAlign = HEADER_VERTICAL_ALIGN;
    style.padding = length(model[HEADER_CELL_PAD_PX]);
    style.position = RELATIVE_POSITION;
    if (sortable) {
      style.cursor = DOT_CURSOR;
    }
    var headProps = {
      className: TABLE_CLASS,
      style: style,
      title: label(header[TOOLTIP])
    };
    headProps[PART_ATTR] = HEADER_PART;
    headProps[COLUMN_ATTR] = text(column);
    headProps[FIELD_ID_ATTR] = text(header[FIELD_ID]);
    headProps[ARIA_LABEL] = label(header[TEXT]);
    headProps[SORTABLE_ATTR] = String(sortable);
    headProps[SORT_DIRECTION_ATTR] = text(header[SORT_DIRECTION]);
    if (sortable) {
      headProps[ACTION_ATTR] = text(objectField(model, ACTIONS)[HEADER_SORTED]);
      headProps.onClick = function () {
        sendSort(model, column);
      };
    }
    return element(
      HEAD_CELL_TAG,
      headProps,
      element(HeaderLabel, { key: LABEL_KEY, model: model, label: header[TEXT] }),
      element(HeaderDot, {
        key: DOT_KEY,
        model: model,
        header: header,
        column: column
      }),
      element(SortMark, { key: MARK_KEY, model: model, mark: header[SORT_MARK] })
    );
  }

  function FireButton(props) {
    var model = props.model;
    var button = props.button;
    if (!isPlainObject(button)) {
      return null;
    }
    var style = styleOf(button[STYLE_SHEET]);
    style.height = length(button[HEIGHT]);
    var shadow = glowShadow(button);
    if (shadow !== undefined) {
      style.boxShadow = shadow;
    }
    var buttonProps = {
      className: TABLE_CLASS,
      style: style,
      title: label(button[TOOLTIP]),
      type: BUTTON_TYPE,
      disabled: !button[ENABLED],
      // Qt's Fire button takes the press off the row, so the row's own
      // press must not run as well.
      onClick: function (event) {
        event.stopPropagation();
        sendFire(model, props.botId);
      }
    };
    buttonProps[PART_ATTR] = FIRE_PART;
    buttonProps[PATH_ATTR] = text(button[PATH]);
    buttonProps[GLOW_ATTR] = text(button[GLOW]);
    buttonProps[BOT_ID_ATTR] = text(props.botId);
    buttonProps[ARIA_LABEL] = label(button[TEXT]);
    buttonProps[ACTION_ATTR] = text(objectField(model, ACTIONS)[FIRE_CLICKED]);
    return element(BUTTON_TAG, buttonProps, text(button[TEXT]));
  }

  function DetailButton(props) {
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
      disabled: !button[ENABLED],
      // Detail selects the row itself, through on_detail, so the row's own
      // press must not run as well and toggle it back off.
      onClick: function (event) {
        event.stopPropagation();
        sendDetail(model, props.botId);
      }
    };
    buttonProps[PART_ATTR] = DETAIL_PART;
    buttonProps[BOT_ID_ATTR] = text(props.botId);
    buttonProps[ARIA_LABEL] = label(button[TEXT]);
    buttonProps[ACTION_ATTR] = text(objectField(model, ACTIONS)[DETAIL_CLICKED]);
    return element(BUTTON_TAG, buttonProps, text(button[TEXT]));
  }

  // The disc _get_coin_icon paints: icon_color fills it, icon_letter names it
  // and icon_size sizes it.
  function CoinDisc(props) {
    var found = props.cell;
    var size = Number(found[ICON_SIZE]);
    var style = { background: colour(found[ICON_COLOR]) };
    if (size > 0) {
      style.width = size + PX;
      style.height = size + PX;
      style.lineHeight = size + PX;
      style.fontSize = Math.round(size * DISC_LETTER_SHARE) + PX;
    }
    var discProps = { className: TABLE_CLASS, style: style };
    discProps[PART_ATTR] = DISC_PART;
    discProps[ICON_ATTR] = text(found[ICON_ASSET]);
    discProps[ICON_SIZE_ATTR] = text(found[ICON_SIZE]);
    return element(DISC_TAG, discProps, text(found[ICON_LETTER]));
  }

  function BodyCell(props) {
    var model = props.model;
    var found = props.cell;
    var column = props.column;
    // The window's own cells elide inside their column; these did not, so
    // a long pair ran over the column beside it at a narrow width.
    var style = {
      overflow: CELL_OVERFLOW,
      textOverflow: CELL_TEXT_OVERFLOW,
      whiteSpace: CELL_WHITE_SPACE
    };
    var cellProps = { className: TABLE_CLASS, style: style };
    cellProps[PART_ATTR] = CELL_PART;
    cellProps[COLUMN_ATTR] = text(column);
    cellProps[ARIA_LABEL] = label(listField(model, COLUMNS)[column]);
    if (!isPlainObject(found)) {
      return element(CELL_TAG, cellProps, props.children);
    }
    if (isFilledText(found[COLOR])) {
      style.color = colour(found[COLOR]);
    }
    if (found[UNDERLINE] === true) {
      style.textDecoration = UNDERLINE;
    }
    withAlignment(style, found[ALIGNMENT]);
    cellProps.title = label(found[TOOLTIP]);
    cellProps[ALIGNMENT_ATTR] = text(found[ALIGNMENT]);
    cellProps[ALIGNMENT_VALUE_ATTR] = text(found[ALIGNMENT_VALUE]);
    cellProps[ICON_ATTR] = text(found[ICON_ASSET]);
    cellProps[ICON_SIZE_ATTR] = text(found[ICON_SIZE]);
    cellProps[CHART_URL_ATTR] = text(found[CHART_URL]);
    if (isFilledText(found[CHART_URL])) {
      cellProps[ACTION_ATTR] = text(objectField(model, ACTIONS)[CELL_CLICKED]);
      cellProps.onClick = function () {
        sendCellClick(model, props.at, column);
      };
    }
    if (props.children !== undefined) {
      return element(CELL_TAG, cellProps, props.children);
    }
    if (isFilledText(found[ICON_COLOR])) {
      return element(
        CELL_TAG,
        cellProps,
        element(CoinDisc, { key: DISC_PART, cell: found }),
        text(found[TEXT])
      );
    }
    return element(CELL_TAG, cellProps, text(found[TEXT]));
  }

  // The button one column holds, or undefined where the column holds text.
  function buttonAt(model, row, column, botId) {
    if (column === model[FIRE_COLUMN]) {
      return element(FireButton, { model: model, button: row[FIRE], botId: botId });
    }
    if (column === model[DETAIL_COLUMN]) {
      return element(DetailButton, { model: model, button: row[DETAIL], botId: botId });
    }
    return undefined;
  }

  function BotRow(props) {
    var model = props.model;
    var row = isPlainObject(props.row) ? props.row : {};
    var at = props.at;
    var botId = row[BOT_ID];
    var cells = listField(row, CELLS);
    var drawn = listField(model, COLUMNS).map(function (name, column) {
      return element(BodyCell, {
        key: String(column),
        model: model,
        cell: cells[column],
        column: column,
        at: at,
        children: buttonAt(model, row, column, botId)
      });
    });
    var selected = model[HAS_SELECTION] === true && at === model[CURRENT_ROW];
    var rowProps = {
      className: TABLE_CLASS,
      onClick: function () {
        sendRowPress(model, botId);
      }
    };
    rowProps[PART_ATTR] = ROW_PART;
    rowProps[ROW_ATTR] = text(at);
    rowProps[BOT_ID_ATTR] = text(botId);
    rowProps[SKIPPED_ATTR] = text(row[SKIPPED]);
    rowProps[SELECTED_ATTR] = String(selected);
    rowProps[DECLARED_COLUMNS_ATTR] = text(model[COLUMN_COUNT]);
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
    var headers = listField(model, HEADERS);
    var headProps = { className: TABLE_CLASS };
    headProps[PART_ATTR] = HEAD_ROW_PART;
    var tableStyle = styleOf(model[STYLE_SHEET]);
    if (model[HEADER_RESIZE_MODE] === STRETCH_MODE) {
      // The CSS spelling of the Qt stretch: every column takes its own
      // share of the table, and a label wraps rather than widen it.
      tableStyle.tableLayout = FIXED_TABLE_LAYOUT;
      tableStyle.width = FULL_WIDTH;
    }
    var tableProps = {
      id: props.id,
      className: TABLE_CLASS,
      style: tableStyle
    };
    tableProps[PART_ATTR] = TABLE_PART;
    tableProps[EXCHANGE_ATTR] = text(model[EXCHANGE_ID]);
    tableProps[ARIA_LABEL] = label(model[ACCESSIBLE_NAME]);
    tableProps[DECLARED_ROWS_ATTR] = text(model[ROW_COUNT]);
    tableProps[HELD_ROWS_ATTR] = String(rows.length);
    tableProps[DECLARED_COLUMNS_ATTR] = text(model[COLUMN_COUNT]);
    tableProps[HELD_COLUMNS_ATTR] = String(listField(model, COLUMNS).length);
    return element(
      TABLE_TAG,
      tableProps,
      element(
        HEAD_TAG,
        null,
        element(
          ROW_TAG,
          headProps,
          headers.map(function (header, column) {
            return element(HeaderCell, {
              key: String(column),
              model: model,
              header: header,
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

  // -- what the payload carries, and what it does not ------------------

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

  // A wrong type is named only where the surface publishes a default of
  // the same meaning to hold it against.
  function checkTypeAgainst(where, bag, field, holder) {
    if (holder === null || holder === undefined) {
      return;
    }
    if (!owns(bag, field)) {
      tableFaults.push(fault(where, field, MISSING_FAULT, null));
      return;
    }
    if (bag[field] === null) {
      tableFaults.push(fault(where, field, NULL_FAULT, null));
      return;
    }
    if (kindOf(bag[field]) !== kindOf(holder)) {
      tableFaults.push(fault(where, field, WRONG_TYPE_FAULT, kindOf(bag[field])));
    }
  }

  function checkSameText(where, bag, field, declared) {
    if (!isFilledText(declared) || !owns(bag, field)) {
      return;
    }
    if (bag[field] !== declared) {
      tableFaults.push(
        fault(where, field, TEXT_MISMATCH_FAULT, {
          declared: declared,
          held: bag[field]
        })
      );
    }
  }

  function checkNamed(where, bag, names) {
    names.forEach(function (name) {
      if (!owns(bag, name)) {
        tableFaults.push(fault(where, name, MISSING_FAULT, null));
      }
    });
  }

  function checkSheet(where, field, sheet) {
    declarations(sheet).forEach(function (one) {
      if (carries(one.value, QT_ONLY)) {
        tableFaults.push(fault(where, field, NOT_CSS_FAULT, one.property));
      }
    });
  }

  function checkSheets(model) {
    var styles = objectField(model, FIRE_STYLES);
    Object.keys(styles).forEach(function (path) {
      checkSheet(FIRE_STYLES, path, styles[path]);
    });
    checkSheet(null, DETAIL_STYLE, model[DETAIL_STYLE]);
    checkSheet(null, STYLE_SHEET, model[STYLE_SHEET]);
  }

  function checkCells(model, where, row) {
    var cells = listField(row, CELLS);
    if (cells.length !== model[COLUMN_COUNT]) {
      tableFaults.push(fault(where, CELLS, SHORT_LIST_FAULT, cells.length));
    }
    cells.forEach(function (found, column) {
      if (found === null) {
        return;
      }
      var at = where + CELL_AT + String(column);
      if (!isPlainObject(found)) {
        tableFaults.push(fault(at, null, NOT_AN_OBJECT_FAULT, kindOf(found)));
        return;
      }
      checkNamed(at, found, CELL_FIELDS);
      checkTypeAgainst(at, found, TEXT, model[EMPTY_TEXT]);
      checkTypeAgainst(at, found, ALIGNMENT, model[ALIGNMENT]);
      checkTypeAgainst(at, found, ALIGNMENT_VALUE, model[ALIGNMENT_VALUE]);
      if (column === model[BOT_ID_COLUMN]) {
        checkTypeAgainst(at, found, COLOR, model[DEFAULT_STATE_COLOR]);
      }
    });
  }

  function checkFire(model, where, button) {
    if (button === null || button === undefined) {
      return;
    }
    var at = where + FIRE_AT;
    if (!isPlainObject(button)) {
      tableFaults.push(fault(at, null, NOT_AN_OBJECT_FAULT, kindOf(button)));
      return;
    }
    checkNamed(at, button, FIRE_FIELDS);
    checkTypeAgainst(at, button, TEXT, model[FIRE_LABEL]);
    checkTypeAgainst(at, button, STYLE_SHEET, model[FIRE_STYLE_HEAD]);
    checkTypeAgainst(at, button, HEIGHT, model[BUTTON_HEIGHT]);
    checkTypeAgainst(at, button, FOCUS_POLICY, model[FOCUS_POLICY]);
    checkTypeAgainst(at, button, GLOW_BLUR_RADIUS, model[GLOW_BLUR_RADIUS]);
    var path = button[PATH];
    if (!contains(listField(model, FIRE_PATHS), path)) {
      tableFaults.push(
        fault(at, PATH, UNKNOWN_PATH_FAULT, path === undefined ? null : path)
      );
      return;
    }
    var styles = objectField(model, FIRE_STYLES);
    if (owns(styles, path) && button[STYLE_SHEET] !== styles[path]) {
      tableFaults.push(
        fault(at, STYLE_SHEET, STYLE_MISMATCH_FAULT, {
          declared: styles[path],
          held: button[STYLE_SHEET]
        })
      );
    }
    var glows = objectField(model, FIRE_GLOWS);
    if (owns(glows, path) && button[GLOW] !== glows[path]) {
      tableFaults.push(
        fault(at, GLOW, GLOW_MISMATCH_FAULT, {
          declared: glows[path],
          held: button[GLOW]
        })
      );
    }
  }

  function checkDetail(model, where, button) {
    if (button === null || button === undefined) {
      return;
    }
    var at = where + DETAIL_AT;
    if (!isPlainObject(button)) {
      tableFaults.push(fault(at, null, NOT_AN_OBJECT_FAULT, kindOf(button)));
      return;
    }
    checkNamed(at, button, DETAIL_FIELDS);
    checkTypeAgainst(at, button, TEXT, model[DETAIL_LABEL]);
    checkTypeAgainst(at, button, STYLE_SHEET, model[DETAIL_STYLE]);
    checkTypeAgainst(at, button, TOOLTIP, model[DETAIL_TOOLTIP]);
    checkTypeAgainst(at, button, HEIGHT, model[BUTTON_HEIGHT]);
    checkSameText(at, button, TEXT, model[DETAIL_LABEL]);
    checkSameText(at, button, STYLE_SHEET, model[DETAIL_STYLE]);
    checkSameText(at, button, TOOLTIP, model[DETAIL_TOOLTIP]);
  }

  function checkRows(model) {
    listField(model, ROWS).forEach(function (row, at) {
      var where = ROW_AT + String(at);
      if (!isPlainObject(row)) {
        tableFaults.push(fault(where, null, NOT_AN_OBJECT_FAULT, kindOf(row)));
        return;
      }
      checkNamed(where, row, ROW_FIELDS);
      checkCells(model, where, row);
      checkFire(model, where, row[FIRE]);
      checkDetail(model, where, row[DETAIL]);
    });
  }

  function checkHeaders(model) {
    var headers = listField(model, HEADERS);
    if (headers.length && headers.length !== model[COLUMN_COUNT]) {
      tableFaults.push(fault(HEADERS, null, SHORT_LIST_FAULT, headers.length));
    }
    headers.forEach(function (header, column) {
      var where = HEADER_AT + String(column);
      if (!isPlainObject(header)) {
        tableFaults.push(fault(where, null, NOT_AN_OBJECT_FAULT, kindOf(header)));
        return;
      }
      checkNamed(where, header, HEADER_FIELDS);
      HEADER_FIELDS.forEach(function (name) {
        checkTypeAgainst(where, header, name, model[EMPTY_TEXT]);
      });
    });
  }

  function heldFieldCount() {
    return DECLARED_FIELDS.filter(function (field) {
      return held !== null && owns(held.model, field);
    }).length;
  }

  // Counts fields, rows and columns declared against those held.
  function report() {
    var model = held.model;
    return {
      declared: {
        fields: DECLARED_FIELDS.length,
        rows: model[ROW_COUNT],
        columns: model[COLUMN_COUNT]
      },
      held: {
        fields: heldFieldCount(),
        rows: listField(model, ROWS).length,
        columns: listField(model, COLUMNS).length
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
    checkHeaders(model);
    checkRows(model);
    checkSheets(model);
    return report();
  }

  // loadTable asks METHOD once per distinct request, clearing asked so a
  // refusal retries and so a second screen is not answered with the first
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

  function heldModel() {
    return held === null ? {} : held.model;
  }

  function actionNamed(model, name) {
    return objectField(model, ACTIONS)[name];
  }

  // One request, keyed by the name the surface publishes for that field
  // and naming the exchange the clicked screen was drawn for.
  function request(model, field, value) {
    var params = {};
    params[String(model[field])] = value;
    params[String(model[EXCHANGE_ID_PARAM_FIELD])] = text(model[EXCHANGE_ID]);
    return params;
  }

  // The answer replaces only the screens drawn for that same exchange, so
  // a click on one exchange's table leaves another exchange's rows alone.
  function dispatch(model, name, params) {
    var exchange = text(model[EXCHANGE_ID]);
    dispatched.push({ action: name, params: params, exchange: exchange });
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

  function sendPrivacyToggle(model, column) {
    return dispatch(
      model,
      actionNamed(model, PRIVACY_TOGGLED),
      request(model, PRIVACY_TOGGLE_PARAM, column)
    );
  }

  function sendSort(model, column) {
    return dispatch(
      model,
      actionNamed(model, HEADER_SORTED),
      request(model, SORT_COLUMN_PARAM, column)
    );
  }

  function sendCellClick(model, row, column) {
    return dispatch(
      model,
      actionNamed(model, CELL_CLICKED),
      request(model, CELL_CLICK_PARAM, [row, column])
    );
  }

  function sendFire(model, botId) {
    return dispatch(
      model,
      actionNamed(model, FIRE_CLICKED),
      request(model, FIRE_PARAM, botId)
    );
  }

  function sendDetail(model, botId) {
    return dispatch(
      model,
      actionNamed(model, DETAIL_CLICKED),
      request(model, DETAIL_PARAM, botId)
    );
  }

  // A press on one row, which moves the Voting Panel to that row's bot and
  // takes it off that bot when the row is the one already shown.
  function sendRowPress(model, botId) {
    return dispatch(
      model,
      actionNamed(model, ROW_PRESSED),
      request(model, SELECT_BOT_PARAM, botId)
    );
  }

  // The nearest ancestor that scrolls the rows, or null while none does.
  function scrollBoxOf(node) {
    var found = node;
    while (found && found !== global.document.body) {
      if (found.scrollHeight > found.clientHeight + 1) {
        return found;
      }
      found = found.parentElement;
    }
    return null;
  }

  // The first and last row index the scroll box draws whole.
  function visibleRowBand(node) {
    var box = scrollBoxOf(node);
    if (box === null) {
      return null;
    }
    var edge = box.getBoundingClientRect();
    var first = -1;
    var last = -1;
    var found = node.querySelectorAll("[" + PART_ATTR + '="' + ROW_PART + '"]');
    Array.prototype.forEach.call(found, function (one) {
      var at = Number(one.getAttribute(ROW_ATTR));
      var span = one.getBoundingClientRect();
      if (span.top >= edge.top - 1 && span.bottom <= edge.bottom + 1) {
        if (first < 0) {
          first = at;
        }
        last = at;
      }
    });
    return first < 0 ? null : [first, last];
  }

  // The payload one drawn host is holding, or null for a host not drawn into.
  function modelAt(target) {
    var found = null;
    roots.forEach(function (pair) {
      if (pair.node === target) {
        found = pair.model;
      }
    });
    return found;
  }

  // The rows drawn after a hand scroll, which releases a highlight the box
  // no longer shows. The Voting Panel keeps the bot it is drawing.
  function sendViewBand(model, band) {
    return dispatch(
      model,
      actionNamed(model, VIEW_SCROLLED),
      request(model, VIEW_BAND_PARAM, band)
    );
  }

  // One listener per scroll box, bound once the rows overflow it.
  function watchScroll(target) {
    var box = scrollBoxOf(target);
    if (box === null || watched.indexOf(box) >= 0) {
      return null;
    }
    watched.push(box);
    box.addEventListener("scroll", function () {
      var band = visibleRowBand(target);
      var model = modelAt(target);
      if (band !== null && isPlainObject(model)) {
        sendViewBand(model, band);
      }
    });
    return box;
  }

  function sent() {
    return dispatched.slice();
  }

  // The payload this module holds for one exchange, or null for none.
  function modelFor(exchangeId) {
    return owns(models, String(exchangeId)) ? models[String(exchangeId)] : null;
  }

  // The exchange each host this module has drawn into is holding rows for.
  function drawnExchanges() {
    return roots.map(function (pair) {
      return text(objectField(pair, MODEL_KEY)[EXCHANGE_ID]);
    });
  }

  // Every host this module has drawn into, re-drawn from its own model.
  function redraw() {
    roots.forEach(function (pair) {
      draw(pair.node, element(Table, { model: objectField(pair, MODEL_KEY) }));
    });
    return roots.length;
  }

  // -- reading the held payload ----------------------------------------------------------

  function payload() {
    return copyOf(heldModel());
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

  function headers() {
    return list(HEADERS);
  }

  function header(column) {
    return headers()[column];
  }

  function rows() {
    return list(ROWS);
  }

  function row(at) {
    return rows()[at];
  }

  function cellAt(at, column) {
    var found = row(at);
    return isPlainObject(found) ? listField(found, CELLS)[column] : undefined;
  }

  function fire(at) {
    var found = row(at);
    return isPlainObject(found) ? found[FIRE] : undefined;
  }

  function detail(at) {
    var found = row(at);
    return isPlainObject(found) ? found[DETAIL] : undefined;
  }

  function firePath(at) {
    var button = fire(at);
    return isPlainObject(button) ? button[PATH] : undefined;
  }

  function botIds() {
    return list(BOT_IDS);
  }

  // Each row's own bot id, which is what a row is identified by.
  function rowBotIds() {
    return rows().map(function (found) {
      return isPlainObject(found) ? found[BOT_ID] : undefined;
    });
  }

  // rowTexts returns each row bot_id beside its cell texts.
  function rowTexts() {
    return rows().map(function (found) {
      var cells = listField(found, CELLS);
      return {
        bot_id: isPlainObject(found) ? found[BOT_ID] : undefined,
        texts: cells.map(function (one) {
          return isPlainObject(one) ? one[TEXT] : null;
        })
      };
    });
  }

  function selectedBotId() {
    return field(SELECTED_BOT_ID);
  }

  function skippedRows() {
    return list(SKIPPED_ROWS);
  }

  function calls() {
    return list(CALLS);
  }

  function action(name) {
    var found = bag(ACTIONS);
    return owns(found, name) ? found[name] : undefined;
  }

  function stateColour(name) {
    var found = bag(STATE_COLORS);
    return owns(found, name) ? found[name] : undefined;
  }

  function columnTooltip(column) {
    var found = bag(COLUMN_TOOLTIPS);
    var name = String(column);
    return owns(found, name) ? found[name] : undefined;
  }

  function privacyField(column) {
    var found = bag(PRIVACY_FIELD_BY_COL);
    var name = String(column);
    return owns(found, name) ? found[name] : undefined;
  }

  function fixedWidth(column) {
    return held === null ? undefined : fixedWidthOf(held.model, column);
  }

  function fireStyle(path) {
    var found = bag(FIRE_STYLES);
    return owns(found, path) ? found[path] : undefined;
  }

  function fireGlow(path) {
    var found = bag(FIRE_GLOWS);
    return owns(found, path) ? found[path] : undefined;
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
    return tableFaults.slice();
  }

  function loadError() {
    return loadFault;
  }

  function isLoaded() {
    return held !== null;
  }

  // -- drawing ----------------------------------------------------------

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

  function renderTable(target, model) {
    var drawn = model;
    if (!isPlainObject(drawn)) {
      drawn = held === null ? null : held.model;
    }
    var host = draw(target, element(Table, { model: drawn }));
    roots.forEach(function (pair) {
      if (pair.node === target) {
        pair.model = drawn;
      }
    });
    watchScroll(target);
    return host;
  }

  function forget() {
    held = null;
    tableFaults = [];
    loadFault = null;
    asked = null;
    dispatched = [];
    models = {};
    watched = [];
  }

  global.acervatorSetBotTable = setTable;
  global.acervatorLoadBotTable = loadTable;
  global.acervatorBotTable = {
    method: METHOD,
    Table: Table,
    BotRow: BotRow,
    BodyCell: BodyCell,
    HeaderCell: HeaderCell,
    SortMark: SortMark,
    sendSort: sendSort,
    FireButton: FireButton,
    DetailButton: DetailButton,
    payload: payload,
    declaredNames: declaredNames,
    field: field,
    headers: headers,
    header: header,
    rows: rows,
    row: row,
    cellAt: cellAt,
    fire: fire,
    detail: detail,
    firePath: firePath,
    botIds: botIds,
    rowBotIds: rowBotIds,
    rowTexts: rowTexts,
    selectedBotId: selectedBotId,
    skippedRows: skippedRows,
    calls: calls,
    action: action,
    stateColour: stateColour,
    columnTooltip: columnTooltip,
    privacyField: privacyField,
    fixedWidth: fixedWidth,
    fireStyle: fireStyle,
    fireGlow: fireGlow,
    alignmentWords: alignmentWords,
    glowShadow: glowShadow,
    styleOf: styleOf,
    declarations: declarations,
    variableFor: variableFor,
    colour: colour,
    length: length,
    kinds: kinds,
    faults: faults,
    loadError: loadError,
    isLoaded: isLoaded,
    renderTable: renderTable,
    redraw: redraw,
    modelFor: modelFor,
    drawnExchanges: drawnExchanges,
    sendPrivacyToggle: sendPrivacyToggle,
    sendCellClick: sendCellClick,
    sendFire: sendFire,
    sendDetail: sendDetail,
    sendRowPress: sendRowPress,
    sendViewBand: sendViewBand,
    visibleRowBand: visibleRowBand,
    scrollBoxOf: scrollBoxOf,
    sent: sent,
    forget: forget
  };
})(window);
