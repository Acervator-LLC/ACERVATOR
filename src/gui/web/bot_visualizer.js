// The Bot Swarm tab, as the Python surface serves it.
(function (global) {
  "use strict";

  var METHOD = "bot_visualizer.state";

  // Every field bot_visualizer_surface publishes, answered by field().
  var DECLARED_FIELDS = [
    "actions", "all_exchanges_label", "all_exchanges_value", "any_masked",
    "bench_pnl_placeholder", "bench_remove_button_size",
    "bench_run_button_size", "bench_start_button_size", "bench_widths",
    "bidirectional_offset_px", "bot_ids", "bot_log_topic", "bots_key",
    "broken_dot_style_sheet", "broken_privacy_button_style_sheet",
    "bus_emitted", "bus_topics", "button_kind", "canvas_shown",
    "capital_max", "capital_min", "capital_prefix",
    "capital_start", "capital_text_format", "colors", "column_widths",
    "confirm_default_button", "confirm_head_format", "confirm_line_format",
    "confirm_pct_format", "confirm_plural", "confirm_tail", "confirm_title",
    "confirm_unshowable_log", "context_cfg_keys", "curve_scale",
    "default_candle_total", "default_capital", "default_pnl",
    "default_theme_key", "description_style_sheet",
    "description_word_wrap", "dest_key", "dot_cursor", "dot_text",
    "drag_onto_wired_why", "drag_start_id", "drag_to_empty_why", "dragging",
    "emitted", "empty_alignment", "empty_style_sheet", "empty_text",
    "empty_visible", "exchange", "exchange_caption", "exchange_items",
    "exchange_tooltip", "exchanges", "fallback_kind", "fallback_tint",
    "feed_cfg_keys", "frame_interval_ms", "grid_alignment", "grid_cells",
    "grid_cols", "grid_margins", "grid_spacing", "header_hint",
    "header_spacing", "header_title", "hit_samples", "hit_threshold_px",
    "hydration_emitted_info", "hydration_failed_error",
    "hydration_no_bus_error", "hydration_rejected_warning",
    "hydration_shortfall_warning", "ids_in_scope", "inflow_stat_key",
    "info_level", "inner_spacing", "is_empty", "label_kind",
    "label_word_wrap", "layer_chrome", "layer_header_spacing",
    "layer_id_keys", "layer_list_margins", "layer_list_spacing",
    "layer_margins", "layer_signals", "layer_spacing", "layer_stop_status",
    "list_refresh_debug", "list_row_keys", "live_mode", "live_row_order",
    "live_rows", "log_lines", "logger_name", "mask_failed_warning_format",
    "mask_field_id", "mask_text", "mask_unavailable_warning", "masked",
    "masked_glyph", "menu_cancel", "menu_disconnect", "menu_disconnect_both",
    "menu_separator", "menu_style_sheet", "menu_wire_header_format",
    "method", "min_wire_pct", "missing_amount", "missing_text",
    "nested_margins", "no_offset_px", "opacity_max_pct", "opacity_min_pct",
    "opacity_pct", "opacity_slider_width_px", "opacity_start_pct",
    "opacity_tooltip", "outer_margins", "outer_spacing", "outflow_stat_key",
    "paper_bench_id_format", "paper_bench_pairs", "paper_bench_sources",
    "paper_mode", "paper_registered_signal", "paper_row_order", "paper_rows",
    "bot_symbols", "drag_start_pos", "locust_cards", "overlay_style",
    "panel", "panel_words",
    "paper_summary", "paper_summary_active_format",
    "paper_summary_active_start", "paper_summary_capital_format",
    "paper_summary_capital_start", "paper_summary_pnl",
    "paper_summary_start", "paper_summary_title", "paper_tab_index",
    "pct_key", "phase_rate", "picker_incoming_format",
    "picker_incoming_header", "picker_outgoing_format",
    "picker_outgoing_header", "pnl_placeholder_text", "pnl_text_format",
    "price_format_limit", "price_large_format", "price_small_format",
    "privacy_dot_style_sheet", "privacy_dot_tooltip",
    "privacy_failed_warning_format", "privacy_glyph",
    "privacy_mode_off_text", "privacy_mode_on_text",
    "privacy_mode_style_sheet", "privacy_mode_text", "privacy_mode_tooltip",
    "privacy_off_style_sheet", "privacy_on_style_sheet",
    "privacy_unavailable_warning", "progress_done_text", "progress_max_pct",
    "progress_min_total", "progress_scale", "progress_start_text",
    "progress_text_format", "qt_unset_spacing", "remove_button_text",
    "revealed_glyph", "routes_key", "row_handle_keys", "row_kind",
    "row_kinds", "row_margins", "row_radius_px", "row_spacing", "rows_sent",
    "run_button_text", "scroll_style_sheet", "scrumming_key",
    "short_id_length", "signals", "sim_bench_assets", "sim_bench_id_format",
    "sim_bench_presets", "sim_candle_total", "sim_mode",
    "sim_registered_signal", "sim_row_order", "sim_rows", "sim_summary",
    "sim_summary_pnl_empty", "sim_summary_pnl_format",
    "sim_summary_running_format", "sim_summary_start", "sim_summary_title",
    "sim_summary_trades", "sim_summary_trades_start",
    "sim_summary_wins_start", "sim_tab_index", "start_button_text",
    "start_phase", "state_write_failed_error", "status_done", "status_idle",
    "status_live", "status_running", "status_stopped", "stop_button_text",
    "summary_label_style_sheet", "summary_margins", "summary_spacing",
    "layer_list_style_sheet", "swarm_accents", "swarm_tab_index",
    "swarm_tints", "tab_kind", "tab_style_sheet", "tab_titles",
    "theme_caption", "theme_key", "theme_keys", "theme_start_index",
    "threads", "timer_delays_ms", "timers", "trades_placeholder_text",
    "trades_text_format", "visible_bots", "viz_margins", "viz_spacing",
    "warning_level", "wire_config_prompt_format", "wire_config_row_label",
    "wire_config_title", "wire_config_width_px", "wire_connected_log_format",
    "wire_count", "wire_created_topic", "wire_disconnected_log_format",
    "wire_keys", "wire_menu_style_sheet", "wire_pct_max", "wire_pct_min",
    "wire_pct_start", "wire_pct_suffix", "wire_removed_topic", "wire_sheet",
    "wires",
    "wires_caption"
  ];

  var HEADER_TITLE = "header_title";
  var HEADER_HINT = "header_hint";
  var HEADER_SPACING = "header_spacing";
  var OUTER_MARGINS = "outer_margins";
  var OUTER_SPACING = "outer_spacing";
  var VIZ_MARGINS = "viz_margins";
  var VIZ_SPACING = "viz_spacing";
  var INNER_SPACING = "inner_spacing";
  var LAYER_MARGINS = "layer_margins";
  var LAYER_SPACING = "layer_spacing";
  var LAYER_HEADER_SPACING = "layer_header_spacing";
  var LAYER_LIST_MARGINS = "layer_list_margins";
  var LAYER_LIST_SPACING = "layer_list_spacing";
  var SUMMARY_MARGINS = "summary_margins";
  var SUMMARY_SPACING = "summary_spacing";
  var NESTED_MARGINS = "nested_margins";
  var GRID_MARGINS = "grid_margins";
  var GRID_SPACING = "grid_spacing";
  var GRID_COLS = "grid_cols";
  var GRID_CELLS = "grid_cells";
  var BOT_IDS = "bot_ids";
  var EMPTY_TEXT = "empty_text";
  var EMPTY_STYLE_SHEET = "empty_style_sheet";
  var EMPTY_VISIBLE = "empty_visible";
  var TAB_TITLES = "tab_titles";
  var TAB_STYLE_SHEET = "tab_style_sheet";
  var SWARM_TAB_INDEX = "swarm_tab_index";
  var SIM_TAB_INDEX = "sim_tab_index";
  var PAPER_TAB_INDEX = "paper_tab_index";
  var EXCHANGE = "exchange";
  var EXCHANGE_ITEMS = "exchange_items";
  var EXCHANGE_CAPTION = "exchange_caption";
  var EXCHANGE_TOOLTIP = "exchange_tooltip";
  var THEME_CAPTION = "theme_caption";
  var THEME_KEY = "theme_key";
  var THEME_KEYS = "theme_keys";
  var WIRES_CAPTION = "wires_caption";
  var OPACITY_PCT = "opacity_pct";
  var OPACITY_MIN_PCT = "opacity_min_pct";
  var OPACITY_MAX_PCT = "opacity_max_pct";
  var OPACITY_SLIDER_WIDTH = "opacity_slider_width_px";
  var OPACITY_TOOLTIP = "opacity_tooltip";
  var PRIVACY_GLYPH = "privacy_glyph";
  var PRIVACY_DOT_STYLE_SHEET = "privacy_dot_style_sheet";
  var PRIVACY_DOT_TOOLTIP = "privacy_dot_tooltip";
  var PRIVACY_MODE_TEXT = "privacy_mode_text";
  var PRIVACY_MODE_STYLE_SHEET = "privacy_mode_style_sheet";
  var PRIVACY_MODE_TOOLTIP = "privacy_mode_tooltip";
  var DOT_CURSOR = "dot_cursor";
  var LABEL_WORD_WRAP = "label_word_wrap";
  var DESCRIPTION_WORD_WRAP = "description_word_wrap";
  var DESCRIPTION_STYLE_SHEET = "description_style_sheet";
  var SCROLL_STYLE_SHEET = "scroll_style_sheet";
  var LAYER_LIST_STYLE_SHEET = "layer_list_style_sheet";
  var SUMMARY_LABEL_STYLE_SHEET = "summary_label_style_sheet";
  var LAYER_CHROME = "layer_chrome";
  var COLUMN_WIDTHS = "column_widths";
  var ROW_HANDLE_KEYS = "row_handle_keys";
  var ACTIONS = "actions";

  var LIVE_ROWS = "live_rows";
  var SIM_ROWS = "sim_rows";
  var PAPER_ROWS = "paper_rows";
  var LIVE_ROW_ORDER = "live_row_order";
  var SIM_ROW_ORDER = "sim_row_order";
  var PAPER_ROW_ORDER = "paper_row_order";
  var SIM_SUMMARY = "sim_summary";
  var PAPER_SUMMARY = "paper_summary";

  var HEADING_TEXT = "heading_text";
  var HEADING_STYLE_SHEET = "heading_style_sheet";
  var DESCRIPTION_TEXT = "description_text";
  var SUMMARY_TITLE = "summary_title";
  var SUMMARY_STYLE_SHEET = "summary_style_sheet";
  var SUMMARY_ORDER = "summary_order";
  var BUTTONS = "buttons";

  var TEXT = "text";
  var STYLE_SHEET = "style_sheet";
  var WIDTH = "width";
  var KIND = "kind";
  var WIDGET = "widget";
  var MARGINS = "margins";
  var SPACING = "spacing";
  var WIRES = "wires";
  var IS_EMPTY = "is_empty";
  var TAB_WIDGET_SELECTOR = "QTabWidget";
  var REPEAT_OPEN = "repeat(";
  var REPEAT_TAIL = ", max-content)";
  var SPAN_OPEN = "span ";

  var LIVE = "live";
  var SIM = "sim";
  var PAPER = "paper";

  // Each layer names the payload fields its rows and order arrive in.
  var LAYER_SLOTS = [
    { key: LIVE, rows: LIVE_ROWS, order: LIVE_ROW_ORDER },
    { key: SIM, rows: SIM_ROWS, order: SIM_ROW_ORDER },
    { key: PAPER, rows: PAPER_ROWS, order: PAPER_ROW_ORDER }
  ];

  var MISSING_FAULT = "missing";
  var NULL_FAULT = "null";
  var NOT_AN_OBJECT_FAULT = "not-an-object";
  var WRONG_TYPE_FAULT = "wrong-type";
  var QT_COLOUR_FAULT = "qt-colour";
  var DISAGREES_FAULT = "disagrees";
  var UNPLACED_FAULT = "unplaced";
  var NO_SHEET_SOURCE_FAULT = "no-sheet-source";
  var NO_THEME_SOURCE_FAULT = "no-theme-source";

  var ROW_AT = "row:";
  var LAYER_AT = "layer:";

  var NO_BRIDGE = "the preload bridge is not present";

  var PATH_SPLIT = ".";
  var EMPTY = "";
  var GAP = " ";
  var SLASH = "/";
  var SEMICOLON = ";";
  var COLON = ":";
  var COMMA = ",";
  var HASH = "#";
  var DOT = ".";
  var PERCENT = "%";
  var CLOSE = ")";
  var PX = "px";
  var VAR_OPEN = "var(--";
  var VAR_SPLIT = COMMA + GAP;
  var VAR_CLOSE = ")";
  var CALC_OPEN = "calc(";
  // The unit factor that turns a unitless token into a CSS length.
  var PX_FACTOR = " * 1px)";

  // Qt reads an eight-digit hex colour alpha first; CSS reads it last.
  var HEX_ARGB = "AARRGGBB";
  // Qt counts an rgba alpha in bytes; CSS counts it as a fraction.
  var RGBA_OPEN = "rgba(";

  // A gap borrows only from spacing, because a radius means something else.
  var SPACE_GROUPS = ["spacing"];
  // A drawn width borrows only from the two groups that measure widths.
  var WIDTH_GROUPS = ["target_sizes", "table_columns"];

  var ROW = "row";
  var COLUMN = "column";
  var FLEX = "flex";
  var FLEX_NONE = "none";
  var GRID = "grid";
  var HIDDEN = "hidden";
  var AUTO = "auto";
  var NOWRAP = "nowrap";
  var PRE_WRAP = "pre-wrap";
  var NORMAL = "normal";
  var NONE = "none";
  var START = "flex-start";
  var CENTER = "center";
  var POINTER = "pointer";
  // dot_cursor carries a Qt cursor name; CSS names the same cursor differently.
  var CURSOR_BY_NAME = { PointingHandCursor: POINTER };
  var BUTTON_TYPE = "button";
  var RANGE_TYPE = "range";
  var DIV_TAG = "div";
  var SPAN_TAG = "span";
  var BUTTON_TAG = "button";
  var SELECT_TAG = "select";
  var OPTION_TAG = "option";
  var INPUT_TAG = "input";

  var TAB_CLASS = "acervator-swarm-tab";
  var ROW_CLASS = "acervator-swarm-row";
  var CELL_CLASS = "acervator-swarm-cell";
  var INPUT_CLASS = "acervator-swarm-input";

  var TAB_PART = "tab";
  var TAB_BAR_PART = "tab-bar";
  var TAB_BUTTON_PART = "tab-button";
  var TAB_BODY_PART = "tab-body";
  var SWARM_PANE_PART = "swarm-pane";
  var LAYER_PANE_PART = "layer-pane";
  var HEADER_ROW_PART = "header-row";
  var HEADER_TITLE_PART = "header-title";
  var HEADER_HINT_PART = "header-hint";
  var PRIVACY_DOT_PART = "privacy-dot";
  var PRIVACY_MODE_PART = "privacy-mode";
  var CAPTION_PART = "caption";
  var EXCHANGE_SELECT_PART = "exchange-select";
  var THEME_SELECT_PART = "theme-select";
  var OPACITY_SLIDER_PART = "opacity-slider";
  var STRETCH_PART = "stretch";
  var INNER_ROW_PART = "inner-row";
  var GRID_PAGE_PART = "grid-page";
  var LOCUST_PART = "locust";
  var EMPTY_PART = "empty";
  var WIRE_CANVAS_PART = "wire-canvas";
  var QUICK_ROUTING_PART = "quick-routing";
  var LIVE_ROWS_PART = "live-rows";
  var LAYER_HEADER_PART = "layer-header";
  var LAYER_HEADING_PART = "layer-heading";
  var LAYER_BUTTON_PART = "layer-button";
  var LAYER_DESCRIPTION_PART = "layer-description";
  var LAYER_SCROLL_PART = "layer-scroll";
  var LAYER_LIST_PART = "layer-list";
  var SWARM_ROW_PART = "swarm-row";
  var SWARM_CELL_PART = "swarm-cell";
  var SUMMARY_PART = "summary";
  var SUMMARY_TITLE_PART = "summary-title";
  var SUMMARY_LINE_PART = "summary-line";

  var PART_ATTR = "data-part";
  var SLOT_ATTR = "data-slot";
  var KEY_ATTR = "data-key";
  var ACTION_ATTR = "data-action";
  var INDEX_ATTR = "data-index";
  var ROW_ATTR = "data-row";
  var COLUMN_ATTR = "data-column";
  var LAYER_ATTR = "data-layer";
  var CURRENT_ATTR = "data-current";
  var HOVERED_ATTR = "data-hovered";
  var COUNT_ATTR = "data-count";
  var DECLARED_ATTR = "data-declared-rows";
  var HELD_ATTR = "data-held-rows";
  var ARIA_LABEL = "aria-label";
  var ARIA_SELECTED = "aria-selected";
  var TAB_ROLE = "tab";
  var TABLIST_ROLE = "tablist";

  var HOVER_STATE = "hover";
  var SELECTED_STATE = "selected";
  var TAB_SELECTOR = "QTabBar";

  var SET_EXCHANGE = "set_exchange";
  var SET_THEME = "set_theme";
  var SET_OPACITY = "set_opacity";
  var SET_MASKED = "set_masked";
  var TOGGLE_PRIVACY_MODE = "toggle_privacy_mode";
  var FINISH_DRAG = "finish_drag";
  var ANSWER_PANEL = "answer_panel";

  var LOCUST_CARDS = "locust_cards";
  var BOT_SYMBOLS = "bot_symbols";
  var SYMBOLS_PARAM = "symbols";
  var MASKED_PARAM = "masked";
  var ANY_MASKED = "any_masked";
  var WIRE_CANVAS_API = "acervatorWireCanvas";
  var WIRE_SHEET = "wire_sheet";
  var OVERLAY_STYLE = "overlay_style";
  var BOXES_PARAM = "boxes";
  var QUICK_ROUTING_API = "acervatorQuickRouting";
  var QUICK_ROUTING_METHOD = "quick_routing.state";
  var STEPS_PARAM = "steps";
  var REBUILD_STEP = "rebuild";
  var WIRE_OVERLAY_PART = "wire-overlay";
  var RELATIVE = "relative";
  var PANEL = "panel";
  var PANEL_WORDS = "panel_words";
  var PANEL_PART = "panel";
  var PANEL_TITLE_PART = "panel-title";
  var PANEL_BODY_PART = "panel-body";
  var PANEL_INPUT_PART = "panel-input";
  var PANEL_BUTTON_PART = "panel-button";
  var PANEL_ENTRY_PART = "panel-entry";
  var TITLE = "title";
  var PROMPT = "prompt";
  var ROW_LABEL = "row_label";
  var SUFFIX = "suffix";
  var BODY = "body";
  var ENTRIES = "entries";
  var MIN = "min";
  var MAX = "max";
  var VALUE = "value";
  var OK = "ok";
  var YES = "yes";
  var NO = "no";
  var CANCEL = "cancel";
  var CONFIG_WORD = "config";
  var CONFIRM_WORD = "confirm";
  var PICKER_WORD = "picker";
  var NUMBER_TYPE = "number";
  var DIALOG_ROLE = "dialog";
  var KIND_ATTR = "data-kind";
  var FUNCTION_KIND = "function";

  var ZERO = Number(EMPTY);
  var STEP = Number(true);

  var held = null;
  var swarmFaults = [];
  var loadFault = null;
  var asked = null;
  var dispatched = [];
  var roots = [];
  var dragFrom = EMPTY;

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

  // An empty tooltip stays off, so label writes no title attribute.
  function label(value) {
    return typeof value === "string" && value.length ? value : undefined;
  }

  function afterFirst(value, splitter) {
    var parts = String(value).split(splitter);
    parts.shift();
    return parts;
  }

  function carries(value, splitter) {
    return Boolean(afterFirst(value, splitter).length);
  }

  // variableFor asks acervatorWidgets for the one token carrying a value.
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

  function length(value) {
    return scaled(value, SPACE_GROUPS);
  }

  function widthOf(value) {
    return scaled(value, WIDTH_GROUPS);
  }

  // declarations asks acervatorHeader to read one Qt sheet.
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

  function hasSheetSource() {
    var api = global.acervatorHeader;
    return Boolean(api && typeof api.styleOf === "function");
  }

  // themeLabel asks acervatorVisualizerThemes for the word a theme shows.
  function themeLabel(key) {
    var api = global.acervatorVisualizerThemes;
    if (!api || typeof api.themeDisplayName !== "function") {
      return text(key);
    }
    var found = api.themeDisplayName(key);
    return found === undefined || found === null ? text(key) : String(found);
  }

  function hasThemeSource() {
    var api = global.acervatorVisualizerThemes;
    return Boolean(api && typeof api.themeDisplayName === "function");
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

  // The style a named Qt state paints, `:hover` and `:selected` alike.
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

  // The style one Qt selector paints, before any state rule is added.
  function selectorStyle(sheet, selector) {
    var found = {};
    stateRules(sheet).forEach(function (rule) {
      if (!carries(rule.selector, selector) || carries(rule.selector, COLON)) {
        return;
      }
      var painted = styleOf(rule.body);
      Object.keys(painted).forEach(function (name) {
        found[name] = painted[name];
      });
    });
    return found;
  }

  function merged(base, extra) {
    Object.keys(extra).forEach(function (name) {
      base[name] = extra[name];
    });
    return base;
  }

  // The surface publishes a margin in left, top, right, bottom order.
  var PADDING_SIDES = ["paddingLeft", "paddingTop", "paddingRight", "paddingBottom"];

  function marginStyle(model, field) {
    var style = {};
    var margins = listField(model, field);
    PADDING_SIDES.forEach(function (side, at) {
      if (at < margins.length) {
        style[side] = length(margins[at]);
      }
    });
    return style;
  }

  function boxStyle(model, marginField, spacingField, direction) {
    var style = marginStyle(model, marginField);
    style.display = FLEX;
    style.flexDirection = direction;
    if (isPlainObject(model) && owns(model, spacingField)) {
      style.gap = length(model[spacingField]);
    }
    return style;
  }

  // A Qt label clips its text and cannot be dragged over.
  function labelStyle(model, sheet) {
    var style = styleOf(sheet);
    style.userSelect = NONE;
    style.whiteSpace = model[LABEL_WORD_WRAP] === true ? PRE_WRAP : NOWRAP;
    style.overflow = HIDDEN;
    return style;
  }

  // The description labels are the two Qt sets wordWrap on.
  function descriptionStyle(model) {
    var style = styleOf(model[DESCRIPTION_STYLE_SHEET]);
    style.userSelect = NONE;
    style.whiteSpace = model[DESCRIPTION_WORD_WRAP] === true ? NORMAL : NOWRAP;
    return style;
  }

  function element() {
    return global.React.createElement.apply(null, arguments);
  }

  function hooks() {
    return global.React;
  }

  function dispatch(name, params) {
    dispatched.push({ action: name, params: params });
    if (!global.acervator || typeof global.acervator.call !== "function") {
      return null;
    }
    var sent = copyOf(params);
    sent.action = name;
    return global.acervator.call(METHOD, sent);
  }

  function actionName(model, name) {
    var found = objectField(model, ACTIONS);
    return owns(found, name) ? name : undefined;
  }

  function Caption(props) {
    var captionProps = {
      className: CELL_CLASS,
      style: { userSelect: NONE, whiteSpace: NOWRAP, flex: FLEX_NONE }
    };
    captionProps[PART_ATTR] = CAPTION_PART;
    captionProps[KEY_ATTR] = props.slot;
    return element(SPAN_TAG, captionProps, text(props.text));
  }

  function Stretch(props) {
    var spacerProps = { style: { flex: AUTO } };
    spacerProps[PART_ATTR] = STRETCH_PART;
    spacerProps[SLOT_ATTR] = props.slot;
    return element(DIV_TAG, spacerProps, null);
  }

  function cursorOf(name) {
    return owns(CURSOR_BY_NAME, name) ? CURSOR_BY_NAME[name] : undefined;
  }

  // One click on the dot flips the mask; dot_cursor names the cursor Qt paints.
  function PrivacyDot(props) {
    var model = props.model;
    var style = labelStyle(model, model[PRIVACY_DOT_STYLE_SHEET]);
    style.cursor = cursorOf(model[DOT_CURSOR]);
    style.flex = FLEX_NONE;
    var dotProps = {
      className: CELL_CLASS,
      style: style,
      title: label(model[PRIVACY_DOT_TOOLTIP]),
      onClick: function () {
        dispatch(SET_MASKED, {});
      }
    };
    dotProps[PART_ATTR] = PRIVACY_DOT_PART;
    dotProps[ACTION_ATTR] = text(actionName(model, SET_MASKED));
    dotProps[ARIA_LABEL] = label(model[PRIVACY_DOT_TOOLTIP]);
    return element(SPAN_TAG, dotProps, text(model[PRIVACY_GLYPH]));
  }

  function HoverButton(props) {
    var state = hooks().useState(false);
    var hovered = state.shift();
    var setHovered = state.shift();
    var style = styleOf(props.sheet);
    style.flex = FLEX_NONE;
    style.whiteSpace = NOWRAP;
    if (hovered === true) {
      merged(style, stateStyle(props.sheet, HOVER_STATE));
    }
    var buttonProps = {
      className: INPUT_CLASS,
      style: style,
      type: BUTTON_TYPE,
      title: label(props.tooltip),
      onMouseOver: function () {
        setHovered(true);
      },
      onMouseOut: function () {
        setHovered(false);
      },
      onClick: props.onPress
    };
    buttonProps[PART_ATTR] = props.part;
    buttonProps[SLOT_ATTR] = props.slot;
    buttonProps[ACTION_ATTR] = text(props.action);
    buttonProps[HOVERED_ATTR] = text(hovered);
    return element(BUTTON_TAG, buttonProps, text(props.text));
  }

  function Picker(props) {
    var style = { flex: FLEX_NONE };
    var pickerProps = {
      className: INPUT_CLASS,
      style: style,
      title: label(props.tooltip),
      value: props.value,
      onChange: props.onPick
    };
    pickerProps[PART_ATTR] = props.part;
    pickerProps[SLOT_ATTR] = props.slot;
    pickerProps[ACTION_ATTR] = text(props.action);
    pickerProps[ARIA_LABEL] = label(props.tooltip);
    var drawn = props.items.map(function (one, at) {
      var optionProps = { key: String(at), value: one.value };
      optionProps[INDEX_ATTR] = String(at);
      return element(OPTION_TAG, optionProps, text(one.label));
    });
    return element(SELECT_TAG, pickerProps, drawn);
  }

  function OpacitySlider(props) {
    var model = props.model;
    var sliderProps = {
      className: INPUT_CLASS,
      style: { flex: FLEX_NONE, width: widthOf(model[OPACITY_SLIDER_WIDTH]) },
      type: RANGE_TYPE,
      min: text(model[OPACITY_MIN_PCT]),
      max: text(model[OPACITY_MAX_PCT]),
      value: text(model[OPACITY_PCT]),
      title: label(model[OPACITY_TOOLTIP]),
      onChange: function (event) {
        dispatch(SET_OPACITY, { pct: Number(event.target.value) });
      }
    };
    sliderProps[PART_ATTR] = OPACITY_SLIDER_PART;
    sliderProps[ACTION_ATTR] = text(actionName(model, SET_OPACITY));
    sliderProps[ARIA_LABEL] = label(model[OPACITY_TOOLTIP]);
    return element(INPUT_TAG, sliderProps, null);
  }

  function exchangeItems(model) {
    return listField(model, EXCHANGE_ITEMS).map(function (pair) {
      var one = Array.isArray(pair) ? pair.slice() : [];
      var caption = one.shift();
      var value = one.shift();
      return { label: text(caption), value: text(value) };
    });
  }

  function themeItems(model) {
    return listField(model, THEME_KEYS).map(function (key) {
      return { label: themeLabel(key), value: text(key) };
    });
  }

  // Each locust's box in its page's own coordinates, keyed by bot id.
  function boxesIn(page) {
    var found = {};
    if (page === null) {
      return found;
    }
    var box = page.getBoundingClientRect();
    Array.prototype.forEach.call(
      page.querySelectorAll('[data-part="' + LOCUST_PART + '"]'),
      function (node) {
        var one = node.getBoundingClientRect();
        found[node.getAttribute(KEY_ATTR)] = [
          one.left - box.left,
          one.top - box.top,
          one.width,
          one.height
        ];
      }
    );
    return found;
  }

  function askSurface(method, params) {
    if (!global.acervator || typeof global.acervator.call !== FUNCTION_KIND) {
      return Promise.resolve(null);
    }
    return global.acervator.call(method, params);
  }

  // WireOverlay measures the locust boxes, then draws the sheet the surface holds.
  function WireOverlay(props) {
    var model = props.model;
    var mount = hooks().useRef(null);
    var wires = listField(model, WIRES);
    var opacity = model[OPACITY_PCT];
    var sheet = objectField(model, WIRE_SHEET);
    var drawnFor = hooks().useRef(null);
    var stamp = JSON.stringify([wires, opacity, model[THEME_KEY]]);
    hooks().useEffect(function () {
      if (drawnFor.current === stamp || !wires.length) {
        return;
      }
      var page = mount.current === null ? null : mount.current.parentElement;
      var boxes = boxesIn(page);
      if (!Object.keys(boxes).length) {
        return;
      }
      drawnFor.current = stamp;
      var asked = {};
      asked[BOXES_PARAM] = boxes;
      dispatch(WIRE_SHEET, asked);
    });
    var api = global[WIRE_CANVAS_API];
    var overlayProps = { ref: mount, style: copyOf(objectField(model, OVERLAY_STYLE)) };
    overlayProps.style.pointerEvents = NONE;
    overlayProps[PART_ATTR] = WIRE_OVERLAY_PART;
    overlayProps[COUNT_ATTR] = String(wires.length);
    if (
      !wires.length ||
      !api ||
      typeof api.Sheet !== FUNCTION_KIND ||
      !owns(sheet, STYLE_SHEET)
    ) {
      return element(DIV_TAG, overlayProps, null);
    }
    return element(DIV_TAG, overlayProps, element(api.Sheet, { model: sheet }));
  }

  // QuickRouting draws the matrix module over the fleet the tab holds.
  function QuickRouting(props) {
    var model = props.model;
    var state = hooks().useState(null);
    var held = state.shift();
    var setHeld = state.shift();
    var ids = listField(model, BOT_IDS);
    hooks().useEffect(
      function () {
        var asked = {};
        asked[SYMBOLS_PARAM] = objectField(model, BOT_SYMBOLS);
        asked[MASKED_PARAM] = model[ANY_MASKED] === true;
        asked[STEPS_PARAM] = [[REBUILD_STEP, ids]];
        var live = true;
        askSurface(QUICK_ROUTING_METHOD, asked).then(function (answer) {
          if (live) {
            setHeld(answer);
          }
        });
        return function () {
          live = false;
        };
      },
      [
        JSON.stringify(ids),
        JSON.stringify(objectField(model, BOT_SYMBOLS)),
        model[ANY_MASKED] === true
      ]
    );
    var api = global[QUICK_ROUTING_API];
    if (!api || typeof api.Matrix !== FUNCTION_KIND || !isPlainObject(held)) {
      return null;
    }
    return element(api.Matrix, { model: held });
  }

  // The bot a pointer landed on, read off the nearest ancestor naming one.
  function botKeyAt(node) {
    var at = node;
    while (at) {
      if (typeof at.getAttribute === FUNCTION_KIND) {
        var part = at.getAttribute(PART_ATTR);
        if (part === LOCUST_PART) {
          return at.getAttribute(KEY_ATTR) || EMPTY;
        }
      }
      at = at.parentElement;
    }
    return EMPTY;
  }

  function dragProps(props) {
    props.onPointerDown = function (event) {
      dragFrom = botKeyAt(event.target);
    };
    props.onPointerUp = function (event) {
      var start = dragFrom;
      dragFrom = EMPTY;
      if (start) {
        dispatch(FINISH_DRAG, {
          source_id: start,
          target_id: botKeyAt(event.target)
        });
      }
    };
    return props;
  }

  function PanelButton(props) {
    var buttonProps = {
      className: INPUT_CLASS,
      style: { flex: FLEX_NONE },
      type: BUTTON_TYPE,
      onClick: props.onPress
    };
    buttonProps[PART_ATTR] = PANEL_BUTTON_PART;
    buttonProps[SLOT_ATTR] = props.slot;
    return element(BUTTON_TAG, buttonProps, text(props.text));
  }

  function ConfigPanel(props) {
    var panel = props.panel;
    var words = props.words;
    var state = hooks().useState(String(panel[VALUE]));
    var value = state.shift();
    var setValue = state.shift();
    var inputProps = {
      className: INPUT_CLASS,
      type: NUMBER_TYPE,
      min: text(panel[MIN]),
      max: text(panel[MAX]),
      value: value,
      onChange: function (event) {
        setValue(event.target.value);
      }
    };
    inputProps[PART_ATTR] = PANEL_INPUT_PART;
    inputProps[ARIA_LABEL] = label(panel[ROW_LABEL]);
    var promptProps = {};
    promptProps[PART_ATTR] = PANEL_BODY_PART;
    return element(
      DIV_TAG,
      { style: { display: FLEX, flexDirection: COLUMN } },
      element(DIV_TAG, promptProps, text(panel[PROMPT])),
      element(
        DIV_TAG,
        { style: { display: FLEX, flexDirection: ROW, alignItems: CENTER } },
        element(SPAN_TAG, { key: ROW_LABEL }, text(panel[ROW_LABEL])),
        element(INPUT_TAG, inputProps),
        element(SPAN_TAG, { key: SUFFIX }, text(panel[SUFFIX]))
      ),
      element(
        DIV_TAG,
        { style: { display: FLEX, flexDirection: ROW } },
        element(PanelButton, {
          key: OK,
          slot: words[OK],
          text: text(panel[OK]),
          onPress: function () {
            dispatch(ANSWER_PANEL, { choice: words[OK], pct: Number(value) });
          }
        }),
        element(PanelButton, {
          key: CANCEL,
          slot: words[CANCEL],
          text: text(panel[CANCEL]),
          onPress: function () {
            dispatch(ANSWER_PANEL, { choice: words[CANCEL] });
          }
        })
      )
    );
  }

  function ConfirmPanel(props) {
    var panel = props.panel;
    var words = props.words;
    var bodyProps = { style: { whiteSpace: PRE_WRAP } };
    bodyProps[PART_ATTR] = PANEL_BODY_PART;
    return element(
      DIV_TAG,
      { style: { display: FLEX, flexDirection: COLUMN } },
      element(DIV_TAG, bodyProps, text(panel[BODY])),
      element(
        DIV_TAG,
        { style: { display: FLEX, flexDirection: ROW } },
        element(PanelButton, {
          key: YES,
          slot: words[YES],
          text: text(panel[YES]),
          onPress: function () {
            dispatch(ANSWER_PANEL, { choice: words[YES] });
          }
        }),
        element(PanelButton, {
          key: CANCEL,
          slot: words[CANCEL],
          text: text(panel[NO]),
          onPress: function () {
            dispatch(ANSWER_PANEL, { choice: words[CANCEL] });
          }
        })
      )
    );
  }

  // A picker line with no data is a heading or a separator and does nothing.
  function PickerPanel(props) {
    var panel = props.panel;
    var words = props.words;
    var drawn = (Array.isArray(panel[ENTRIES]) ? panel[ENTRIES] : []).map(
      function (entry, at) {
        var one = Array.isArray(entry) ? entry.slice() : [];
        var caption = one.shift();
        var data = one.shift();
        var entryProps = {
          key: String(at),
          className: INPUT_CLASS,
          type: BUTTON_TYPE,
          disabled: !Array.isArray(data),
          onClick: function () {
            dispatch(ANSWER_PANEL, { choice: words[PICKER_WORD], entry: data });
          }
        };
        entryProps[PART_ATTR] = PANEL_ENTRY_PART;
        entryProps[INDEX_ATTR] = String(at);
        return element(BUTTON_TAG, entryProps, text(caption));
      }
    );
    drawn.push(
      element(PanelButton, {
        key: CANCEL,
        slot: words[CANCEL],
        text: text(panel[CANCEL]),
        onPress: function () {
          dispatch(ANSWER_PANEL, { choice: words[CANCEL] });
        }
      })
    );
    return element(
      DIV_TAG,
      { style: { display: FLEX, flexDirection: COLUMN } },
      drawn
    );
  }

  var PANEL_BODIES = {};
  PANEL_BODIES[CONFIG_WORD] = ConfigPanel;
  PANEL_BODIES[CONFIRM_WORD] = ConfirmPanel;
  PANEL_BODIES[PICKER_WORD] = PickerPanel;

  // The surface names each panel kind, so its own word chooses the body.
  function bodyFor(words, kind) {
    var found;
    Object.keys(PANEL_BODIES).forEach(function (name) {
      if (words[name] === kind) {
        found = PANEL_BODIES[name];
      }
    });
    return found;
  }

  // Panel draws nothing until a drag release asks the surface for one.
  function Panel(props) {
    var panel = props.model[PANEL];
    var words = objectField(props.model, PANEL_WORDS);
    if (!isPlainObject(panel)) {
      return null;
    }
    var Body = bodyFor(words, panel[KIND]);
    if (Body === undefined) {
      return null;
    }
    var panelProps = {
      className: TAB_CLASS,
      style: { display: FLEX, flexDirection: COLUMN, flex: FLEX_NONE },
      role: DIALOG_ROLE
    };
    panelProps[PART_ATTR] = PANEL_PART;
    panelProps[KIND_ATTR] = text(panel[KIND]);
    panelProps[ARIA_LABEL] = label(panel[TITLE]);
    var titleProps = {};
    titleProps[PART_ATTR] = PANEL_TITLE_PART;
    return element(
      DIV_TAG,
      panelProps,
      element(DIV_TAG, titleProps, text(panel[TITLE])),
      element(Body, { panel: panel, words: words })
    );
  }

  function HeaderRow(props) {
    var model = props.model;
    var style = boxStyle(model, NESTED_MARGINS, HEADER_SPACING, ROW);
    style.alignItems = CENTER;
    style.flex = FLEX_NONE;
    var rowProps = { className: TAB_CLASS, style: style };
    rowProps[PART_ATTR] = HEADER_ROW_PART;

    var titleProps = {
      className: CELL_CLASS,
      style: { userSelect: NONE, whiteSpace: NOWRAP, flex: FLEX_NONE }
    };
    titleProps[PART_ATTR] = HEADER_TITLE_PART;

    var hintProps = {
      className: CELL_CLASS,
      style: { userSelect: NONE, whiteSpace: PRE_WRAP, flex: FLEX_NONE }
    };
    hintProps[PART_ATTR] = HEADER_HINT_PART;

    return element(
      DIV_TAG,
      rowProps,
      element(SPAN_TAG, titleProps, text(model[HEADER_TITLE])),
      element(SPAN_TAG, hintProps, text(model[HEADER_HINT])),
      element(PrivacyDot, { key: PRIVACY_DOT_PART, model: model }),
      element(Stretch, { key: STRETCH_PART, slot: HEADER_ROW_PART }),
      element(HoverButton, {
        key: PRIVACY_MODE_PART,
        part: PRIVACY_MODE_PART,
        slot: HEADER_ROW_PART,
        sheet: model[PRIVACY_MODE_STYLE_SHEET],
        text: model[PRIVACY_MODE_TEXT],
        tooltip: model[PRIVACY_MODE_TOOLTIP],
        action: actionName(model, TOGGLE_PRIVACY_MODE),
        onPress: function () {
          dispatch(TOGGLE_PRIVACY_MODE, {});
        }
      }),
      element(Caption, {
        key: EXCHANGE_CAPTION,
        slot: EXCHANGE_CAPTION,
        text: model[EXCHANGE_CAPTION]
      }),
      element(Picker, {
        key: EXCHANGE_SELECT_PART,
        part: EXCHANGE_SELECT_PART,
        slot: EXCHANGE,
        items: exchangeItems(model),
        value: text(model[EXCHANGE]),
        tooltip: model[EXCHANGE_TOOLTIP],
        action: actionName(model, SET_EXCHANGE),
        onPick: function (event) {
          dispatch(SET_EXCHANGE, { exchange: event.target.value });
        }
      }),
      element(Caption, {
        key: THEME_CAPTION,
        slot: THEME_CAPTION,
        text: model[THEME_CAPTION]
      }),
      element(Picker, {
        key: THEME_SELECT_PART,
        part: THEME_SELECT_PART,
        slot: THEME_KEY,
        items: themeItems(model),
        value: text(model[THEME_KEY]),
        tooltip: undefined,
        action: actionName(model, SET_THEME),
        onPick: function (event) {
          dispatch(SET_THEME, { theme_key: event.target.value });
        }
      }),
      element(Caption, {
        key: WIRES_CAPTION,
        slot: WIRES_CAPTION,
        text: model[WIRES_CAPTION]
      }),
      element(OpacitySlider, { key: OPACITY_SLIDER_PART, model: model })
    );
  }

  // Locust marks one grid place as an empty host for a bot card.
  function Locust(props) {
    var cellProps = { style: { gridRow: props.row, gridColumn: props.column } };
    cellProps[PART_ATTR] = LOCUST_PART;
    cellProps[SLOT_ATTR] = LOCUST_PART;
    cellProps[KEY_ATTR] = props.botId;
    cellProps[ROW_ATTR] = String(props.row);
    cellProps[COLUMN_ATTR] = String(props.column);
    cellProps[INDEX_ATTR] = String(props.at);
    return element(DIV_TAG, cellProps, botCard(props.card));
  }

  // The locust the node module paints, or nothing while it has not loaded.
  function botCard(card) {
    var api = global.acervatorBotNode;
    if (!api || typeof api.Card !== FUNCTION_KIND || !isPlainObject(card)) {
      return null;
    }
    return element(api.Card, { model: card });
  }

  function GridPage(props) {
    var model = props.model;
    var cells = listField(model, GRID_CELLS);
    var style = marginStyle(model, GRID_MARGINS);
    style.display = GRID;
    style.gap = length(model[GRID_SPACING]);
    style.gridTemplateColumns =
      REPEAT_OPEN + String(model[GRID_COLS]) + REPEAT_TAIL;
    style.justifyContent = START;
    style.alignContent = START;
    style.flex = AUTO;
    var pageProps = { className: TAB_CLASS, style: style };
    pageProps[PART_ATTR] = GRID_PAGE_PART;
    pageProps[CURRENT_ATTR] = text(true);
    dragProps(pageProps);
    pageProps[DECLARED_ATTR] = String(listField(model, BOT_IDS).length);
    pageProps[HELD_ATTR] = String(cells.length);

    var drawn = cells.map(function (cell, at) {
      var one = Array.isArray(cell) ? cell.slice() : [];
      var botId = one.shift();
      var row = one.shift();
      var column = one.shift();
      return element(Locust, {
        key: String(botId),
        botId: text(botId),
        card: objectField(model, LOCUST_CARDS)[botId],
        row: Number(row) + STEP,
        column: Number(column) + STEP,
        at: at
      });
    });

    if (model[EMPTY_VISIBLE] === true) {
      var emptyStyle = labelStyle(model, model[EMPTY_STYLE_SHEET]);
      emptyStyle.gridColumn = SPAN_OPEN + String(model[GRID_COLS]);
      emptyStyle.textAlign = CENTER;
      var emptyProps = { key: EMPTY_PART, className: CELL_CLASS, style: emptyStyle };
      emptyProps[PART_ATTR] = EMPTY_PART;
      drawn.push(element(DIV_TAG, emptyProps, text(model[EMPTY_TEXT])));
    }

    var canvasProps = { key: WIRE_CANVAS_PART, style: { display: NONE } };
    canvasProps[PART_ATTR] = WIRE_CANVAS_PART;
    canvasProps[SLOT_ATTR] = WIRE_CANVAS_PART;
    canvasProps[COUNT_ATTR] = String(listField(model, WIRES).length);
    drawn.push(element(DIV_TAG, canvasProps, null));
    drawn.push(element(WireOverlay, { key: WIRE_OVERLAY_PART, model: model }));
    pageProps.style.position = RELATIVE;
    return element(DIV_TAG, pageProps, drawn);
  }

  function SwarmCell(props) {
    var model = props.model;
    var cell = isPlainObject(props.cell) ? props.cell : {};
    var style = labelStyle(model, cell[STYLE_SHEET]);
    style.width = widthOf(cell[WIDTH]);
    style.flex = FLEX_NONE;
    var cellProps = { className: CELL_CLASS, style: style };
    cellProps[PART_ATTR] = SWARM_CELL_PART;
    cellProps[COLUMN_ATTR] = props.name;
    cellProps[KEY_ATTR] = props.runId;
    cellProps[LAYER_ATTR] = props.layer;
    return element(SPAN_TAG, cellProps, text(cell[TEXT]));
  }

  // A column is a handle entry carrying both a text and a width.
  function columnNames(model, handle) {
    return listField(model, ROW_HANDLE_KEYS).filter(function (name) {
      var one = isPlainObject(handle) ? handle[name] : undefined;
      return isPlainObject(one) && owns(one, TEXT) && owns(one, WIDTH);
    });
  }

  function declaredColumnCount(model) {
    return Object.keys(objectField(model, COLUMN_WIDTHS)).length;
  }

  function SwarmRow(props) {
    var model = props.model;
    var handle = isPlainObject(props.handle) ? props.handle : {};
    var frame = objectField(handle, WIDGET);
    var style = styleOf(frame[STYLE_SHEET]);
    merged(style, boxStyle(frame, MARGINS, SPACING, ROW));
    style.alignItems = CENTER;
    style.flex = FLEX_NONE;
    var rowProps = { className: ROW_CLASS, style: style };
    rowProps[PART_ATTR] = SWARM_ROW_PART;
    rowProps[LAYER_ATTR] = props.layer;
    rowProps[KEY_ATTR] = props.runId;
    rowProps[INDEX_ATTR] = String(props.at);
    var drawn = columnNames(model, handle).map(function (name) {
      return element(SwarmCell, {
        key: name,
        name: name,
        cell: handle[name],
        model: model,
        runId: props.runId,
        layer: props.layer
      });
    });
    return element(DIV_TAG, rowProps, drawn);
  }

  function LayerSummary(props) {
    var model = props.model;
    var chrome = props.chrome;
    var lines = isPlainObject(props.lines) ? props.lines : {};
    var style = styleOf(chrome[SUMMARY_STYLE_SHEET]);
    merged(style, boxStyle(model, SUMMARY_MARGINS, SUMMARY_SPACING, ROW));
    style.alignItems = CENTER;
    style.flex = FLEX_NONE;
    var boxProps = { className: TAB_CLASS, style: style };
    boxProps[PART_ATTR] = SUMMARY_PART;
    boxProps[LAYER_ATTR] = props.layer;

    var titleStyle = { userSelect: NONE, whiteSpace: NOWRAP, flex: FLEX_NONE };
    var titleProps = {
      key: SUMMARY_TITLE_PART,
      className: CELL_CLASS,
      style: titleStyle
    };
    titleProps[PART_ATTR] = SUMMARY_TITLE_PART;
    titleProps[LAYER_ATTR] = props.layer;

    var order = listField(chrome, SUMMARY_ORDER);
    var drawn = [element(SPAN_TAG, titleProps, text(chrome[SUMMARY_TITLE]))];
    order.forEach(function (name) {
      var lineStyle = labelStyle(model, model[SUMMARY_LABEL_STYLE_SHEET]);
      lineStyle.flex = FLEX_NONE;
      var lineProps = { key: name, className: CELL_CLASS, style: lineStyle };
      lineProps[PART_ATTR] = SUMMARY_LINE_PART;
      lineProps[LAYER_ATTR] = props.layer;
      lineProps[COLUMN_ATTR] = name;
      drawn.push(element(SPAN_TAG, lineProps, text(lines[name])));
    });
    drawn.push(
      element(Stretch, { key: STRETCH_PART, slot: SUMMARY_PART })
    );
    return element(DIV_TAG, boxProps, drawn);
  }

  function LayerHeader(props) {
    var model = props.model;
    var chrome = props.chrome;
    var style = boxStyle(model, NESTED_MARGINS, LAYER_HEADER_SPACING, ROW);
    style.alignItems = CENTER;
    style.flex = FLEX_NONE;
    var headerProps = { className: TAB_CLASS, style: style };
    headerProps[PART_ATTR] = LAYER_HEADER_PART;
    headerProps[LAYER_ATTR] = props.layer;

    var headingStyle = labelStyle(model, chrome[HEADING_STYLE_SHEET]);
    headingStyle.flex = FLEX_NONE;
    var headingProps = {
      key: LAYER_HEADING_PART,
      className: CELL_CLASS,
      style: headingStyle
    };
    headingProps[PART_ATTR] = LAYER_HEADING_PART;
    headingProps[LAYER_ATTR] = props.layer;

    var drawn = [
      element(SPAN_TAG, headingProps, text(chrome[HEADING_TEXT])),
      element(Stretch, { key: STRETCH_PART, slot: LAYER_HEADER_PART })
    ];
    listField(chrome, BUTTONS).forEach(function (one, at) {
      var button = isPlainObject(one) ? one : {};
      drawn.push(
        element(HoverButton, {
          key: String(at),
          part: LAYER_BUTTON_PART,
          slot: props.layer,
          sheet: button[STYLE_SHEET],
          text: button[TEXT],
          tooltip: undefined,
          action: undefined,
          onPress: undefined
        })
      );
    });
    return element(DIV_TAG, headerProps, drawn);
  }

  function LayerPane(props) {
    var model = props.model;
    var chrome = objectField(objectField(model, LAYER_CHROME), props.layer);
    var order = listField(model, props.slot.order);
    var rows = objectField(model, props.slot.rows);
    var style = boxStyle(model, LAYER_MARGINS, LAYER_SPACING, COLUMN);
    style.flex = AUTO;
    style.overflow = HIDDEN;
    var paneProps = {
      className: TAB_CLASS,
      style: style,
      hidden: props.current !== true
    };
    paneProps[PART_ATTR] = LAYER_PANE_PART;
    paneProps[LAYER_ATTR] = props.layer;
    paneProps[CURRENT_ATTR] = text(props.current);
    paneProps[DECLARED_ATTR] = String(Object.keys(rows).length);
    paneProps[HELD_ATTR] = String(order.length);

    var descriptionProps = {
      key: LAYER_DESCRIPTION_PART,
      className: CELL_CLASS,
      style: descriptionStyle(model)
    };
    descriptionProps[PART_ATTR] = LAYER_DESCRIPTION_PART;
    descriptionProps[LAYER_ATTR] = props.layer;

    var scrollStyle = styleOf(model[SCROLL_STYLE_SHEET]);
    scrollStyle.flex = AUTO;
    scrollStyle.overflow = AUTO;
    var scrollProps = {
      key: LAYER_SCROLL_PART,
      className: TAB_CLASS,
      style: scrollStyle
    };
    scrollProps[PART_ATTR] = LAYER_SCROLL_PART;
    scrollProps[LAYER_ATTR] = props.layer;

    var listStyle = styleOf(model[LAYER_LIST_STYLE_SHEET]);
    merged(listStyle, boxStyle(model, LAYER_LIST_MARGINS, LAYER_LIST_SPACING, COLUMN));
    var listProps = { className: TAB_CLASS, style: listStyle };
    listProps[PART_ATTR] = LAYER_LIST_PART;
    listProps[LAYER_ATTR] = props.layer;

    var drawn = order.map(function (runId, at) {
      return element(SwarmRow, {
        key: String(runId),
        runId: text(runId),
        layer: props.layer,
        handle: rows[runId],
        model: model,
        at: at
      });
    });

    return element(
      DIV_TAG,
      paneProps,
      element(LayerHeader, {
        key: LAYER_HEADER_PART,
        model: model,
        chrome: chrome,
        layer: props.layer
      }),
      element(DIV_TAG, descriptionProps, text(chrome[DESCRIPTION_TEXT])),
      element(DIV_TAG, scrollProps, element(DIV_TAG, listProps, drawn)),
      element(LayerSummary, {
        key: SUMMARY_PART,
        model: model,
        chrome: chrome,
        layer: props.layer,
        lines: props.lines
      })
    );
  }

  // The live rows the surface builds, which the Qt tab never showed.
  function LiveRows(props) {
    var model = props.model;
    var order = listField(model, LIVE_ROW_ORDER);
    var rows = objectField(model, LIVE_ROWS);
    var style = boxStyle(model, LAYER_LIST_MARGINS, LAYER_LIST_SPACING, COLUMN);
    style.flex = FLEX_NONE;
    var liveProps = { className: TAB_CLASS, style: style };
    liveProps[PART_ATTR] = LIVE_ROWS_PART;
    liveProps[DECLARED_ATTR] = String(Object.keys(rows).length);
    liveProps[HELD_ATTR] = String(order.length);
    var drawn = order.map(function (runId, at) {
      return element(SwarmRow, {
        key: String(runId),
        runId: text(runId),
        layer: LIVE,
        handle: rows[runId],
        model: model,
        at: at
      });
    });
    return element(DIV_TAG, liveProps, drawn);
  }

  function SwarmPane(props) {
    var model = props.model;
    var style = boxStyle(model, VIZ_MARGINS, VIZ_SPACING, COLUMN);
    style.flex = AUTO;
    style.overflow = HIDDEN;
    var paneProps = {
      className: TAB_CLASS,
      style: style,
      hidden: props.current !== true
    };
    paneProps[PART_ATTR] = SWARM_PANE_PART;
    paneProps[CURRENT_ATTR] = text(props.current);

    var innerStyle = boxStyle(model, NESTED_MARGINS, INNER_SPACING, ROW);
    innerStyle.flex = AUTO;
    innerStyle.overflow = HIDDEN;
    var innerProps = { key: INNER_ROW_PART, className: TAB_CLASS, style: innerStyle };
    innerProps[PART_ATTR] = INNER_ROW_PART;

    var routingProps = { key: QUICK_ROUTING_PART, style: { flex: STEP } };
    routingProps[PART_ATTR] = QUICK_ROUTING_PART;
    routingProps[SLOT_ATTR] = QUICK_ROUTING_PART;
    var routingBody = element(QuickRouting, { model: model });

    return element(
      DIV_TAG,
      paneProps,
      element(HeaderRow, { key: HEADER_ROW_PART, model: model }),
      element(
        DIV_TAG,
        innerProps,
        element(GridPage, { key: GRID_PAGE_PART, model: model }),
        element(DIV_TAG, routingProps, routingBody)
      ),
      element(LiveRows, { key: LIVE_ROWS_PART, model: model })
    );
  }

  function TabButton(props) {
    var model = props.model;
    var sheet = model[TAB_STYLE_SHEET];
    var state = hooks().useState(false);
    var hovered = state.shift();
    var setHovered = state.shift();
    var style = selectorStyle(sheet, TAB_SELECTOR);
    if (props.current === true) {
      merged(style, stateStyle(sheet, SELECTED_STATE));
    }
    if (hovered === true) {
      merged(style, stateStyle(sheet, HOVER_STATE));
    }
    style.whiteSpace = NOWRAP;
    style.flex = FLEX_NONE;
    var buttonProps = {
      className: INPUT_CLASS,
      style: style,
      type: BUTTON_TYPE,
      role: TAB_ROLE,
      onMouseOver: function () {
        setHovered(true);
      },
      onMouseOut: function () {
        setHovered(false);
      },
      onClick: function () {
        props.onPick(props.at);
      }
    };
    buttonProps[PART_ATTR] = TAB_BUTTON_PART;
    buttonProps[INDEX_ATTR] = String(props.at);
    buttonProps[CURRENT_ATTR] = text(props.current);
    buttonProps[HOVERED_ATTR] = text(hovered);
    buttonProps[ARIA_SELECTED] = text(props.current);
    return element(BUTTON_TAG, buttonProps, text(props.title));
  }

  function Tab(props) {
    var model = isPlainObject(props.model) ? props.model : {};
    var state = hooks().useState(model[SWARM_TAB_INDEX]);
    var current = state.shift();
    var setCurrent = state.shift();
    var style = boxStyle(model, OUTER_MARGINS, OUTER_SPACING, COLUMN);
    style.overflow = HIDDEN;
    var tabProps = { className: TAB_CLASS, style: style };
    tabProps[PART_ATTR] = TAB_PART;
    tabProps[INDEX_ATTR] = text(current);

    var barStyle = { display: FLEX, flexDirection: ROW, flex: FLEX_NONE };
    var barProps = { key: TAB_BAR_PART, style: barStyle, role: TABLIST_ROLE };
    barProps[PART_ATTR] = TAB_BAR_PART;

    var bodyStyle = selectorStyle(model[TAB_STYLE_SHEET], TAB_WIDGET_SELECTOR);
    bodyStyle.display = FLEX;
    bodyStyle.flexDirection = COLUMN;
    bodyStyle.flex = AUTO;
    bodyStyle.overflow = HIDDEN;
    var bodyProps = { key: TAB_BODY_PART, style: bodyStyle };
    bodyProps[PART_ATTR] = TAB_BODY_PART;

    var titles = listField(model, TAB_TITLES).map(function (title, at) {
      return element(TabButton, {
        key: String(at),
        at: at,
        title: title,
        model: model,
        current: at === current,
        onPick: setCurrent
      });
    });

    return element(
      DIV_TAG,
      tabProps,
      element(DIV_TAG, barProps, titles),
      element(
        DIV_TAG,
        bodyProps,
        element(SwarmPane, {
          key: SWARM_PANE_PART,
          model: model,
          current: current === model[SWARM_TAB_INDEX]
        }),
        element(LayerPane, {
          key: SIM,
          model: model,
          layer: SIM,
          slot: LAYER_SLOTS[STEP],
          lines: objectField(model, SIM_SUMMARY),
          current: current === model[SIM_TAB_INDEX]
        }),
        element(LayerPane, {
          key: PAPER,
          model: model,
          layer: PAPER,
          slot: LAYER_SLOTS[STEP + STEP],
          lines: objectField(model, PAPER_SUMMARY),
          current: current === model[PAPER_TAB_INDEX]
        })
      ),
      element(Panel, { key: PANEL_PART, model: model })
    );
  }

  function checkFields(model) {
    DECLARED_FIELDS.forEach(function (name) {
      if (!owns(model, name)) {
        swarmFaults.push(fault(null, name, MISSING_FAULT, null));
        return;
      }
      if (model[name] === null) {
        swarmFaults.push(fault(null, name, NULL_FAULT, null));
      }
    });
  }

  // Every sheet the tab paints, refused where CSS reads it differently.
  function sheetsOf(model) {
    var found = [
      { where: null, sheet: model[TAB_STYLE_SHEET] },
      { where: null, sheet: model[EMPTY_STYLE_SHEET] },
      { where: null, sheet: model[PRIVACY_DOT_STYLE_SHEET] },
      { where: null, sheet: model[PRIVACY_MODE_STYLE_SHEET] },
      { where: null, sheet: model[DESCRIPTION_STYLE_SHEET] },
      { where: null, sheet: model[SCROLL_STYLE_SHEET] },
      { where: null, sheet: model[LAYER_LIST_STYLE_SHEET] },
      { where: null, sheet: model[SUMMARY_LABEL_STYLE_SHEET] }
    ];
    var chrome = objectField(model, LAYER_CHROME);
    Object.keys(chrome).forEach(function (layer) {
      var one = objectField(chrome, layer);
      found.push({ where: LAYER_AT + layer, sheet: one[HEADING_STYLE_SHEET] });
      found.push({ where: LAYER_AT + layer, sheet: one[SUMMARY_STYLE_SHEET] });
      listField(one, BUTTONS).forEach(function (button) {
        found.push({
          where: LAYER_AT + layer,
          sheet: isPlainObject(button) ? button[STYLE_SHEET] : undefined
        });
      });
    });
    LAYER_SLOTS.forEach(function (slot) {
      var rows = objectField(model, slot.rows);
      Object.keys(rows).forEach(function (runId) {
        var handle = objectField(rows, runId);
        found.push({
          where: ROW_AT + slot.key + SLASH + runId,
          sheet: objectField(handle, WIDGET)[STYLE_SHEET]
        });
        columnNames(model, handle).forEach(function (name) {
          found.push({
            where: ROW_AT + slot.key + SLASH + runId,
            sheet: handle[name][STYLE_SHEET]
          });
        });
      });
    });
    return found;
  }

  function checkColours(model) {
    sheetsOf(model).forEach(function (one) {
      declarations(one.sheet).forEach(function (declared) {
        var why = qtColour(declared.value);
        if (why !== undefined) {
          swarmFaults.push(fault(one.where, declared.property, QT_COLOUR_FAULT, why));
        }
      });
    });
  }

  // A row named in an order the tab has no handle for is never drawn.
  function checkRowOrder(model) {
    LAYER_SLOTS.forEach(function (slot) {
      var rows = objectField(model, slot.rows);
      var order = listField(model, slot.order);
      order.forEach(function (runId) {
        if (!owns(rows, String(runId))) {
          swarmFaults.push(
            fault(LAYER_AT + slot.key, slot.order, UNPLACED_FAULT, runId)
          );
        }
      });
      Object.keys(rows).forEach(function (runId) {
        var named = order.filter(function (one) {
          return String(one) === runId;
        });
        if (!named.length) {
          swarmFaults.push(
            fault(LAYER_AT + slot.key, slot.rows, UNPLACED_FAULT, runId)
          );
        }
      });
    });
  }

  function checkCells(model) {
    var declared = declaredColumnCount(model);
    LAYER_SLOTS.forEach(function (slot) {
      var rows = objectField(model, slot.rows);
      Object.keys(rows).forEach(function (runId) {
        var handle = objectField(rows, runId);
        var names = columnNames(model, handle);
        if (names.length !== declared) {
          swarmFaults.push(
            fault(
              ROW_AT + slot.key + SLASH + runId,
              COLUMN_WIDTHS,
              DISAGREES_FAULT,
              declared
            )
          );
        }
        listField(model, ROW_HANDLE_KEYS).forEach(function (name) {
          if (!owns(handle, name)) {
            swarmFaults.push(
              fault(ROW_AT + slot.key + SLASH + runId, name, MISSING_FAULT, null)
            );
            return;
          }
          if (!isPlainObject(handle[name])) {
            return;
          }
          var written = handle[name][TEXT];
          if (written !== undefined && typeof written === "object") {
            swarmFaults.push(
              fault(
                ROW_AT + slot.key + SLASH + runId,
                name,
                written === null ? NULL_FAULT : WRONG_TYPE_FAULT,
                kindOf(written)
              )
            );
          }
        });
      });
    });
  }

  // The grid places one cell per bot, so the two counts hold each other.
  function checkGrid(model) {
    var ids = listField(model, BOT_IDS);
    var cells = listField(model, GRID_CELLS);
    if (ids.length !== cells.length) {
      swarmFaults.push(fault(null, GRID_CELLS, DISAGREES_FAULT, ids.length));
    }
    cells.forEach(function (cell, at) {
      var one = Array.isArray(cell) ? cell : [];
      if (at < ids.length && String(one[ZERO]) !== String(ids[at])) {
        swarmFaults.push(fault(null, GRID_CELLS, DISAGREES_FAULT, ids[at]));
      }
    });
    if (owns(model, IS_EMPTY) && model[IS_EMPTY] !== (ids.length === ZERO)) {
      swarmFaults.push(fault(null, IS_EMPTY, DISAGREES_FAULT, ids.length));
    }
  }

  function checkSources() {
    if (!hasSheetSource()) {
      swarmFaults.push(fault(null, STYLE_SHEET, NO_SHEET_SOURCE_FAULT, null));
    }
    if (!hasThemeSource()) {
      swarmFaults.push(fault(null, THEME_KEYS, NO_THEME_SOURCE_FAULT, null));
    }
  }

  function heldFieldCount() {
    return DECLARED_FIELDS.filter(function (name) {
      return held !== null && owns(held.model, name);
    }).length;
  }

  function rowCounts(model, pick) {
    var total = ZERO;
    LAYER_SLOTS.forEach(function (slot) {
      total = total + pick(model, slot);
    });
    return total;
  }

  function drawnCellCount(model) {
    var total = ZERO;
    LAYER_SLOTS.forEach(function (slot) {
      var rows = objectField(model, slot.rows);
      listField(model, slot.order).forEach(function (runId) {
        total = total + columnNames(model, rows[runId]).length;
      });
    });
    return total;
  }

  function report() {
    var model = held.model;
    return {
      declared: {
        fields: DECLARED_FIELDS.length,
        rows: rowCounts(model, function (one, slot) {
          return Object.keys(objectField(one, slot.rows)).length;
        }),
        bots: listField(model, BOT_IDS).length,
        cells: declaredColumnCount(model) * rowCounts(model, function (one, slot) {
          return listField(one, slot.order).length;
        })
      },
      held: {
        fields: heldFieldCount(),
        rows: rowCounts(model, function (one, slot) {
          return listField(one, slot.order).length;
        }),
        bots: listField(model, GRID_CELLS).length,
        cells: drawnCellCount(model)
      },
      faults: swarmFaults.slice()
    };
  }

  function setBotSwarm(model) {
    dispatched = [];
    if (!isPlainObject(model)) {
      held = null;
      swarmFaults = [fault(null, null, NOT_AN_OBJECT_FAULT, kindOf(model))];
      return { declared: null, held: null, faults: swarmFaults.slice() };
    }
    held = { model: model };
    swarmFaults = [];
    checkFields(model);
    checkColours(model);
    checkRowOrder(model);
    checkCells(model);
    checkGrid(model);
    checkSources();
    return report();
  }

  // A failed load is not remembered, so a later ask reaches the bridge.
  function loadBotSwarm(params) {
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
        setBotSwarm(model);
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

  function layerNames() {
    return LAYER_SLOTS.map(function (slot) {
      return slot.key;
    });
  }

  function rowOrder(layer) {
    var named = LAYER_SLOTS.filter(function (slot) {
      return slot.key === layer;
    });
    return named.length ? list(named[ZERO].order) : [];
  }

  function rowsOf(layer) {
    var named = LAYER_SLOTS.filter(function (slot) {
      return slot.key === layer;
    });
    return named.length ? bag(named[ZERO].rows) : {};
  }

  function summaryOf(layer) {
    var chrome = objectField(bag(LAYER_CHROME), layer);
    return {
      order: listField(chrome, SUMMARY_ORDER).slice(),
      title: chrome[SUMMARY_TITLE]
    };
  }

  function actions() {
    return bag(ACTIONS);
  }

  function sent() {
    return dispatched.slice();
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
    return swarmFaults.slice();
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

  function renderTab(target, model) {
    var payload = model;
    if (!isPlainObject(payload)) {
      payload = held === null ? null : held.model;
    }
    return draw(target, element(Tab, { model: payload }));
  }

  function forget() {
    held = null;
    swarmFaults = [];
    loadFault = null;
    asked = null;
    dispatched = [];
  }

  // The shell draws this tab by its module name; the host reads that name
  // off the script tag running now, so it is written down nowhere.
  if (global.acervatorPanelHost) {
    global.acervatorPanelHost.register({
      method: METHOD,
      render: renderTab,
      load: loadBotSwarm,
      loadError: loadError
    });
  }

  global.acervatorSetBotSwarm = setBotSwarm;
  global.acervatorLoadBotSwarm = loadBotSwarm;
  global.acervatorBotSwarm = {
    method: METHOD,
    Tab: Tab,
    TabButton: TabButton,
    Panel: Panel,
    WireOverlay: WireOverlay,
    QuickRouting: QuickRouting,
    boxesIn: boxesIn,
    ConfigPanel: ConfigPanel,
    ConfirmPanel: ConfirmPanel,
    PickerPanel: PickerPanel,
    botKeyAt: botKeyAt,
    SwarmPane: SwarmPane,
    HeaderRow: HeaderRow,
    PrivacyDot: PrivacyDot,
    HoverButton: HoverButton,
    Picker: Picker,
    OpacitySlider: OpacitySlider,
    GridPage: GridPage,
    Locust: Locust,
    LayerPane: LayerPane,
    LayerHeader: LayerHeader,
    LayerSummary: LayerSummary,
    SwarmRow: SwarmRow,
    SwarmCell: SwarmCell,
    LiveRows: LiveRows,
    field: field,
    declaredNames: declaredNames,
    layerNames: layerNames,
    rowOrder: rowOrder,
    rowsOf: rowsOf,
    summaryOf: summaryOf,
    columnNames: function (layer, runId) {
      var found = rowsOf(layer);
      return held === null ? [] : columnNames(held.model, found[runId]);
    },
    columnCount: function () {
      return held === null ? ZERO : declaredColumnCount(held.model);
    },
    actions: actions,
    sent: sent,
    declarations: declarations,
    stateRules: stateRules,
    styleOf: styleOf,
    stateStyle: stateStyle,
    selectorStyle: selectorStyle,
    qtColour: qtColour,
    keptSheet: keptSheet,
    variableFor: variableFor,
    variableInGroups: variableInGroups,
    themeLabel: themeLabel,
    length: length,
    widthOf: widthOf,
    spaceGroups: function () {
      return SPACE_GROUPS.slice();
    },
    widthGroups: function () {
      return WIDTH_GROUPS.slice();
    },
    kinds: kinds,
    faults: faults,
    loadError: loadError,
    isLoaded: isLoaded,
    renderTab: renderTab,
    forget: forget
  };
})(window);
