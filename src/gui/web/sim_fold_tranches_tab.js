// The Simulator's fork of fold_tranches_tab.js under the Simulator's names;
// it answers the sim_fold_tranches_tab.state payload the Sim window pushes.
// Draws the Fold Tranches tab from the fold_tranches_tab.state payload.
(function (global) {
  "use strict";

  var METHOD = "sim_fold_tranches_tab.state";

  var ACCESSIBLE_NAME = "accessible_name";
  var ACTIONS = "actions";
  var ARBITER_BUTTON = "arbiter_button";
  var ARBITER_VALUES = "arbiter_values";
  var ATTRIBUTES = "attributes";
  var BORDER_BY_BACKGROUND = "border_by_background";
  var BORDER_PX = "border_px";
  var BOXES = "boxes";
  var BUS_SUBSCRIPTIONS = "bus_subscriptions";
  var BUS_TOPICS = "bus_topics";
  var BUTTON_STYLE = "button_style";
  var BUTTON_TOOLTIPS = "button_tooltips";
  var BUTTON_VALUES = "button_values";
  var BUTTONS = "buttons";
  var CALL_NAMES = "call_names";
  var CALLS = "calls";
  var CLEAR_REASON = "clear_reason";
  var COLORS = "colors";
  var CONTAINER = "container";
  var DESPAWN = "despawn";
  var EMITTED = "emitted";
  var EMPTY_LABEL = "empty_label";
  var EXTRACTOR_ROW_NUMBER = "extractor_row_number";
  var FIRE_BUTTON = "fire_button";
  var FIRE_READ_FIELDS = "fire_read_fields";
  var FORMATS = "formats";
  var HEALTH_COLORS = "health_colors";
  var HEALTH_GROUP = "health_group";
  var HEALTH_LABELS = "health_labels";
  var HEALTH_ROWS = "health_rows";
  var HEALTH_TOOLTIPS = "health_tooltips";
  var ICONS = "icons";
  var JOINS = "joins";
  var KEYS = "keys";
  var METHOD_FIELD = "method";
  var NO_CELL_COLOR = "no_cell_color";
  var NO_VALUE_TEXT = "no_value_text";
  var NUMBERS = "numbers";
  var OUTCOME = "outcome";
  var OUTCOMES = "outcomes";
  var PANEL_SHOWS = "panel_shows";
  var POLL_ELAPSED_S = "poll_elapsed_s";
  var ROW_CONTROLS = "row_controls";
  var SETTLED = "settled";
  var SIGNALS = "signals";
  var SORT_KEYS = "sort_keys";
  var SOURCES = "sources";
  var TAB_LABEL = "tab_label";
  var TABLE = "table";
  var TEXTS = "texts";
  var THREADS = "threads";
  var TIMER_DELAYS_MS = "timer_delays_ms";
  var TIMERS = "timers";
  var TITLES = "titles";

  // Every top-level name the fold_tranches_tab.state payload carries.
  var DECLARED_FIELDS = [
    ACCESSIBLE_NAME,
    ACTIONS,
    ARBITER_BUTTON,
    ARBITER_VALUES,
    ATTRIBUTES,
    BORDER_BY_BACKGROUND,
    BORDER_PX,
    BOXES,
    BUS_SUBSCRIPTIONS,
    BUS_TOPICS,
    BUTTON_STYLE,
    BUTTON_TOOLTIPS,
    BUTTON_VALUES,
    BUTTONS,
    CALL_NAMES,
    CALLS,
    CLEAR_REASON,
    COLORS,
    CONTAINER,
    DESPAWN,
    EMITTED,
    EMPTY_LABEL,
    EXTRACTOR_ROW_NUMBER,
    FIRE_BUTTON,
    FIRE_READ_FIELDS,
    FORMATS,
    HEALTH_COLORS,
    HEALTH_GROUP,
    HEALTH_LABELS,
    HEALTH_ROWS,
    HEALTH_TOOLTIPS,
    ICONS,
    JOINS,
    KEYS,
    METHOD_FIELD,
    NO_CELL_COLOR,
    NO_VALUE_TEXT,
    NUMBERS,
    OUTCOME,
    OUTCOMES,
    PANEL_SHOWS,
    POLL_ELAPSED_S,
    ROW_CONTROLS,
    SETTLED,
    SIGNALS,
    SORT_KEYS,
    SOURCES,
    TAB_LABEL,
    TABLE,
    TEXTS,
    THREADS,
    TIMER_DELAYS_MS,
    TIMERS,
    TITLES
  ];

  var DECLARED_BAGS = [
    ACTIONS,
    ARBITER_BUTTON,
    ATTRIBUTES,
    BORDER_BY_BACKGROUND,
    BUTTON_VALUES,
    COLORS,
    CONTAINER,
    DESPAWN,
    EMPTY_LABEL,
    FIRE_BUTTON,
    FORMATS,
    HEALTH_GROUP,
    ICONS,
    JOINS,
    KEYS,
    NUMBERS,
    PANEL_SHOWS,
    ROW_CONTROLS,
    SORT_KEYS,
    SOURCES,
    TABLE,
    TEXTS,
    TIMERS,
    TITLES
  ];

  var DECLARED_LISTS = [
    ARBITER_VALUES,
    BOXES,
    BUS_SUBSCRIPTIONS,
    BUS_TOPICS,
    BUTTON_TOOLTIPS,
    BUTTONS,
    CALL_NAMES,
    CALLS,
    EMITTED,
    FIRE_READ_FIELDS,
    HEALTH_COLORS,
    HEALTH_LABELS,
    HEALTH_ROWS,
    HEALTH_TOOLTIPS,
    OUTCOMES,
    SETTLED,
    SIGNALS,
    THREADS,
    TIMER_DELAYS_MS
  ];

  // The wired names, as a list, because pairing three buttons off a bag
  // would rest on that bag's key order.
  var CLEAR_CLICKED = "clear_button.clicked";
  var WIRE_CLICKED = "wire_button.clicked";
  var COUNTERS_CLICKED = "counters_button.clicked";
  var ARBITER_CLICKED = "arbiter_button.clicked";
  var FIRE_CLICKED = "fire_button.clicked";
  var POLL_TIMEOUT = "poll_timer.timeout";
  var CLEAR_ACTIONS = [CLEAR_CLICKED, WIRE_CLICKED, COUNTERS_CLICKED];
  var ACTION_NAMES = [
    CLEAR_CLICKED,
    WIRE_CLICKED,
    COUNTERS_CLICKED,
    ARBITER_CLICKED,
    FIRE_CLICKED,
    POLL_TIMEOUT
  ];

  // The answer names, as a list, so a message box offers them in one order.
  var YES_ANSWER = "yes";
  var NO_ANSWER = "no";
  var CANCEL_ANSWER = "cancel";
  var OK_ANSWER = "ok";
  var ANSWER_NAMES = [YES_ANSWER, NO_ANSWER, CANCEL_ANSWER, OK_ANSWER];

  var COLUMNS = "columns";
  var COLUMN_COUNT = "column_count";
  var COLUMN_TOOLTIPS = "column_tooltips";
  var ROW_COUNT = "row_count";
  var FOLD_ROW_COUNT = "fold_row_count";
  var EXTRACTOR_ROW_COUNT = "extractor_row_count";
  var ROWS = "rows";
  var ROW_COLORS = "row_colors";
  var ROW_BACKGROUNDS = "row_backgrounds";
  var ROW_BORDERS = "row_borders";
  var HIDDEN_ROWS = "hidden_rows";
  var SHOWN = "shown";
  var TABLE_TITLE = "title";
  var FIRE_COLUMN = "fire_column";
  var ARBITER_COLUMN = "arbiter_column";
  var ROW_HEIGHT_PX = "row_height_px";
  var VISIBLE_ROWS = "visible_rows";
  var HEIGHT_ROWS = "height_rows";
  var ALTERNATING = "alternating_row_colors";
  var SHOW_GRID = "show_grid";
  var EDIT_TRIGGERS = "edit_triggers";
  var HEADER_RESIZE_MODE = "header_resize_mode";

  var STYLE_SHEET = "style_sheet";
  var TOOLTIP = "tooltip";
  var ARBITER_TOOLTIPS = "tooltips";
  var ARBITER_LABEL_BAG = "labels";
  var SOURCE_TOOLTIPS = "tooltips";
  var TEXT_FIELD = "text";
  var TIMER_ROW_LABEL = "timer_row";
  var PREVIEW_ROW_LABEL = "preview_row";
  var INSET_PX = "inset_px";
  var FIRE_NUMBERS = "numbers";
  var IDENTITIES = "identities";
  var NOT_APPLICABLE_TOOLTIP = "not_applicable_tooltip";
  var GROUP_TITLE = "title";
  var CONFIGURED_BY_HOST = "configured_by_host";
  var CONFIGURED = "configured";
  var SPACING_PX = "spacing_px";
  var MARGINS_SET = "margins_set";
  var WORD_WRAP = "word_wrap";
  var BOX_TEXT = "text";
  var BOX_TITLE = "title";
  var BOX_ICON = "icon";
  var BOX_BUTTONS = "buttons_value";
  var BOX_DEFAULT = "default_button_value";
  var BOX_FIELDS = [BOX_ICON, BOX_TITLE, BOX_TEXT, BOX_BUTTONS, BOX_DEFAULT];
  var DESPAWN_TOOLTIP = "tooltip";

  var MISSING_FAULT = "missing";
  var NULL_FAULT = "null";
  var NOT_AN_OBJECT_FAULT = "not-an-object";
  var NOT_A_BAG_FAULT = "not-a-bag";
  var NOT_A_LIST_FAULT = "not-a-list";
  var SHORT_LIST_FAULT = "short-list";
  var SWAPPED_ALPHA_FAULT = "swapped-alpha";
  var REORDERED_KEY_FAULT = "reordered-key";
  var DISAGREES_FAULT = "disagrees";
  var UNKNOWN_ACTION_FAULT = "unknown-action";
  var UNPAIRED_TOOLTIP_FAULT = "unpaired-tooltip";
  var NOT_CSS_FAULT = "not-css";
  var NO_CHROME_FAULT = "no-chrome";

  var ROW_AT = "row:";
  var BOX_AT = "box:";
  var PATH_SPLIT = ".";
  var EMPTY = "";

  var NO_BRIDGE = "the preload bridge is not present";

  // Qt paints this gradient by name and no browser stylesheet runs it.
  var QT_ONLY = "qlineargradient";

  var TAB_CLASS = "acervator-fold-tranches";

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

  var TAB_PART = "fold-tranches-tab";
  var HEALTH_GROUP_PART = "health-group";
  var HEALTH_TITLE_PART = "health-group-title";
  var HEALTH_ROW_PART = "health-row";
  var HEALTH_LABEL_PART = "health-label";
  var HEALTH_VALUE_PART = "health-value";
  var CLEAR_BUTTONS_PART = "clear-buttons";
  var CLEAR_BUTTON_PART = "clear-button";
  var EMPTY_NOTE_PART = "empty-note";
  var TRANCHE_PANEL_PART = "tranche-panel";
  var TABLE_TITLE_PART = "table-title";
  var TABLE_PART = "tranche-table";
  var HEAD_PART = "table-head";
  var HEAD_ROW_PART = "head-row";
  var HEADER_CELL_PART = "header-cell";
  var BODY_PART = "table-body";
  var TRANCHE_ROW_PART = "tranche-row";
  var TRANCHE_CELL_PART = "tranche-cell";
  var FIRE_BUTTON_PART = "fire-button";
  var ARBITER_BUTTON_PART = "arbiter-button";
  var CONTROLS_SPACE_PART = "row-controls-space";
  var MESSAGE_BOX_PART = "message-box";
  var BOX_TITLE_PART = "box-title";
  var BOX_TEXT_PART = "box-text";
  var BOX_BUTTON_PART = "box-button";
  var OUTCOME_PART = "outcome";
  var SETTLED_PART = "settled-line";
  var PIN_PART = "tab-pin";

  // PAGE_PART is the space the Live Bot Settings window leaves for this tab.
  var PAGE_PART = "fold-tranches-page";

  var PART_ATTR = "data-part";
  var KEY_ATTR = "data-key";
  var NAME_ATTR = "data-name";
  var INDEX_ATTR = "data-index";
  var COLUMN_ATTR = "data-column";
  var ROW_ATTR = "data-row";
  var KIND_ATTR = "data-kind";
  var COUNT_ATTR = "data-count";
  var ENABLED_ATTR = "data-enabled";
  var ACTION_ATTR = "data-action";
  var HIDDEN_ATTR = "data-hidden";
  var BORDER_ATTR = "data-border";
  var FILL_ATTR = "data-fill";
  var PAINTED_ATTR = "data-painted";
  var NUMBER_ATTR = "data-number";
  var TRANCHE_ATTR = "data-tranche-id";
  var CHILD_ATTR = "data-child-bot-id";
  var ICON_ATTR = "data-icon";
  var VALUE_ATTR = "data-value";
  var DEFAULT_ATTR = "data-default";
  var SHOWN_ATTR = "data-shown";
  var WRAP_ATTR = "data-word-wrap";
  var HOST_ATTR = "data-configured-by-host";
  var MARGINS_ATTR = "data-margins-set";
  var GRID_ATTR = "data-show-grid";
  var ALTERNATING_ATTR = "data-alternating";
  var RESIZE_ATTR = "data-resize-mode";
  var EDIT_ATTR = "data-edit-triggers";
  var MATCHED_ATTR = "data-matched";
  var FILLS_ATTR = "data-fills";
  var STYLED_ATTR = "data-styled";
  var ARIA_LABEL = "aria-label";

  var SELECT_OPEN = "[";
  var SELECT_IS = "=\"";
  var SELECT_CLOSE = "\"]";

  // HASH_ESCAPE decodes to the mark every colour opens with.
  var HASH_ESCAPE = "%23";
  var HEX_MARK = decodeURIComponent(HASH_ESCAPE);
  // SWAPPED_LENGTH is the width of a colour written with eight hex digits.
  var SWAPPED_LENGTH = HEX_MARK.length + "aabbccdd".length;

  var DIGITS = "0123456789";

  var PX = "px";
  var FLEX = "flex";
  var ROW_DIRECTION = "row";
  var COLUMN_DIRECTION = "column";
  var FIXED = "fixed";
  var FULL = "100%";
  var COLLAPSE = "collapse";
  var SOLID = "solid";
  var NOWRAP = "nowrap";
  var NORMAL = "normal";
  var HIDDEN = "hidden";
  var AUTO = "auto";
  var ELLIPSIS = "ellipsis";

  var ZERO = Number(EMPTY);
  var STEP = Number(true);
  var SECOND = STEP + STEP;

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

  // True for a colour written with eight hex digits, which Qt reads alpha-first.
  function isSwappedAlpha(value) {
    return (
      typeof value === "string" &&
      value.length === SWAPPED_LENGTH &&
      value.charAt(ZERO) === HEX_MARK
    );
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

  function colour(value) {
    var api = global.acervatorSimCells;
    if (!api || typeof api.colour !== "function") {
      return text(value);
    }
    return api.colour(value);
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

  function chromeApi() {
    var api = global.acervatorFoldChrome;
    return api && typeof api.rowLabel === "function" ? api : null;
  }

  function model() {
    return held === null ? null : held.model;
  }

  function tableBag() {
    return objectField(model(), TABLE);
  }

  function columns() {
    return listField(tableBag(), COLUMNS).slice();
  }

  function columnTooltip(at) {
    return listField(tableBag(), COLUMN_TOOLTIPS)[at];
  }

  function rows() {
    return listField(tableBag(), ROWS);
  }

  function rowCells(at) {
    var found = rows()[at];
    return Array.isArray(found) ? found : [];
  }

  function extractorWord() {
    var found = model();
    return found === null ? undefined : found[EXTRACTOR_ROW_NUMBER];
  }

  // A row naming itself with the extractor word is an Extractor Tranche row.
  function isExtractorRow(at) {
    return rowCells(at)[ZERO] === extractorWord();
  }

  function foldRowIndexes() {
    var found = [];
    rows().forEach(function (one, at) {
      if (!isExtractorRow(at)) {
        found.push(at);
      }
    });
    return found;
  }

  function extractorRowIndexes() {
    var found = [];
    rows().forEach(function (one, at) {
      if (isExtractorRow(at)) {
        found.push(at);
      }
    });
    return found;
  }

  function fireNumbers() {
    return listField(objectField(model(), FIRE_BUTTON), FIRE_NUMBERS).slice();
  }

  function identities() {
    return listField(objectField(model(), ARBITER_BUTTON), IDENTITIES).slice();
  }

  // The queue number one fold row buys back, by that row's place among fold rows.
  function fireNumberFor(at) {
    var where = foldRowIndexes().indexOf(at);
    return where < ZERO ? undefined : fireNumbers()[where];
  }

  function identityFor(at) {
    var where = extractorRowIndexes().indexOf(at);
    return where < ZERO ? undefined : identities()[where];
  }

  // Every row named by what identifies it, never by where it sits.
  function rowIdentities() {
    return rows().map(function (one, at) {
      var extractor = isExtractorRow(at);
      var identity = identityFor(at);
      return {
        at: at,
        extractor: extractor,
        name: extractor
          ? text(Array.isArray(identity) ? identity[ZERO] : undefined)
          : text(fireNumberFor(at))
      };
    });
  }

  function healthLabels() {
    return listField(model(), HEALTH_LABELS).slice();
  }

  function healthTooltips() {
    return listField(model(), HEALTH_TOOLTIPS).slice();
  }

  function despawnTooltip() {
    return objectField(model(), DESPAWN)[DESPAWN_TOOLTIP];
  }

  // The two rows the despawn tooltip covers, found where that tooltip sits.
  function despawnLabelPair() {
    var tips = healthTooltips();
    var labels = healthLabels();
    var at = tips.indexOf(despawnTooltip());
    if (at < ZERO || labels.length !== tips.length + STEP) {
      return [];
    }
    return [labels[at], labels[at + STEP]];
  }

  // One tooltip per health label, the despawn pair sharing the one they share.
  function healthTooltipMap() {
    var tips = healthTooltips();
    var labels = healthLabels();
    var found = {};
    var shared = tips.indexOf(despawnTooltip());
    if (shared < ZERO || labels.length !== tips.length + STEP) {
      labels.forEach(function (name, at) {
        found[String(name)] = tips[at];
      });
      return found;
    }
    labels.forEach(function (name, at) {
      if (at <= shared) {
        found[String(name)] = tips[at];
        return;
      }
      if (at === shared + STEP) {
        found[String(name)] = tips[shared];
        return;
      }
      found[String(name)] = tips[at - STEP];
    });
    return found;
  }

  function healthTooltip(name) {
    var found = healthTooltipMap();
    return owns(found, String(name)) ? found[String(name)] : undefined;
  }

  function healthRows() {
    return listField(model(), HEALTH_ROWS);
  }

  function healthColour(at) {
    return listField(model(), HEALTH_COLORS)[at];
  }

  // One health row found by its own label, never by where it sits.
  function healthRowNamed(name) {
    var found;
    healthRows().forEach(function (row) {
      if (Array.isArray(row) && row.length && row[ZERO] === name) {
        found = row;
      }
    });
    return found;
  }

  function healthValue(name) {
    var row = healthRowNamed(name);
    return Array.isArray(row) && row.length > STEP ? row[STEP] : undefined;
  }

  function buttons() {
    return listField(model(), BUTTONS);
  }

  function buttonTooltip(at) {
    return listField(model(), BUTTON_TOOLTIPS)[at];
  }

  function action(name) {
    var found = objectField(model(), ACTIONS);
    return owns(found, name) ? found[name] : undefined;
  }

  function answerValue(name) {
    var found = objectField(model(), BUTTON_VALUES);
    return owns(found, name) ? found[name] : undefined;
  }

  function boxes() {
    return listField(model(), BOXES);
  }

  // The answer names one message box offers, read off its own bit pattern.
  function boxAnswers(box) {
    var offered = isPlainObject(box) ? box[BOX_BUTTONS] : undefined;
    if (typeof offered !== "number") {
      return [];
    }
    return ANSWER_NAMES.filter(function (name) {
      var value = answerValue(name);
      return typeof value === "number" && (offered & value) === value;
    });
  }

  function noCellColour() {
    var found = model();
    return found === null ? null : found[NO_CELL_COLOR];
  }

  function borderForFill(fill) {
    var found = objectField(model(), BORDER_BY_BACKGROUND);
    return owns(found, fill) ? found[fill] : undefined;
  }

  function colourNamed(name) {
    var found = objectField(model(), COLORS);
    return owns(found, name) ? found[name] : undefined;
  }

  function emitted() {
    return listField(model(), EMITTED).slice();
  }

  function calls() {
    return listField(model(), CALLS).slice();
  }

  function checkFields(found) {
    DECLARED_FIELDS.forEach(function (name) {
      if (!owns(found, name)) {
        tabFaults.push(fault(null, name, MISSING_FAULT, null));
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
    if (owns(found, METHOD_FIELD) && found[METHOD_FIELD] !== METHOD) {
      tabFaults.push(fault(null, METHOD_FIELD, DISAGREES_FAULT, found[METHOD_FIELD]));
    }
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
    if (listField(found, BUTTONS).length > CLEAR_ACTIONS.length) {
      tabFaults.push(
        fault(null, BUTTONS, DISAGREES_FAULT, listField(found, BUTTONS).length)
      );
    }
    if (listField(found, BUTTON_TOOLTIPS).length < listField(found, BUTTONS).length) {
      tabFaults.push(
        fault(null, BUTTON_TOOLTIPS, SHORT_LIST_FAULT, listField(found, BUTTON_TOOLTIPS).length)
      );
    }
  }

  function checkCounts(found) {
    var table = objectField(found, TABLE);
    var drawn = listField(table, ROWS);
    if (drawn.length !== table[ROW_COUNT]) {
      tabFaults.push(fault(null, ROW_COUNT, DISAGREES_FAULT, table[ROW_COUNT]));
    }
    [ROW_COLORS, ROW_BACKGROUNDS, ROW_BORDERS, HIDDEN_ROWS].forEach(function (name) {
      if (listField(table, name).length !== drawn.length) {
        tabFaults.push(fault(null, name, SHORT_LIST_FAULT, listField(table, name).length));
      }
    });
    if (listField(table, COLUMNS).length !== table[COLUMN_COUNT]) {
      tabFaults.push(fault(null, COLUMN_COUNT, DISAGREES_FAULT, table[COLUMN_COUNT]));
    }
    if (listField(table, COLUMN_TOOLTIPS).length !== listField(table, COLUMNS).length) {
      tabFaults.push(fault(null, COLUMN_TOOLTIPS, SHORT_LIST_FAULT, null));
    }
    drawn.forEach(function (row, at) {
      if (!Array.isArray(row)) {
        tabFaults.push(fault(ROW_AT + String(at), ROWS, NOT_A_LIST_FAULT, kindOf(row)));
        return;
      }
      if (row.length !== table[COLUMN_COUNT]) {
        tabFaults.push(fault(ROW_AT + String(at), ROWS, SHORT_LIST_FAULT, row.length));
      }
    });
  }

  function checkRowKinds(found) {
    var table = objectField(found, TABLE);
    if (extractorRowIndexes().length !== table[EXTRACTOR_ROW_COUNT]) {
      tabFaults.push(
        fault(null, EXTRACTOR_ROW_COUNT, DISAGREES_FAULT, table[EXTRACTOR_ROW_COUNT])
      );
    }
    if (foldRowIndexes().length !== table[FOLD_ROW_COUNT]) {
      tabFaults.push(fault(null, FOLD_ROW_COUNT, DISAGREES_FAULT, table[FOLD_ROW_COUNT]));
    }
    if (fireNumbers().length !== foldRowIndexes().length) {
      tabFaults.push(fault(null, FIRE_BUTTON, SHORT_LIST_FAULT, fireNumbers().length));
    }
    if (identities().length !== extractorRowIndexes().length) {
      tabFaults.push(fault(null, ARBITER_BUTTON, SHORT_LIST_FAULT, identities().length));
    }
    foldRowIndexes().forEach(function (at) {
      if (rowCells(at)[ZERO] !== text(fireNumberFor(at))) {
        tabFaults.push(fault(ROW_AT + String(at), FIRE_BUTTON, DISAGREES_FAULT, rowCells(at)[ZERO]));
      }
    });
  }

  // The despawn pair must be the two rows the panel chrome names.
  function checkHealthTooltips(found) {
    var labels = listField(found, HEALTH_LABELS);
    var tips = listField(found, HEALTH_TOOLTIPS);
    if (labels.length !== tips.length + STEP) {
      tabFaults.push(fault(null, HEALTH_TOOLTIPS, UNPAIRED_TOOLTIP_FAULT, tips.length));
    }
    var api = chromeApi();
    if (api === null) {
      tabFaults.push(fault(null, HEALTH_TOOLTIPS, NO_CHROME_FAULT, null));
      return;
    }
    var pair = despawnLabelPair();
    var named = [api.rowLabel(TIMER_ROW_LABEL), api.rowLabel(PREVIEW_ROW_LABEL)];
    if (pair[ZERO] !== named[ZERO] || pair[STEP] !== named[STEP]) {
      tabFaults.push(fault(null, HEALTH_TOOLTIPS, DISAGREES_FAULT, pair));
    }
  }

  function checkColour(where, field, value) {
    if (isSwappedAlpha(value)) {
      tabFaults.push(fault(where, field, SWAPPED_ALPHA_FAULT, value));
    }
  }

  function checkColours(found) {
    var bag = objectField(found, COLORS);
    Object.keys(bag).forEach(function (name) {
      checkColour(null, COLORS, bag[name]);
    });
    var borders = objectField(found, BORDER_BY_BACKGROUND);
    Object.keys(borders).forEach(function (fill) {
      checkColour(null, BORDER_BY_BACKGROUND, fill);
      checkColour(null, BORDER_BY_BACKGROUND, borders[fill]);
    });
    var table = objectField(found, TABLE);
    listField(table, ROW_COLORS).forEach(function (row, at) {
      (Array.isArray(row) ? row : []).forEach(function (value) {
        checkColour(ROW_AT + String(at), ROW_COLORS, value);
      });
    });
    [ROW_BACKGROUNDS, ROW_BORDERS].forEach(function (name) {
      listField(table, name).forEach(function (value, at) {
        checkColour(ROW_AT + String(at), name, value);
      });
    });
    listField(found, HEALTH_COLORS).forEach(function (value, at) {
      checkColour(ROW_AT + String(at), HEALTH_COLORS, value);
      declarations(value).forEach(function (one) {
        checkColour(ROW_AT + String(at), HEALTH_COLORS, one.value);
      });
    });
  }

  function checkSheets(found) {
    var sheets = [
      { field: BUTTON_STYLE, sheet: found[BUTTON_STYLE] },
      { field: FIRE_BUTTON, sheet: objectField(found, FIRE_BUTTON)[STYLE_SHEET] },
      { field: ARBITER_BUTTON, sheet: objectField(found, ARBITER_BUTTON)[STYLE_SHEET] },
      { field: EMPTY_LABEL, sheet: objectField(found, EMPTY_LABEL)[STYLE_SHEET] }
    ];
    sheets.forEach(function (one) {
      declarations(one.sheet).forEach(function (written) {
        checkColour(null, one.field, written.value);
        if (String(written.value).indexOf(QT_ONLY) >= ZERO) {
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
    listField(found, BOXES).forEach(function (box, at) {
      if (!isPlainObject(box)) {
        tabFaults.push(fault(BOX_AT + String(at), BOXES, NOT_AN_OBJECT_FAULT, kindOf(box)));
        return;
      }
      BOX_FIELDS.forEach(function (name) {
        if (!owns(box, name)) {
          tabFaults.push(fault(BOX_AT + String(at), BOXES, MISSING_FAULT, name));
        }
      });
      if (!boxAnswers(box).length) {
        tabFaults.push(fault(BOX_AT + String(at), BOXES, SHORT_LIST_FAULT, box[BOX_BUTTONS]));
      }
    });
  }

  // The Arbiter word one row shows, matched to the tooltip that explains it.
  function arbiterTooltipFor(word) {
    var arbiter = objectField(model(), ARBITER_BUTTON);
    var labels = objectField(arbiter, ARBITER_LABEL_BAG);
    var tips = listField(arbiter, ARBITER_TOOLTIPS);
    var at = ZERO - STEP;
    listField(model(), ARBITER_VALUES).forEach(function (value, index) {
      if (labels[value] === word) {
        at = index;
      }
    });
    return at < ZERO ? arbiter[NOT_APPLICABLE_TOOLTIP] : tips[at];
  }

  // A cell whose own words are a source label carries that label's tooltip.
  function sourceTooltipFor(words) {
    var tips = objectField(objectField(model(), SOURCES), SOURCE_TOOLTIPS);
    return owns(tips, String(words)) ? tips[String(words)] : undefined;
  }

  function cellTooltip(at, column) {
    var words = rowCells(at)[column];
    if (column === tableBag()[ARBITER_COLUMN]) {
      return arbiterTooltipFor(words);
    }
    return sourceTooltipFor(words);
  }

  function element() {
    return global.React.createElement.apply(null, arguments);
  }

  // A bare colour carries no declaration, so it paints the text and nothing else.
  function paintedStyle(value) {
    if (value === noCellColour() || value === undefined) {
      return {};
    }
    var written = declarations(value);
    if (!written.length) {
      return { color: colour(value) };
    }
    return styleOf(value);
  }

  function HealthRow(props) {
    var row = Array.isArray(props.row) ? props.row : [];
    var name = row.length ? row[ZERO] : undefined;
    var tip = healthTooltip(name);
    var sheet = healthColour(props.at);
    var rowProps = {
      className: TAB_CLASS,
      style: { display: FLEX, flexDirection: ROW_DIRECTION }
    };
    rowProps[PART_ATTR] = HEALTH_ROW_PART;
    rowProps[KEY_ATTR] = text(name);
    rowProps[INDEX_ATTR] = text(props.at);
    var labelProps = { className: TAB_CLASS, title: label(tip) };
    labelProps[PART_ATTR] = HEALTH_LABEL_PART;
    labelProps[KEY_ATTR] = text(name);
    var valueProps = {
      className: TAB_CLASS,
      style: paintedStyle(sheet),
      title: label(tip)
    };
    valueProps[PART_ATTR] = HEALTH_VALUE_PART;
    valueProps[KEY_ATTR] = text(name);
    valueProps[PAINTED_ATTR] = String(sheet !== noCellColour() && sheet !== undefined);
    valueProps[STYLED_ATTR] = String(Boolean(declarations(sheet).length));
    return element(
      DIV_TAG,
      rowProps,
      element(SPAN_TAG, labelProps, text(name)),
      element(SPAN_TAG, valueProps, text(row.length > STEP ? row[STEP] : undefined))
    );
  }

  function HealthGroup(props) {
    var group = objectField(props.model, HEALTH_GROUP);
    var groupProps = {
      className: TAB_CLASS,
      style: { display: FLEX, flexDirection: COLUMN_DIRECTION }
    };
    groupProps[PART_ATTR] = HEALTH_GROUP_PART;
    groupProps[COUNT_ATTR] = text(healthRows().length);
    groupProps[HOST_ATTR] = text(group[CONFIGURED_BY_HOST]);
    groupProps[MATCHED_ATTR] = text(group[CONFIGURED]);
    var titleProps = { className: TAB_CLASS };
    titleProps[PART_ATTR] = HEALTH_TITLE_PART;
    var drawn = [element(SPAN_TAG, titleProps, text(group[GROUP_TITLE]))];
    healthRows().forEach(function (row, at) {
      drawn.push(element(HealthRow, { key: HEALTH_ROW_PART + String(at), row: row, at: at }));
    });
    return element(DIV_TAG, groupProps, drawn);
  }

  function ClearButton(props) {
    var one = Array.isArray(props.button) ? props.button : [];
    var words = one.length ? one[ZERO] : undefined;
    var enabled = one.length > STEP ? one[STEP] === true : false;
    var name = CLEAR_ACTIONS[props.at];
    var buttonProps = {
      className: TAB_CLASS,
      style: styleOf(props.sheet),
      type: BUTTON_TYPE,
      title: label(buttonTooltip(props.at)),
      disabled: !enabled,
      onClick: function () {
        press(name, name);
        if (typeof props.onClear === "function") {
          props.onClear(name);
        }
      }
    };
    buttonProps[PART_ATTR] = CLEAR_BUTTON_PART;
    buttonProps[INDEX_ATTR] = text(props.at);
    buttonProps[NAME_ATTR] = name;
    buttonProps[ACTION_ATTR] = label(action(name));
    buttonProps[ENABLED_ATTR] = String(enabled);
    buttonProps[ARIA_LABEL] = label(words);
    return element(BUTTON_TAG, buttonProps, text(words));
  }

  function ClearButtons(props) {
    var boxProps = {
      className: TAB_CLASS,
      style: { display: FLEX, flexDirection: ROW_DIRECTION }
    };
    boxProps[PART_ATTR] = CLEAR_BUTTONS_PART;
    boxProps[COUNT_ATTR] = text(buttons().length);
    var sheet = props.model[BUTTON_STYLE];
    var drawn = buttons().map(function (one, at) {
      return element(ClearButton, {
        key: CLEAR_ACTIONS[at],
        button: one,
        at: at,
        sheet: sheet,
        onClear: props.onClear
      });
    });
    return element(DIV_TAG, boxProps, drawn);
  }

  function EmptyNote(props) {
    var note = objectField(props.model, EMPTY_LABEL);
    var style = styleOf(note[STYLE_SHEET]);
    style.whiteSpace = note[WORD_WRAP] === true ? NORMAL : NOWRAP;
    var noteProps = { className: TAB_CLASS, style: style, hidden: note[SHOWN] !== true };
    noteProps[PART_ATTR] = EMPTY_NOTE_PART;
    noteProps[SHOWN_ATTR] = text(note[SHOWN]);
    noteProps[WRAP_ATTR] = text(note[WORD_WRAP]);
    return element(DIV_TAG, noteProps, text(note[TEXT_FIELD]));
  }

  function HeaderCell(props) {
    var headProps = {
      className: TAB_CLASS,
      style: { whiteSpace: NOWRAP, overflow: HIDDEN, textOverflow: ELLIPSIS },
      title: label(columnTooltip(props.at))
    };
    headProps[PART_ATTR] = HEADER_CELL_PART;
    headProps[COLUMN_ATTR] = text(props.at);
    headProps[KEY_ATTR] = text(props.name);
    headProps[ARIA_LABEL] = label(props.name);
    return element(HEAD_CELL_TAG, headProps, text(props.name));
  }

  function FireButton(props) {
    var fire = objectField(model(), FIRE_BUTTON);
    var style = styleOf(fire[STYLE_SHEET]);
    style.marginTop = length(fire[INSET_PX]);
    style.marginBottom = length(fire[INSET_PX]);
    var buttonProps = {
      className: TAB_CLASS,
      style: style,
      type: BUTTON_TYPE,
      title: label(fire[TOOLTIP]),
      onClick: function () {
        press(FIRE_CLICKED, props.number);
        if (typeof props.onFire === "function") {
          props.onFire(props.number);
        }
      }
    };
    buttonProps[PART_ATTR] = FIRE_BUTTON_PART;
    buttonProps[NUMBER_ATTR] = text(props.number);
    buttonProps[ROW_ATTR] = text(props.at);
    buttonProps[ACTION_ATTR] = label(action(FIRE_CLICKED));
    buttonProps[ARIA_LABEL] = label(props.words);
    return element(BUTTON_TAG, buttonProps, text(props.words));
  }

  function ArbiterButton(props) {
    var arbiter = objectField(model(), ARBITER_BUTTON);
    var identity = Array.isArray(props.identity) ? props.identity : [];
    var buttonProps = {
      className: TAB_CLASS,
      style: styleOf(arbiter[STYLE_SHEET]),
      type: BUTTON_TYPE,
      title: label(props.tip),
      onClick: function () {
        press(ARBITER_CLICKED, identity);
        if (typeof props.onArbiter === "function") {
          props.onArbiter(identity);
        }
      }
    };
    buttonProps[PART_ATTR] = ARBITER_BUTTON_PART;
    buttonProps[TRANCHE_ATTR] = text(identity[ZERO]);
    buttonProps[CHILD_ATTR] = text(identity[STEP]);
    buttonProps[ROW_ATTR] = text(props.at);
    buttonProps[ACTION_ATTR] = label(action(ARBITER_CLICKED));
    buttonProps[ARIA_LABEL] = label(props.words);
    return element(BUTTON_TAG, buttonProps, text(props.words));
  }

  // The Fire column carries a button on a fold row, the Arbiter column on an
  // Extractor row.
  function cellChild(props) {
    var table = tableBag();
    var at = props.at;
    var column = props.column;
    if (!isExtractorRow(at) && column === table[FIRE_COLUMN]) {
      return element(FireButton, {
        at: at,
        number: fireNumberFor(at),
        words: columns()[column],
        onFire: props.onFire
      });
    }
    if (isExtractorRow(at) && column === table[ARBITER_COLUMN]) {
      return element(ArbiterButton, {
        at: at,
        identity: identityFor(at),
        words: rowCells(at)[column],
        tip: arbiterTooltipFor(rowCells(at)[column]),
        onArbiter: props.onArbiter
      });
    }
    return text(rowCells(at)[column]);
  }

  function TrancheCell(props) {
    var table = tableBag();
    var at = props.at;
    var column = props.column;
    var painted = listField(table, ROW_COLORS)[at];
    var value = Array.isArray(painted) ? painted[column] : undefined;
    var style = { whiteSpace: NOWRAP, overflow: HIDDEN, textOverflow: ELLIPSIS };
    if (value !== noCellColour() && value !== undefined) {
      style.color = colour(value);
    }
    var cellProps = {
      className: TAB_CLASS,
      style: style,
      title: label(cellTooltip(at, column))
    };
    cellProps[PART_ATTR] = TRANCHE_CELL_PART;
    cellProps[COLUMN_ATTR] = text(column);
    cellProps[KEY_ATTR] = text(columns()[column]);
    cellProps[PAINTED_ATTR] = String(value !== noCellColour() && value !== undefined);
    return element(CELL_TAG, cellProps, cellChild(props));
  }

  function TrancheRow(props) {
    var table = tableBag();
    var at = props.at;
    var fill = listField(table, ROW_BACKGROUNDS)[at];
    var edge = listField(table, ROW_BORDERS)[at];
    var style = {
      background: colour(fill),
      height: length(table[ROW_HEIGHT_PX])
    };
    if (edge !== null && edge !== undefined) {
      style.borderStyle = SOLID;
      style.borderWidth = length(props.model[BORDER_PX]);
      style.borderColor = colour(edge);
    }
    var hidden = listField(table, HIDDEN_ROWS)[at] === true;
    var rowProps = { className: TAB_CLASS, style: style, hidden: hidden };
    rowProps[PART_ATTR] = TRANCHE_ROW_PART;
    rowProps[ROW_ATTR] = text(at);
    rowProps[KIND_ATTR] = String(isExtractorRow(at));
    rowProps[NAME_ATTR] = isExtractorRow(at)
      ? text((identityFor(at) || [])[ZERO])
      : text(fireNumberFor(at));
    rowProps[FILL_ATTR] = text(fill);
    rowProps[BORDER_ATTR] = text(edge);
    rowProps[HIDDEN_ATTR] = String(hidden);
    var drawn = columns().map(function (name, column) {
      return element(TrancheCell, {
        key: String(column),
        at: at,
        column: column,
        onFire: props.onFire,
        onArbiter: props.onArbiter
      });
    });
    return element(ROW_TAG, rowProps, drawn);
  }

  // fold_chrome.js draws the order picker and the filter box into this space.
  function RowControlSpace(props) {
    var api = global.acervatorFoldChrome;
    var spaceProps = { className: TAB_CLASS };
    spaceProps[PART_ATTR] = CONTROLS_SPACE_PART;
    spaceProps[FILLS_ATTR] = text(api ? api.method : undefined);
    spaceProps[MATCHED_ATTR] = String(Boolean(api && api.isLoaded && api.isLoaded()));
    if (!api || !api.RowControls || !api.isLoaded || !api.isLoaded()) {
      return element(DIV_TAG, spaceProps, null);
    }
    return element(
      DIV_TAG,
      spaceProps,
      element(api.RowControls, {
        typed: props.typed,
        onPick: props.onPick,
        onType: props.onType
      })
    );
  }

  function TranchePanel(props) {
    var table = objectField(props.model, TABLE);
    var panelProps = {
      className: TAB_CLASS,
      style: { display: FLEX, flexDirection: COLUMN_DIRECTION, overflow: AUTO },
      hidden: table[SHOWN] !== true
    };
    panelProps[PART_ATTR] = TRANCHE_PANEL_PART;
    panelProps[SHOWN_ATTR] = text(table[SHOWN]);
    var titleProps = { className: TAB_CLASS };
    titleProps[PART_ATTR] = TABLE_TITLE_PART;
    var headProps = { className: TAB_CLASS };
    headProps[PART_ATTR] = HEAD_PART;
    var headRowProps = { className: TAB_CLASS };
    headRowProps[PART_ATTR] = HEAD_ROW_PART;
    headRowProps[COUNT_ATTR] = text(table[COLUMN_COUNT]);
    var bodyProps = { className: TAB_CLASS };
    bodyProps[PART_ATTR] = BODY_PART;
    bodyProps[COUNT_ATTR] = text(table[ROW_COUNT]);
    var tableProps = {
      className: TAB_CLASS,
      style: { tableLayout: FIXED, width: FULL, borderCollapse: COLLAPSE }
    };
    tableProps[PART_ATTR] = TABLE_PART;
    tableProps[GRID_ATTR] = text(table[SHOW_GRID]);
    tableProps[ALTERNATING_ATTR] = text(table[ALTERNATING]);
    tableProps[RESIZE_ATTR] = text(table[HEADER_RESIZE_MODE]);
    tableProps[EDIT_ATTR] = text(table[EDIT_TRIGGERS]);
    tableProps[INDEX_ATTR] = text(table[HEIGHT_ROWS]);
    tableProps[COUNT_ATTR] = text(table[VISIBLE_ROWS]);
    return element(
      DIV_TAG,
      panelProps,
      element(SPAN_TAG, titleProps, text(table[TABLE_TITLE])),
      element(RowControlSpace, {
        key: CONTROLS_SPACE_PART,
        typed: props.typed,
        onPick: props.onPick,
        onType: props.onType
      }),
      element(
        TABLE_TAG,
        tableProps,
        element(
          HEAD_TAG,
          headProps,
          element(
            ROW_TAG,
            headRowProps,
            columns().map(function (name, at) {
              return element(HeaderCell, { key: String(at), name: name, at: at });
            })
          )
        ),
        element(
          BODY_TAG,
          bodyProps,
          listField(table, ROWS).map(function (one, at) {
            return element(TrancheRow, {
              key: String(at),
              model: props.model,
              at: at,
              onFire: props.onFire,
              onArbiter: props.onArbiter
            });
          })
        )
      )
    );
  }

  function BoxButton(props) {
    var value = answerValue(props.name);
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
    var boxProps = { className: TAB_CLASS };
    boxProps[PART_ATTR] = MESSAGE_BOX_PART;
    boxProps[INDEX_ATTR] = text(props.at);
    boxProps[ICON_ATTR] = text(box[BOX_ICON]);
    boxProps[KEY_ATTR] = text(box[BOX_TITLE]);
    boxProps[VALUE_ATTR] = text(box[BOX_BUTTONS]);
    boxProps[DEFAULT_ATTR] = text(box[BOX_DEFAULT]);
    var titleProps = { className: TAB_CLASS };
    titleProps[PART_ATTR] = BOX_TITLE_PART;
    var textProps = { className: TAB_CLASS, style: { whiteSpace: NORMAL } };
    textProps[PART_ATTR] = BOX_TEXT_PART;
    var drawn = boxAnswers(box).map(function (name) {
      return element(BoxButton, {
        key: name,
        name: name,
        fallback: box[BOX_DEFAULT],
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

  function TabPin(props) {
    var one = Array.isArray(props.pin) ? props.pin : [];
    var pinProps = { className: TAB_CLASS };
    pinProps[PART_ATTR] = PIN_PART;
    pinProps[NAME_ATTR] = text(one.length ? one[ZERO] : undefined);
    pinProps[INDEX_ATTR] = text(props.at);
    pinProps[MATCHED_ATTR] = String(
      one.length > SECOND && JSON.stringify(one[STEP]) === JSON.stringify(one[SECOND])
    );
    return element(DIV_TAG, pinProps, null);
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
    tabProps[KEY_ATTR] = text(found[TAB_LABEL]);
    tabProps[MARGINS_ATTR] = text(box[MARGINS_SET]);
    tabProps[NAME_ATTR] = text(found[OUTCOME]);
    tabProps[ARIA_LABEL] = label(found[ACCESSIBLE_NAME]);
    var outcomeProps = { className: TAB_CLASS };
    outcomeProps[PART_ATTR] = OUTCOME_PART;
    outcomeProps[VALUE_ATTR] = text(found[OUTCOME]);
    var drawn = [
      element(HealthGroup, { key: HEALTH_GROUP_PART, model: found }),
      element(ClearButtons, { key: CLEAR_BUTTONS_PART, model: found, onClear: props.onClear }),
      element(EmptyNote, { key: EMPTY_NOTE_PART, model: found }),
      element(TranchePanel, {
        key: TRANCHE_PANEL_PART,
        model: found,
        typed: props.typed,
        onPick: props.onPick,
        onType: props.onType,
        onFire: props.onFire,
        onArbiter: props.onArbiter
      }),
      element(SPAN_TAG, outcomeProps, text(found[OUTCOME]))
    ];
    listField(found, SETTLED).forEach(function (line, at) {
      var lineProps = { key: SETTLED_PART + String(at), className: TAB_CLASS };
      lineProps[PART_ATTR] = SETTLED_PART;
      lineProps[INDEX_ATTR] = text(at);
      drawn.push(element(DIV_TAG, lineProps, text(line)));
    });
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
    listField(found, EMITTED).forEach(function (one, at) {
      drawn.push(element(TabPin, { key: PIN_PART + String(at), pin: one, at: at }));
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

  // Counts fields, rows, columns and buttons declared against those held.
  function report() {
    var found = held.model;
    var table = objectField(found, TABLE);
    return {
      declared: {
        fields: DECLARED_FIELDS.length,
        rows: table[ROW_COUNT],
        columns: table[COLUMN_COUNT],
        fold: table[FOLD_ROW_COUNT],
        extractor: table[EXTRACTOR_ROW_COUNT],
        buttons: CLEAR_ACTIONS.length,
        actions: ACTION_NAMES.length
      },
      held: {
        fields: heldFieldCount(found),
        rows: listField(table, ROWS).length,
        columns: listField(table, COLUMNS).length,
        fold: foldRowIndexes().length,
        extractor: extractorRowIndexes().length,
        buttons: listField(found, BUTTONS).length,
        actions: Object.keys(objectField(found, ACTIONS)).length
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
    checkCounts(found);
    checkRowKinds(found);
    checkHealthTooltips(found);
    checkColours(found);
    checkSheets(found);
    checkBagOrder(found);
    checkBoxes(found);
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

  function clearActionNames() {
    return CLEAR_ACTIONS.slice();
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
        typed: wired.typed,
        onClear: wired.onClear,
        onFire: wired.onFire,
        onArbiter: wired.onArbiter,
        onAnswer: wired.onAnswer,
        onPick: wired.onPick,
        onType: wired.onType
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

  global.acervatorSetSimFoldTranchesTab = setTab;
  global.acervatorLoadSimFoldTranchesTab = loadTab;
  global.acervatorSimFoldTranchesTab = {
    method: METHOD,
    spacePart: PAGE_PART,
    Tab: Tab,
    HealthGroup: HealthGroup,
    ClearButtons: ClearButtons,
    TranchePanel: TranchePanel,
    TrancheRow: TrancheRow,
    MessageBox: MessageBox,
    payload: payload,
    declaredNames: declaredNames,
    field: field,
    bag: bag,
    list: list,
    bagKeys: bagKeys,
    actionNames: actionNames,
    clearActionNames: clearActionNames,
    answerNames: answerNames,
    columns: columns,
    columnTooltip: columnTooltip,
    rows: rows,
    rowCells: rowCells,
    rowIdentities: rowIdentities,
    isExtractorRow: isExtractorRow,
    foldRowIndexes: foldRowIndexes,
    extractorRowIndexes: extractorRowIndexes,
    fireNumbers: fireNumbers,
    fireNumberFor: fireNumberFor,
    identities: identities,
    identityFor: identityFor,
    healthLabels: healthLabels,
    healthTooltips: healthTooltips,
    healthTooltipMap: healthTooltipMap,
    healthTooltip: healthTooltip,
    despawnLabelPair: despawnLabelPair,
    healthRows: healthRows,
    healthRowNamed: healthRowNamed,
    healthValue: healthValue,
    healthColour: healthColour,
    buttons: buttons,
    buttonTooltip: buttonTooltip,
    action: action,
    answerValue: answerValue,
    boxes: boxes,
    boxAnswers: boxAnswers,
    noCellColour: noCellColour,
    borderForFill: borderForFill,
    colourNamed: colourNamed,
    emitted: emitted,
    calls: calls,
    press: press,
    pressed: pressed,
    paintedStyle: paintedStyle,
    arbiterTooltipFor: arbiterTooltipFor,
    sourceTooltipFor: sourceTooltipFor,
    cellTooltip: cellTooltip,
    isSwappedAlpha: isSwappedAlpha,
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
