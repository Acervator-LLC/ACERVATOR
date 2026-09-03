// The Live Bot Settings window shell, drawn into one global function.
(function (global) {
  "use strict";

  var METHOD = "bot_live_settings.state";

  var ACTIONS = "actions";
  var ANY_MODE = "any_mode";
  var APPLY_ENABLED = "apply_enabled";
  var APPLY_LABEL = "apply_label";
  var APPLY_STYLE = "apply_style";
  var CHANGES = "changes";
  var CHANGE_APPLIED_FORMAT = "change_applied_format";
  var CHANGE_APPLIED_STYLE = "change_applied_style";
  var CHANGE_EMPTY_TEXT = "change_empty_text";
  var CHANGE_FIELD_SEPARATOR = "change_field_separator";
  var CHANGE_LABEL = "change_label";
  var CHANGE_PENDING_FORMAT = "change_pending_format";
  var CHANGE_PENDING_STYLE = "change_pending_style";
  var CHANGE_STYLE = "change_style";
  var CLOSE_LABEL = "close_label";
  var CLOSE_STYLE = "close_style";
  var CURRENT_TAB = "current_tab";
  var FIRST_TAB_INDEX = "first_tab_index";
  var FORMS = "forms";
  var FORM_FIELD_GROWTH = "form_field_growth";
  var FORM_HORIZONTAL_SPACING_PX = "form_horizontal_spacing_px";
  var FORM_MARGINS_PX = "form_margins_px";
  var FORM_ROW_WRAP = "form_row_wrap";
  var FORM_VERTICAL_SPACING_PX = "form_vertical_spacing_px";
  var HEADER_LABEL = "header_label";
  var HEADER_STYLE = "header_style";
  var INSTALLED_BY_HOST = "installed_by_host";
  var INSTALLED_BY_WINDOW = "installed_by_window";
  var MINIMUM_H_PX = "minimum_h_px";
  var MINIMUM_SIZE_PX = "minimum_size_px";
  var MINIMUM_W_PX = "minimum_w_px";
  var NAV_SHOWN = "nav_shown";
  var NAV_SHOWN_ABOVE_SIBLINGS = "nav_shown_above_siblings";
  var NAV_STYLE = "nav_style";
  var NEXT_LABEL = "next_label";
  var NEXT_STEP = "next_step";
  var NEXT_TOOLTIP = "next_tooltip";
  var NO_TABS = "no_tabs";
  var OPENED_SIZE_PX = "opened_size_px";
  var PREV_LABEL = "prev_label";
  var PREV_STEP = "prev_step";
  var PREV_TOOLTIP = "prev_tooltip";
  var SCROLL_FRAME_SHAPE = "scroll_frame_shape";
  var SCROLL_RESIZABLE = "scroll_resizable";
  var SENT = "sent";
  var SHORTCUTS = "shortcuts";
  var SIBLINGS = "siblings";
  var STATE_COLORS = "state_colors";
  var STATE_LABEL = "state_label";
  var STATE_STYLE = "state_style";
  var TABS = "tabs";
  var TAB_BOT_SWARM = "tab_bot_swarm";
  var TAB_FOLD_TRANCHES = "tab_fold_tranches";
  var TAB_MARKET_INSPECTOR = "tab_market_inspector";
  var TAB_PHANTOM_BOTS = "tab_phantom_bots";
  var TAB_PLAN = "tab_plan";
  var TAB_POSITIONS_HELD = "tab_positions_held";
  var TAB_SETTINGS = "tab_settings";
  var TAB_STACK_TRANCHES = "tab_stack_tranches";
  var TAB_STATUS = "tab_status";
  var TITLE = "title";
  var WRAPPED_TABS = "wrapped_tabs";

  var PREV_CLICKED = "prev_clicked";
  var NEXT_CLICKED = "next_clicked";
  var APPLY_CLICKED = "apply_clicked";
  var CLOSE_CLICKED = "close_clicked";

  var DECLARED_FIELDS = [
    "accepted", ACTIONS, "age_days_format", "age_hours_format",
    "age_minutes_format", "age_seconds_format", ANY_MODE, "applied",
    "applied_entry_format", "applied_entry_separator", "applied_error_format",
    "applied_join", "applied_log", "applied_refused_format",
    "applied_synced_format", APPLY_ENABLED, "apply_enabled_at_start",
    APPLY_LABEL, APPLY_STYLE, "bot_id_short_length",
    "bot_manager_attribute", "bus_topics", "call_names", "calls",
    CHANGE_APPLIED_FORMAT, CHANGE_APPLIED_STYLE, CHANGE_EMPTY_TEXT,
    CHANGE_FIELD_SEPARATOR, CHANGE_LABEL, CHANGE_PENDING_FORMAT,
    CHANGE_PENDING_STYLE, CHANGE_STYLE, CHANGES, CLOSE_LABEL,
    CLOSE_STYLE, "coordinator_attribute", "coordinator_lock_attribute",
    CURRENT_TAB, FIRST_TAB_INDEX, "fold_sort_key", "fold_sort_queue_order",
    FORM_FIELD_GROWTH, FORM_HORIZONTAL_SPACING_PX, FORM_MARGINS_PX,
    FORM_ROW_WRAP, FORM_VERTICAL_SPACING_PX, FORMS, "header_color",
    "header_format", HEADER_LABEL, HEADER_STYLE, "header_style_format",
    INSTALLED_BY_HOST, INSTALLED_BY_WINDOW, "logged", "logger_name",
    "method", MINIMUM_H_PX, MINIMUM_SIZE_PX, MINIMUM_W_PX,
    "mode_extractor", "mode_scrumming", "nav_needs_siblings", NAV_SHOWN,
    NAV_SHOWN_ABOVE_SIBLINGS, NAV_STYLE, NEXT_LABEL, NEXT_STEP,
    NEXT_TOOLTIP, "no_changes", "no_manager_reason", "no_navigation",
    "no_siblings", NO_TABS, OPENED_SIZE_PX, "pending_navigate_to",
    "phantom_applied_key", "phantom_caveat_log", "phantom_caveats_key",
    "phantom_enable_attribute", "phantom_enable_field", "phantom_failed_log",
    "phantom_fields", "phantom_lock_field", "phantom_timeframes_attribute",
    "phantom_timeframes_field", "phantom_update_method", PREV_LABEL,
    PREV_STEP, PREV_TOOLTIP, "route_applied_key", "route_raised_log",
    "route_reason_key", "route_refused_log", "route_unknown_reason",
    "runtime_routed", "save_failed_format", "save_failed_log", "save_method",
    "saved_reason", "screen_margin_h_px", "screen_margin_w_px",
    SCROLL_FRAME_SHAPE, SCROLL_RESIZABLE, "seconds_per_day",
    "seconds_per_hour", "seconds_per_minute", SENT, "shortcut_failed_log",
    "shortcut_plan", SHORTCUTS, SIBLINGS, "signal_name", "skin",
    STATE_COLORS, "state_cooldown", "state_error", "state_idle",
    STATE_LABEL, "state_label_format", "state_paused", "state_running",
    "state_stopped", STATE_STYLE, "state_style_format", "state_unknown_bg",
    "state_unknown_fg", "style_sheet", TAB_BOT_SWARM, TAB_FOLD_TRANCHES,
    TAB_MARKET_INSPECTOR, TAB_PHANTOM_BOTS, TAB_PLAN,
    TAB_POSITIONS_HELD, TAB_SETTINGS, TAB_STACK_TRANCHES, TAB_STATUS,
    TABS, "timer_delays_ms", "timers", TITLE, "title_format",
    WRAPPED_TABS
  ];

  var DECLARED_BAGS = [ACTIONS, CHANGES, "runtime_routed", "skin", STATE_COLORS, "timers"];

  var DECLARED_LISTS = [
    "applied", "bus_topics", "call_names", "calls", FORM_MARGINS_PX, FORMS,
    "logged", MINIMUM_SIZE_PX, "no_siblings", OPENED_SIZE_PX,
    "phantom_fields", SENT, "shortcut_plan", SHORTCUTS, SIBLINGS,
    TAB_PLAN, TABS, "timer_delays_ms", WRAPPED_TABS
  ];

  // Every word this shell draws, refused as markup before React draws it.
  var WORD_FIELDS = [
    TITLE, HEADER_LABEL, STATE_LABEL, CHANGE_LABEL, PREV_LABEL, NEXT_LABEL,
    APPLY_LABEL, CLOSE_LABEL, PREV_TOOLTIP, NEXT_TOOLTIP
  ];

  // Every Qt sheet this shell paints, named by the field it arrived in.
  var SHEET_FIELDS = [HEADER_STYLE, STATE_STYLE, NAV_STYLE, APPLY_STYLE, CLOSE_STYLE, CHANGE_STYLE];

  var MISSING_FAULT = "missing";
  var NULL_FAULT = "null";
  var NOT_AN_OBJECT_FAULT = "not-an-object";
  var NOT_A_LIST_FAULT = "not-a-list";
  var NOT_PLAIN_FAULT = "not-plain";
  var WRONG_TYPE_FAULT = "wrong-type";
  var QT_COLOUR_FAULT = "qt-colour";
  var MARKUP_FAULT = "markup";
  var DISAGREES_FAULT = "disagrees";
  var UNPLACED_FAULT = "unplaced";

  // Two fields the surface leaves empty until a step is staged.
  var NULLABLE_FIELDS = ["no_navigation", "pending_navigate_to"];

  var COLOUR_PROPERTY = "color";
  var FILL_PROPERTY = "background";

  var TAB_AT = "tab:";
  var FORM_AT = "form:";
  var SENT_AT = "sent:";
  var PATH_SPLIT = ".";
  var EMPTY = "";
  var GAP = " ";
  var SEMICOLON = ";";
  var COLON = ":";
  var COMMA = ",";
  var HASH = "#";
  var DOT = ".";
  var PERCENT = "%";
  var CLOSE = ")";
  var BRACE_OPEN = "{";
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
  // The largest value one hex byte holds, which is the alpha scale Qt counts in.
  var HEX_PREFIX = "0x";
  var HEX_BYTE_MAX = "ff";
  var ALPHA_SCALE = Number(HEX_PREFIX + HEX_BYTE_MAX);
  // A markup tag a rich-text QLabel reads as formatting rather than words.
  var MARKUP_OPEN = "<";

  // Only these token groups carry a value a CSS length may borrow.
  var LENGTH_GROUPS = ["spacing", "radii", "target_sizes", "table_columns", "focus"];
  var NO_BRIDGE = "the preload bridge is not present";

  var ROW = "row";
  var COLUMN = "column";
  var FLEX = "flex";
  var FLEX_NONE = "none";
  var HIDDEN = "hidden";
  var AUTO = "auto";
  var CENTER = "center";
  var NOWRAP = "nowrap";
  var ELLIPSIS = "ellipsis";
  var BUTTON_TYPE = "button";
  var DIV_TAG = "div";
  var SPAN_TAG = "span";
  var BUTTON_TAG = "button";
  var ARROW_LEFT = "ArrowLeft";
  var ARROW_RIGHT = "ArrowRight";

  var WINDOW_CLASS = "acervator-bot-live-settings";

  var WINDOW_PART = "bot-live-settings";
  var HEADER_ROW_PART = "header-row";
  var HEADER_LABEL_PART = "header-label";
  var STATE_BADGE_PART = "state-badge";
  var HEADER_STRETCH_PART = "header-stretch";
  var PREV_BUTTON_PART = "prev-button";
  var NEXT_BUTTON_PART = "next-button";
  var TAB_BAR_PART = "tab-bar";
  var TAB_BUTTON_PART = "tab-button";
  var TAB_PAGES_PART = "tab-pages";
  var FOOTER_ROW_PART = "footer-row";
  var FOOTER_STRETCH_PART = "footer-stretch";
  var APPLY_BUTTON_PART = "apply-button";
  var CLOSE_BUTTON_PART = "close-button";
  var CHANGE_LABEL_PART = "change-label";

  var STATUS_PAGE_PART = "status-page";
  var SETTINGS_PAGE_PART = "settings-page";
  var FOLD_TRANCHES_PAGE_PART = "fold-tranches-page";
  var STACK_TRANCHES_PAGE_PART = "stack-tranches-page";
  var BOT_SWARM_PAGE_PART = "bot-swarm-page";
  var MARKET_INSPECTOR_PAGE_PART = "market-inspector-page";
  var PHANTOM_BOTS_PAGE_PART = "phantom-bots-page";
  var POSITIONS_HELD_PAGE_PART = "positions-held-page";

  // One row per tab: the field naming it, the space it keeps, its own unit.
  var PAGE_PLAN = [
    [TAB_STATUS, STATUS_PAGE_PART, "live_status_tab_surface"],
    [TAB_SETTINGS, SETTINGS_PAGE_PART, "live_settings_tab_surface"],
    [TAB_FOLD_TRANCHES, FOLD_TRANCHES_PAGE_PART, "fold_tranches_tab_surface"],
    [TAB_STACK_TRANCHES, STACK_TRANCHES_PAGE_PART, "stack_tranches_tab_surface"],
    [TAB_BOT_SWARM, BOT_SWARM_PAGE_PART, "bot_swarm_tab_surface"],
    [TAB_MARKET_INSPECTOR, MARKET_INSPECTOR_PAGE_PART, "market_inspector_tab_surface"],
    [TAB_PHANTOM_BOTS, PHANTOM_BOTS_PAGE_PART, "phantom_bots_tab_surface"],
    [TAB_POSITIONS_HELD, POSITIONS_HELD_PAGE_PART, "positions_held_surface"]
  ];

  // fold_chrome and fold_tokens dress the rows the Fold Tranches unit draws.
  var FOLD_ALSO = "fold_chrome_surface fold_tokens_surface";

  var PART_ATTR = "data-part";
  var SLOT_ATTR = "data-slot";
  var KEY_ATTR = "data-key";
  var ACTION_ATTR = "data-action";
  var INDEX_ATTR = "data-index";
  var STEP_ATTR = "data-step";
  var CURRENT_ATTR = "data-current";
  var VISIBLE_ATTR = "data-visible";
  var ENABLED_ATTR = "data-enabled";
  var HOVERED_ATTR = "data-hovered";
  var WRAPPED_ATTR = "data-wrapped";
  var INSTALLED_ATTR = "data-installed";
  var FILLS_ATTR = "data-fills";
  var ALSO_ATTR = "data-also";
  var COUNT_ATTR = "data-count";
  var ARIA_LABEL = "aria-label";
  var ARIA_DISABLED = "aria-disabled";

  var NAVIGATE_PARAM = "navigate";
  var APPLY_PARAM = "apply";

  var HOVER_STATE = "hover";
  var DISABLED_STATE = "disabled";

  var ZERO = Number(EMPTY);
  var STEP = Number(true);

  var held = null;
  var windowFaults = [];
  var loadFault = null;
  var asked = null;
  var dispatched = [];
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

  // An undefined value leaves the attribute off rather than writing text.
  function text(value) {
    return value === null || value === undefined ? undefined : String(value);
  }

  // An empty label value stays off, so no title attribute is written.
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

  function opensWith(value, head) {
    return (
      Boolean(String(head).length) &&
      carries(value, head) &&
      String(value).split(head).shift() === EMPTY
    );
  }

  function numberOr(value, fallback) {
    return typeof value === "number" && value === value ? value : fallback;
  }

  // acervatorWidgets owns the one-carrier rule that names one variable.
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

  function variableInGroups(value, groups) {
    var name = variableFor(value);
    if (name === undefined || !inGroups(name, groups)) {
      return undefined;
    }
    return name;
  }

  // A token holds a bare number, so `calc` scales that value to a length.
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
    return scaled(value, LENGTH_GROUPS);
  }

  // The reciprocal of the alpha scale, so a fraction needs no division.
  var ALPHA_RECIPROCAL = Math.pow(ALPHA_SCALE, ZERO - STEP);

  // The fraction CSS wants from an alpha Qt counted in whole bytes.
  function alphaFraction(bytes) {
    return numberOr(bytes, ZERO) * ALPHA_RECIPROCAL;
  }

  // The alpha fraction CSS reads from the trailing byte of an eight-digit colour.
  function alphaOf(value) {
    var word = hexWord(value);
    if (word.length !== HEX_ARGB.length) {
      return undefined;
    }
    var digits = word.split(EMPTY);
    var low = digits.pop();
    var high = digits.pop();
    return alphaFraction(Number(HEX_PREFIX + high + low));
  }

  // `header_strip.js` owns the sheet parser and the camel-case rule.
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

  // The first hex word of one value, empty when the value carries none.
  function hexWord(value) {
    var parts = afterFirst(value, HASH);
    if (!parts.length) {
      return EMPTY;
    }
    return String(parts.shift()).trim().split(GAP).shift();
  }

  // A three and a six digit colour, whose lengths the reading below measures.
  var HEX_SHORT = "rgb";
  var HEX_LONG = "rrggbb";
  var CHANNEL_WIDTH = HEX_BYTE_MAX.length;

  // The three channels one written colour carries, hex or rgba alike.
  function channelsOf(value) {
    var word = hexWord(value);
    if (word.length === HEX_SHORT.length) {
      word = word
        .split(EMPTY)
        .map(function (one) {
          return one + one;
        })
        .join(EMPTY);
    }
    if (word.length >= HEX_LONG.length) {
      var digits = [];
      var at = ZERO;
      while (digits.length * CHANNEL_WIDTH < HEX_LONG.length) {
        digits.push(Number(HEX_PREFIX + word.slice(at, at + CHANNEL_WIDTH)));
        at = at + CHANNEL_WIDTH;
      }
      return digits;
    }
    var parts = afterFirst(value, RGBA_OPEN);
    if (!parts.length) {
      return undefined;
    }
    var fields = String(parts.shift()).split(CLOSE).shift().split(COMMA);
    if (fields.length <= HEX_SHORT.length) {
      return undefined;
    }
    var numbers = [];
    fields.slice(ZERO, HEX_SHORT.length).forEach(function (one) {
      numbers.push(Number(String(one).trim()));
    });
    return numbers;
  }

  // Whether two written colours carry the same three channels.
  function sameChannels(one, other) {
    var here = channelsOf(one);
    var there = channelsOf(other);
    if (here === undefined || there === undefined) {
      return false;
    }
    return here.join(COMMA) === there.join(COMMA);
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
    return hexWord(value).length === HEX_ARGB.length ? HEX_ARGB : undefined;
  }

  // One Qt rgba rewritten so a browser paints the alpha Qt painted.
  function cssValue(value) {
    if (!byteAlpha(value)) {
      return value;
    }
    var written = String(value);
    var rest = afterFirst(written, RGBA_OPEN).join(RGBA_OPEN);
    var fields = rest.split(CLOSE).shift().split(COMMA);
    var alpha = fields.pop();
    var head = [];
    fields.forEach(function (one) {
      head.push(String(one).trim());
    });
    head.push(String(alphaFraction(Number(String(alpha).trim()))));
    return (
      written.split(RGBA_OPEN).shift() +
      RGBA_OPEN +
      head.join(COMMA) +
      CLOSE +
      afterFirst(rest, CLOSE).join(CLOSE)
    );
  }

  // The sheet without the declarations CSS would read as another colour.
  function keptSheet(sheet) {
    var kept = [];
    declarations(sheet).forEach(function (one) {
      if (qtColour(one.value) === undefined) {
        kept.push(one.property + COLON + cssValue(one.value));
      }
    });
    return kept.join(SEMICOLON);
  }

  function styleOf(sheet) {
    return headerStyleOf(keptSheet(sheet));
  }

  // The style one named Qt state paints, `:hover` and `:disabled` alike.
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

  function merged(base, extra) {
    Object.keys(extra).forEach(function (name) {
      base[name] = extra[name];
    });
    return base;
  }

  function element() {
    return global.React.createElement.apply(null, arguments);
  }

  function hooks() {
    return global.React;
  }

  function hasBridge() {
    return Boolean(global.acervator) && typeof global.acervator.call === "function";
  }

  function dispatch(name, params) {
    dispatched.push({ action: name, params: params });
    if (!hasBridge()) {
      return null;
    }
    return global.acervator.call(METHOD, copyOf(params));
  }

  function heldModel() {
    return held === null ? {} : held.model;
  }

  function actionNamed(model, name) {
    return objectField(model, ACTIONS)[name];
  }

  function navigate(step) {
    var model = heldModel();
    var params = {};
    params[NAVIGATE_PARAM] = step;
    var name = step === model[NEXT_STEP] ? NEXT_CLICKED : PREV_CLICKED;
    return dispatch(actionNamed(model, name), params);
  }

  function navigatePrev() {
    return navigate(heldModel()[PREV_STEP]);
  }

  function navigateNext() {
    return navigate(heldModel()[NEXT_STEP]);
  }

  function applyChanges() {
    var model = heldModel();
    var params = {};
    params[APPLY_PARAM] = true;
    return dispatch(actionNamed(model, APPLY_CLICKED), params);
  }

  // `view_model` reads no close parameter, so the ask carries its name alone.
  function closeWindow() {
    return dispatch(actionNamed(heldModel(), CLOSE_CLICKED), {});
  }

  // The steps the two arrow keys walk, taken from the shortcuts the window kept.
  function shortcutSteps() {
    return listField(heldModel(), SHORTCUTS).map(function (pair) {
      return Array.isArray(pair) ? pair.slice().pop() : undefined;
    });
  }

  function stepIsBound(step) {
    return Boolean(
      shortcutSteps().filter(function (one) {
        return one === step;
      }).length
    );
  }

  function pressKey(key, withModifier) {
    var model = heldModel();
    if (withModifier !== true) {
      return null;
    }
    if (key === ARROW_LEFT && stepIsBound(model[PREV_STEP])) {
      return navigate(model[PREV_STEP]);
    }
    if (key === ARROW_RIGHT && stepIsBound(model[NEXT_STEP])) {
      return navigate(model[NEXT_STEP]);
    }
    return null;
  }

  // The head the pending line opens with, taken from the surface's own format.
  function pendingHead(model) {
    return String(model[CHANGE_PENDING_FORMAT]).split(BRACE_OPEN).shift();
  }

  // The edited field names in the order the change line draws them.
  function changeFields(model) {
    var line = model[CHANGE_LABEL];
    var head = pendingHead(model);
    if (typeof line !== "string" || !opensWith(line, head)) {
      return [];
    }
    var parts = String(line).split(head);
    parts.shift();
    var tail = parts.join(head);
    if (!tail.length) {
      return [];
    }
    return tail.split(String(model[CHANGE_FIELD_SEPARATOR]));
  }

  // The space one tab name keeps, matched by name and never by position.
  function pageFor(model, name) {
    var found = PAGE_PLAN.filter(function (row) {
      return model[row.slice().shift()] === name;
    });
    var row = found.shift();
    if (row === undefined) {
      return undefined;
    }
    var one = row.slice();
    var field = one.shift();
    return { field: field, part: one.shift(), fills: one.shift() };
  }

  function planFor(model, name) {
    var found = listField(model, TAB_PLAN).filter(function (row) {
      return Array.isArray(row) && row.slice().shift() === name;
    });
    var row = found.shift();
    if (!Array.isArray(row)) {
      return {};
    }
    var one = row.slice();
    one.shift();
    return { mode: one.shift(), wrapped: one.shift(), installed: one.shift() };
  }

  function drawnTabs(model) {
    return listField(model, TABS).filter(function (name) {
      return pageFor(model, name) !== undefined;
    });
  }

  function emptySpaces() {
    return PAGE_PLAN.map(function (row) {
      var one = row.slice();
      one.shift();
      return one.shift();
    });
  }

  function currentTab(model) {
    return numberOr(model[CURRENT_TAB], numberOr(model[FIRST_TAB_INDEX], ZERO));
  }

  function HoverButton(props) {
    var state = hooks().useState(false);
    var hovered = state.shift();
    var setHovered = state.shift();
    var style = styleOf(props.sheet);
    style.flex = FLEX_NONE;
    style.whiteSpace = NOWRAP;
    if (props.enabled === false) {
      merged(style, stateStyle(props.sheet, DISABLED_STATE));
    } else if (hovered === true) {
      merged(style, stateStyle(props.sheet, HOVER_STATE));
    }
    var buttonProps = {
      className: WINDOW_CLASS,
      style: style,
      type: BUTTON_TYPE,
      title: label(props.tooltip),
      hidden: props.visible === false,
      disabled: props.enabled === false,
      onMouseOver: function () {
        setHovered(true);
      },
      onMouseOut: function () {
        setHovered(false);
      },
      onClick: props.onPress
    };
    buttonProps[PART_ATTR] = props.part;
    buttonProps[ACTION_ATTR] = text(props.action);
    buttonProps[STEP_ATTR] = text(props.step);
    buttonProps[VISIBLE_ATTR] = text(props.visible);
    buttonProps[ENABLED_ATTR] = text(props.enabled);
    buttonProps[HOVERED_ATTR] = text(hovered);
    buttonProps[ARIA_LABEL] = label(props.tooltip);
    buttonProps[ARIA_DISABLED] = text(props.enabled === false);
    return element(BUTTON_TAG, buttonProps, text(props.words));
  }

  // A Qt label clips its own text where the row it sits in is squeezed.
  function Caption(props) {
    var style = styleOf(props.sheet);
    style.whiteSpace = NOWRAP;
    style.overflow = HIDDEN;
    style.textOverflow = ELLIPSIS;
    style.flexGrow = ZERO;
    style.flexShrink = STEP;
    style.flexBasis = AUTO;
    style.minWidth = ZERO;
    var captionProps = { className: WINDOW_CLASS, style: style };
    captionProps[PART_ATTR] = props.part;
    captionProps[SLOT_ATTR] = props.slot;
    return element(SPAN_TAG, captionProps, text(props.words));
  }

  function Stretch(props) {
    var spacerProps = { style: { flex: AUTO } };
    spacerProps[PART_ATTR] = props.part;
    return element(DIV_TAG, spacerProps, null);
  }

  function HeaderRow(props) {
    var model = props.model;
    var shown = model[NAV_SHOWN] === true;
    var rowProps = {
      className: WINDOW_CLASS,
      style: {
        display: FLEX,
        flexDirection: ROW,
        alignItems: CENTER,
        flex: FLEX_NONE,
        minWidth: ZERO,
        overflow: HIDDEN
      }
    };
    rowProps[PART_ATTR] = HEADER_ROW_PART;
    return element(
      DIV_TAG,
      rowProps,
      element(Caption, {
        key: HEADER_LABEL_PART,
        part: HEADER_LABEL_PART,
        slot: HEADER_LABEL,
        sheet: model[HEADER_STYLE],
        words: model[HEADER_LABEL]
      }),
      element(Caption, {
        key: STATE_BADGE_PART,
        part: STATE_BADGE_PART,
        slot: STATE_LABEL,
        sheet: model[STATE_STYLE],
        words: model[STATE_LABEL]
      }),
      element(Stretch, { key: HEADER_STRETCH_PART, part: HEADER_STRETCH_PART }),
      element(HoverButton, {
        key: PREV_BUTTON_PART,
        part: PREV_BUTTON_PART,
        sheet: model[NAV_STYLE],
        words: model[PREV_LABEL],
        tooltip: model[PREV_TOOLTIP],
        action: actionNamed(model, PREV_CLICKED),
        step: model[PREV_STEP],
        visible: shown,
        onPress: navigatePrev
      }),
      element(HoverButton, {
        key: NEXT_BUTTON_PART,
        part: NEXT_BUTTON_PART,
        sheet: model[NAV_STYLE],
        words: model[NEXT_LABEL],
        tooltip: model[NEXT_TOOLTIP],
        action: actionNamed(model, NEXT_CLICKED),
        step: model[NEXT_STEP],
        visible: shown,
        onPress: navigateNext
      })
    );
  }

  function TabBar(props) {
    var model = props.model;
    var names = drawnTabs(model);
    var barProps = {
      className: WINDOW_CLASS,
      style: { display: FLEX, flexDirection: ROW, flex: FLEX_NONE, overflow: HIDDEN }
    };
    barProps[PART_ATTR] = TAB_BAR_PART;
    barProps[COUNT_ATTR] = String(names.length);
    var drawn = names.map(function (name, at) {
      var current = at === props.at;
      var tabProps = {
        key: String(at),
        className: WINDOW_CLASS,
        style: { flex: FLEX_NONE, whiteSpace: NOWRAP },
        type: BUTTON_TYPE,
        onClick: function () {
          props.onPick(at);
        }
      };
      tabProps[PART_ATTR] = TAB_BUTTON_PART;
      tabProps[KEY_ATTR] = text(name);
      tabProps[INDEX_ATTR] = String(at);
      tabProps[CURRENT_ATTR] = text(current);
      return element(BUTTON_TAG, tabProps, text(name));
    });
    return element(DIV_TAG, barProps, drawn);
  }

  // One named space per tab, kept empty for the unit that draws that tab.
  function TabPage(props) {
    var plan = props.plan;
    var wrapped = plan.wrapped === props.model[SCROLL_RESIZABLE];
    var style = {
      display: FLEX,
      flexDirection: COLUMN,
      flex: AUTO,
      minHeight: ZERO,
      overflow: wrapped ? AUTO : HIDDEN
    };
    var pageProps = { className: WINDOW_CLASS, style: style, hidden: props.current !== true };
    pageProps[PART_ATTR] = props.page.part;
    pageProps[SLOT_ATTR] = props.page.part;
    pageProps[KEY_ATTR] = text(props.name);
    pageProps[INDEX_ATTR] = String(props.at);
    pageProps[CURRENT_ATTR] = text(props.current);
    pageProps[WRAPPED_ATTR] = text(plan.wrapped);
    pageProps[INSTALLED_ATTR] = text(plan.installed);
    pageProps[FILLS_ATTR] = text(props.page.fills);
    if (props.page.field === TAB_FOLD_TRANCHES) {
      pageProps[ALSO_ATTR] = FOLD_ALSO;
    }
    return element(DIV_TAG, pageProps, null);
  }

  function TabPages(props) {
    var model = props.model;
    var pagesProps = {
      className: WINDOW_CLASS,
      style: { display: FLEX, flexDirection: COLUMN, flex: AUTO, minHeight: ZERO }
    };
    pagesProps[PART_ATTR] = TAB_PAGES_PART;
    pagesProps[COUNT_ATTR] = String(drawnTabs(model).length);
    var drawn = drawnTabs(model).map(function (name, at) {
      return element(TabPage, {
        key: String(at),
        model: model,
        name: name,
        at: at,
        page: pageFor(model, name),
        plan: planFor(model, name),
        current: at === props.at
      });
    });
    return element(DIV_TAG, pagesProps, drawn);
  }

  function FooterRow(props) {
    var model = props.model;
    var rowProps = {
      className: WINDOW_CLASS,
      style: {
        display: FLEX,
        flexDirection: ROW,
        alignItems: CENTER,
        flex: FLEX_NONE,
        minWidth: ZERO,
        overflow: HIDDEN
      }
    };
    rowProps[PART_ATTR] = FOOTER_ROW_PART;
    return element(
      DIV_TAG,
      rowProps,
      element(Stretch, { key: FOOTER_STRETCH_PART, part: FOOTER_STRETCH_PART }),
      element(HoverButton, {
        key: APPLY_BUTTON_PART,
        part: APPLY_BUTTON_PART,
        sheet: model[APPLY_STYLE],
        words: model[APPLY_LABEL],
        action: actionNamed(model, APPLY_CLICKED),
        enabled: model[APPLY_ENABLED] === true,
        onPress: applyChanges
      }),
      element(HoverButton, {
        key: CLOSE_BUTTON_PART,
        part: CLOSE_BUTTON_PART,
        sheet: model[CLOSE_STYLE],
        words: model[CLOSE_LABEL],
        action: actionNamed(model, CLOSE_CLICKED),
        onPress: closeWindow
      })
    );
  }

  function Window(props) {
    var model = isPlainObject(props.model) ? props.model : {};
    var state = hooks().useState(currentTab(model));
    var at = state.shift();
    var setAt = state.shift();
    var opened = listField(model, OPENED_SIZE_PX).slice();
    var floor = listField(model, MINIMUM_SIZE_PX).slice();
    var style = {
      display: FLEX,
      flexDirection: COLUMN,
      overflow: HIDDEN,
      width: length(opened.shift()),
      height: length(opened.shift()),
      minWidth: length(floor.shift()),
      minHeight: length(floor.shift())
    };
    var windowProps = {
      className: WINDOW_CLASS,
      style: style,
      onKeyDown: function (event) {
        pressKey(event.key, event.ctrlKey);
      }
    };
    windowProps.tabIndex = ZERO - STEP;
    windowProps[PART_ATTR] = WINDOW_PART;
    windowProps[KEY_ATTR] = text(model[TITLE]);
    windowProps[INDEX_ATTR] = String(at);
    windowProps[COUNT_ATTR] = String(listField(model, SHORTCUTS).length);
    return element(
      DIV_TAG,
      windowProps,
      element(HeaderRow, { key: HEADER_ROW_PART, model: model }),
      element(TabBar, { key: TAB_BAR_PART, model: model, at: at, onPick: setAt }),
      element(TabPages, { key: TAB_PAGES_PART, model: model, at: at }),
      element(FooterRow, { key: FOOTER_ROW_PART, model: model }),
      element(Caption, {
        key: CHANGE_LABEL_PART,
        part: CHANGE_LABEL_PART,
        slot: CHANGE_LABEL,
        sheet: model[CHANGE_STYLE],
        words: model[CHANGE_LABEL]
      })
    );
  }

  function checkFields(model) {
    DECLARED_FIELDS.forEach(function (field) {
      if (!owns(model, field)) {
        windowFaults.push(fault(null, field, MISSING_FAULT, null));
        return;
      }
      if (model[field] === null && NULLABLE_FIELDS.indexOf(field) < ZERO) {
        windowFaults.push(fault(null, field, NULL_FAULT, null));
      }
    });
  }

  function checkShapes(model) {
    DECLARED_BAGS.forEach(function (field) {
      if (owns(model, field) && !isPlainObject(model[field])) {
        windowFaults.push(fault(null, field, NOT_AN_OBJECT_FAULT, kindOf(model[field])));
      }
    });
    DECLARED_LISTS.forEach(function (field) {
      if (owns(model, field) && !Array.isArray(model[field])) {
        windowFaults.push(fault(null, field, NOT_A_LIST_FAULT, kindOf(model[field])));
      }
    });
  }

  // Every drawn tab is a plan row, in the plan's order, for one bot mode.
  function checkTabs(model) {
    var plan = listField(model, TAB_PLAN).map(function (row) {
      return Array.isArray(row) ? row.slice().shift() : undefined;
    });
    var seen = ZERO - STEP;
    var modes = [];
    listField(model, TABS).forEach(function (name, at) {
      var where = TAB_AT + String(at);
      var order = plan.indexOf(name);
      if (order < ZERO) {
        windowFaults.push(fault(where, TABS, UNPLACED_FAULT, name));
        return;
      }
      if (order <= seen) {
        windowFaults.push(fault(where, TABS, DISAGREES_FAULT, order));
      }
      seen = order;
      if (pageFor(model, name) === undefined) {
        windowFaults.push(fault(where, TABS, MISSING_FAULT, name));
      }
      var mode = planFor(model, name).mode;
      if (mode !== model[ANY_MODE] && modes.indexOf(mode) < ZERO) {
        modes.push(mode);
      }
    });
    if (modes.length > STEP) {
      windowFaults.push(fault(null, TABS, DISAGREES_FAULT, modes.length));
    }
    var at = model[CURRENT_TAB];
    var room = listField(model, TABS).length;
    if (Boolean(room) && typeof at === "number" && (at < ZERO || at >= room)) {
      windowFaults.push(fault(null, CURRENT_TAB, UNPLACED_FAULT, at));
    }
  }

  // A tab the plan wraps is a tab the window put inside a scroller.
  function checkWrappedTabs(model) {
    var wanted = listField(model, TABS).filter(function (name) {
      return planFor(model, name).wrapped === model[SCROLL_RESIZABLE];
    });
    var drawn = listField(model, WRAPPED_TABS).map(function (row) {
      return Array.isArray(row) ? row.slice().shift() : undefined;
    });
    if (String(wanted) !== String(drawn)) {
      windowFaults.push(fault(null, WRAPPED_TABS, DISAGREES_FAULT, wanted.length));
    }
    listField(model, WRAPPED_TABS).forEach(function (row, at) {
      var one = Array.isArray(row) ? row.slice() : [];
      one.shift();
      if (one.shift() !== model[SCROLL_RESIZABLE] || one.shift() !== model[SCROLL_FRAME_SHAPE]) {
        windowFaults.push(fault(TAB_AT + String(at), WRAPPED_TABS, WRONG_TYPE_FAULT, at));
      }
    });
  }

  // The two navigation buttons show above the bot count the surface names.
  function checkNavigation(model) {
    var many = listField(model, SIBLINGS).length > numberOr(model[NAV_SHOWN_ABOVE_SIBLINGS], ZERO);
    if (owns(model, NAV_SHOWN) && model[NAV_SHOWN] !== many) {
      windowFaults.push(fault(null, NAV_SHOWN, DISAGREES_FAULT, many));
    }
    var steps = shortcutSteps();
    if (Boolean(steps.length) && !model[NAV_SHOWN]) {
      windowFaults.push(fault(null, SHORTCUTS, DISAGREES_FAULT, steps.length));
    }
    [PREV_STEP, NEXT_STEP].forEach(function (field) {
      if (Boolean(steps.length) && !stepIsBound(model[field])) {
        windowFaults.push(fault(null, SHORTCUTS, MISSING_FAULT, field));
      }
    });
  }

  // The change line, the Apply button and the edited bag name one state.
  function checkChangeLine(model) {
    var edited = Object.keys(objectField(model, CHANGES));
    var pending = changeFields(model);
    if (Boolean(edited.length) !== Boolean(pending.length)) {
      windowFaults.push(fault(null, CHANGE_LABEL, DISAGREES_FAULT, edited.length));
    }
    if (owns(model, APPLY_ENABLED) && model[APPLY_ENABLED] !== Boolean(edited.length)) {
      windowFaults.push(fault(null, APPLY_ENABLED, DISAGREES_FAULT, edited.length));
    }
    if (Boolean(edited.length) && model[CHANGE_STYLE] !== model[CHANGE_PENDING_STYLE]) {
      windowFaults.push(fault(null, CHANGE_STYLE, DISAGREES_FAULT, model[CHANGE_PENDING_STYLE]));
    }
    if (edited.length || model[CHANGE_LABEL] === model[CHANGE_EMPTY_TEXT]) {
      return;
    }
    var head = String(model[CHANGE_APPLIED_FORMAT]).split(BRACE_OPEN).shift();
    if (!opensWith(model[CHANGE_LABEL], head)) {
      windowFaults.push(fault(null, CHANGE_LABEL, UNPLACED_FAULT, model[CHANGE_LABEL]));
      return;
    }
    if (model[CHANGE_STYLE] !== model[CHANGE_APPLIED_STYLE]) {
      windowFaults.push(fault(null, CHANGE_STYLE, DISAGREES_FAULT, model[CHANGE_APPLIED_STYLE]));
    }
  }

  // A bag walk reorders a numeric name, so the drawn line owns the order.
  function checkChangeOrder(model) {
    var edited = Object.keys(objectField(model, CHANGES));
    var pending = changeFields(model);
    if (!edited.length || edited.length !== pending.length) {
      return;
    }
    if (String(edited) !== String(pending)) {
      windowFaults.push(fault(null, CHANGES, DISAGREES_FAULT, pending.join(COMMA)));
    }
  }

  // The badge paints one state, so its fill opens with its own text colour.
  function checkStateBadge(model) {
    var painted = {};
    declarations(model[STATE_STYLE]).forEach(function (one) {
      painted[one.property] = one.value;
    });
    var fill = painted[FILL_PROPERTY];
    var words = painted[COLOUR_PROPERTY];
    if (fill === undefined || words === undefined) {
      return;
    }
    if (!sameChannels(fill, String(words))) {
      windowFaults.push(fault(STATE_BADGE_PART, FILL_PROPERTY, DISAGREES_FAULT, words));
    }
  }

  function checkColours(model) {
    SHEET_FIELDS.forEach(function (field) {
      declarations(model[field]).forEach(function (one) {
        var named = qtColour(one.value);
        if (named !== undefined) {
          windowFaults.push(fault(one.property, field, QT_COLOUR_FAULT, named));
        }
      });
      stateRules(model[field]).forEach(function (rule) {
        declarations(rule.body).forEach(function (one) {
          var named = qtColour(one.value);
          if (named !== undefined) {
            windowFaults.push(fault(rule.selector, field, QT_COLOUR_FAULT, named));
          }
        });
      });
    });
  }

  function nameMarkup(where, field, value) {
    if (typeof value === "string" && carries(value, MARKUP_OPEN)) {
      windowFaults.push(fault(where, field, MARKUP_FAULT, MARKUP_OPEN));
    }
  }

  function checkMarkup(model) {
    WORD_FIELDS.forEach(function (field) {
      nameMarkup(null, field, model[field]);
    });
    listField(model, TABS).forEach(function (name, at) {
      nameMarkup(TAB_AT + String(at), TABS, name);
    });
  }

  // The window opens no smaller than the floor it carries, on both sides.
  function checkSizes(model) {
    var floor = listField(model, MINIMUM_SIZE_PX);
    var opened = listField(model, OPENED_SIZE_PX);
    [MINIMUM_W_PX, MINIMUM_H_PX].forEach(function (field, at) {
      if (owns(model, field) && floor[at] !== model[field]) {
        windowFaults.push(fault(null, MINIMUM_SIZE_PX, DISAGREES_FAULT, field));
      }
    });
    floor.forEach(function (one, at) {
      if (numberOr(opened[at], ZERO) < numberOr(one, ZERO)) {
        windowFaults.push(fault(null, OPENED_SIZE_PX, DISAGREES_FAULT, at));
      }
    });
  }

  // Every form the window sized carries the same five row settings.
  function formSpec(model) {
    return {
      field_growth: model[FORM_FIELD_GROWTH],
      row_wrap: model[FORM_ROW_WRAP],
      horizontal_spacing_px: model[FORM_HORIZONTAL_SPACING_PX],
      vertical_spacing_px: model[FORM_VERTICAL_SPACING_PX],
      margins_px: listField(model, FORM_MARGINS_PX).slice()
    };
  }

  function checkForms(model) {
    var wanted = formSpec(model);
    listField(model, FORMS).forEach(function (one, at) {
      var where = FORM_AT + String(at);
      if (!isPlainObject(one)) {
        windowFaults.push(fault(where, FORMS, NOT_AN_OBJECT_FAULT, kindOf(one)));
        return;
      }
      Object.keys(wanted).forEach(function (name) {
        if (String(one[name]) !== String(wanted[name])) {
          windowFaults.push(fault(where, name, DISAGREES_FAULT, wanted[name]));
        }
      });
    });
  }

  // Each edit the window sent is one bot id beside the bag it wrote.
  function checkSent(model) {
    listField(model, SENT).forEach(function (one, at) {
      var where = SENT_AT + String(at);
      if (!Array.isArray(one)) {
        windowFaults.push(fault(where, SENT, NOT_A_LIST_FAULT, kindOf(one)));
        return;
      }
      var pair = one.slice();
      if (typeof pair.shift() !== "string") {
        windowFaults.push(fault(where, SENT, WRONG_TYPE_FAULT, at));
      }
      if (!isPlainObject(pair.shift())) {
        windowFaults.push(fault(where, SENT, NOT_AN_OBJECT_FAULT, at));
      }
    });
  }

  // Every value this payload carries must be data a JSON line can hold.
  function plainness() {
    var found = [];
    function descend(path, value) {
      if (value === null) {
        return;
      }
      if (Array.isArray(value)) {
        value.forEach(function (one, at) {
          descend(path + PATH_SPLIT + String(at), one);
        });
        return;
      }
      if (isPlainObject(value)) {
        Object.keys(value).forEach(function (name) {
          descend(path + PATH_SPLIT + name, value[name]);
        });
        return;
      }
      if (typeof value === "object" || typeof value === "function") {
        found.push(path);
      }
    }
    if (held !== null) {
      Object.keys(held.model).forEach(function (name) {
        descend(name, held.model[name]);
      });
    }
    return found;
  }

  function checkPlainData(model) {
    plainness().forEach(function (path) {
      windowFaults.push(fault(null, path, NOT_PLAIN_FAULT, kindOf(model[path])));
    });
  }

  function heldFieldCount(model) {
    return DECLARED_FIELDS.filter(function (field) {
      return owns(model, field);
    }).length;
  }

  function report(model) {
    return {
      declared: {
        fields: DECLARED_FIELDS.length,
        tabs: listField(model, TABS).length,
        spaces: PAGE_PLAN.length,
        changes: Object.keys(objectField(model, CHANGES)).length,
        shortcuts: listField(model, SHORTCUTS).length
      },
      held: {
        fields: heldFieldCount(model),
        tabs: drawnTabs(model).length,
        spaces: emptySpaces().length,
        changes: changeFields(model).length,
        shortcuts: shortcutSteps().filter(function (one) {
          return typeof one === "number";
        }).length
      },
      faults: windowFaults.slice()
    };
  }

  function setBotLiveSettings(model) {
    dispatched = [];
    if (!isPlainObject(model)) {
      held = null;
      windowFaults = [fault(null, null, NOT_AN_OBJECT_FAULT, kindOf(model))];
      return { declared: null, held: null, faults: windowFaults.slice() };
    }
    held = { model: model };
    windowFaults = [];
    checkFields(model);
    checkShapes(model);
    checkTabs(model);
    checkWrappedTabs(model);
    checkNavigation(model);
    checkChangeLine(model);
    checkChangeOrder(model);
    checkStateBadge(model);
    checkColours(model);
    checkMarkup(model);
    checkSizes(model);
    checkForms(model);
    checkSent(model);
    checkPlainData(model);
    return report(model);
  }

  // A failed load is not remembered, so a later ask reaches the bridge.
  function loadBotLiveSettings(params) {
    if (asked !== null) {
      return asked;
    }
    if (!hasBridge()) {
      loadFault = NO_BRIDGE;
      return Promise.resolve(null);
    }
    asked = global.acervator
      .call(METHOD, isPlainObject(params) ? params : {})
      .then(function (model) {
        loadFault = null;
        setBotLiveSettings(model);
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
    return held === null ? null : held.model;
  }

  function field(name) {
    if (held === null || !owns(held.model, name)) {
      return undefined;
    }
    return held.model[name];
  }

  function declaredNames() {
    return DECLARED_FIELDS.slice();
  }

  function bagNames() {
    return DECLARED_BAGS.slice();
  }

  function listNames() {
    return DECLARED_LISTS.slice();
  }

  function wordNames() {
    return WORD_FIELDS.slice();
  }

  function sheetNames() {
    return SHEET_FIELDS.slice();
  }

  function bag(name) {
    return held === null ? {} : copyOf(objectField(held.model, name));
  }

  function list(name) {
    return held === null ? [] : listField(held.model, name).slice();
  }

  function tabNames() {
    return drawnTabs(heldModel()).slice();
  }

  function pageOf(name) {
    var found = pageFor(heldModel(), name);
    return found === undefined ? null : found;
  }

  function editedFields() {
    return changeFields(heldModel()).slice();
  }

  function formOf() {
    return formSpec(heldModel());
  }

  function actions() {
    return bag(ACTIONS);
  }

  function action(name) {
    var found = actions();
    return owns(found, name) ? found[name] : undefined;
  }

  // Every payload value's JavaScript type, by dotted path, null apart.
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
    return windowFaults.slice();
  }

  function sent() {
    return dispatched.slice();
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

  function renderWindow(target, model) {
    var drawn = model;
    if (!isPlainObject(drawn)) {
      drawn = payload();
    }
    var mark = String(drawnTabs(isPlainObject(drawn) ? drawn : {})) + String(
      isPlainObject(drawn) ? drawn[TITLE] : EMPTY
    );
    return draw(target, element(Window, { key: mark, model: drawn }));
  }

  function forget() {
    held = null;
    windowFaults = [];
    loadFault = null;
    asked = null;
    dispatched = [];
  }

  global.acervatorSetBotLiveSettings = setBotLiveSettings;
  global.acervatorLoadBotLiveSettings = loadBotLiveSettings;
  global.acervatorBotLiveSettings = {
    method: METHOD,
    Window: Window,
    HeaderRow: HeaderRow,
    TabBar: TabBar,
    TabPages: TabPages,
    TabPage: TabPage,
    FooterRow: FooterRow,
    HoverButton: HoverButton,
    Caption: Caption,
    payload: payload,
    field: field,
    declaredNames: declaredNames,
    bagNames: bagNames,
    listNames: listNames,
    wordNames: wordNames,
    sheetNames: sheetNames,
    emptySpaces: emptySpaces,
    bag: bag,
    list: list,
    tabNames: tabNames,
    pageOf: pageOf,
    editedFields: editedFields,
    shortcutSteps: shortcutSteps,
    formOf: formOf,
    actions: actions,
    action: action,
    navigatePrev: navigatePrev,
    navigateNext: navigateNext,
    applyChanges: applyChanges,
    closeWindow: closeWindow,
    pressKey: pressKey,
    sent: sent,
    styleOf: styleOf,
    stateStyle: stateStyle,
    keptSheet: keptSheet,
    declarations: declarations,
    qtColour: qtColour,
    alphaOf: alphaOf,
    alphaFraction: alphaFraction,
    alphaScale: function () {
      return ALPHA_SCALE;
    },
    variableFor: variableFor,
    variableInGroups: variableInGroups,
    length: length,
    kinds: kinds,
    plainness: plainness,
    faults: faults,
    loadError: loadError,
    isLoaded: isLoaded,
    renderWindow: renderWindow,
    forget: forget
  };
})(window);
