// The Simulator's fork of phantom_bots_tab.js under the Simulator's names;
// it answers the sim_phantom_bots_tab.state payload the Sim window pushes.
// Draws the Phantom Bots tab from the phantom_bots_tab.state payload.
(function (global) {
  "use strict";

  var METHOD = "sim_phantom_bots_tab.state";

  var ACCESSIBLE_NAME = "accessible_name";
  var ACTIONS = "actions";
  var ALLOWED_TIMEFRAMES = "allowed_timeframes";
  var ATTRIBUTES = "attributes";
  var BUS_EMITS = "bus_emits";
  var BUS_TOPICS = "bus_topics";
  var CALL_NAMES = "call_names";
  var CALLS = "calls";
  var CHANGES = "changes";
  var COLORS = "colors";
  var CONTAINER = "container";
  var DEFAULTS = "defaults";
  var EMPTY_LABEL = "empty_label";
  var EMPTY_TEXTS = "empty_texts";
  var ENABLE_CHECK = "enable_check";
  var ENABLE_GROUP = "enable_group";
  var EXCHANGE_ID = "exchange_id";
  var FALLBACK_TIMEFRAMES = "fallback_timeframes";
  var FIELDS = "fields";
  var FORMATS = "formats";
  var FORMS = "forms";
  var INFO_LABEL = "info_label";
  var KEYS = "keys";
  var LABELS = "labels";
  var LOCK_GROUP = "lock_group";
  var LOCK_SPIN = "lock_spin";
  var LOCKS_GROUP = "locks_group";
  var LOCKS_TABLE = "locks_table";
  var NO_CELL_COLOR = "no_cell_color";
  var NO_CONFIG = "no_config";
  var NO_EXCHANGE_ID = "no_exchange_id";
  var NO_REFUSAL = "no_refusal";
  var PHANTOM_GROUP = "phantom_group";
  var PHANTOM_TABLE = "phantom_table";
  var SIGNAL_COUNT = "signal_count";
  var STEPS = "steps";
  var STRETCH_SHOWN = "stretch_shown";
  var SUMMARY_GROUP = "summary_group";
  var SUMMARY_ROWS = "summary_rows";
  var TABLE_RULES = "table_rules";
  var TEXTS = "texts";
  var THREAD_COUNT = "thread_count";
  var THRESHOLDS = "thresholds";
  var TIMEFRAME_COMBO = "timeframe_combo";
  var TIMEFRAME_GROUP = "timeframe_group";
  var TIMEFRAME_HINT = "timeframe_hint";
  var TIMEFRAMES = "timeframes";
  var TIMER_DELAYS_MS = "timer_delays_ms";
  var TIMERS = "timers";

  // Every top-level name the phantom_bots_tab.state payload carries.
  var DECLARED_FIELDS = [
    ACCESSIBLE_NAME,
    ACTIONS,
    ALLOWED_TIMEFRAMES,
    ATTRIBUTES,
    BUS_EMITS,
    BUS_TOPICS,
    CALL_NAMES,
    CALLS,
    CHANGES,
    COLORS,
    CONTAINER,
    DEFAULTS,
    EMPTY_LABEL,
    EMPTY_TEXTS,
    ENABLE_CHECK,
    ENABLE_GROUP,
    EXCHANGE_ID,
    FALLBACK_TIMEFRAMES,
    FIELDS,
    FORMATS,
    FORMS,
    INFO_LABEL,
    KEYS,
    LABELS,
    LOCK_GROUP,
    LOCK_SPIN,
    LOCKS_GROUP,
    LOCKS_TABLE,
    NO_CELL_COLOR,
    NO_CONFIG,
    NO_EXCHANGE_ID,
    NO_REFUSAL,
    PHANTOM_GROUP,
    PHANTOM_TABLE,
    SIGNAL_COUNT,
    STEPS,
    STRETCH_SHOWN,
    SUMMARY_GROUP,
    SUMMARY_ROWS,
    TABLE_RULES,
    TEXTS,
    THREAD_COUNT,
    THRESHOLDS,
    TIMEFRAME_COMBO,
    TIMEFRAME_GROUP,
    TIMEFRAME_HINT,
    TIMEFRAMES,
    TIMER_DELAYS_MS,
    TIMERS
  ];

  var DECLARED_BAGS = [
    ACTIONS,
    ATTRIBUTES,
    COLORS,
    CONTAINER,
    DEFAULTS,
    EMPTY_LABEL,
    EMPTY_TEXTS,
    ENABLE_CHECK,
    ENABLE_GROUP,
    FIELDS,
    FORMATS,
    FORMS,
    INFO_LABEL,
    KEYS,
    LABELS,
    LOCK_GROUP,
    LOCK_SPIN,
    LOCKS_GROUP,
    LOCKS_TABLE,
    NO_REFUSAL,
    PHANTOM_GROUP,
    PHANTOM_TABLE,
    SUMMARY_GROUP,
    TABLE_RULES,
    TEXTS,
    THRESHOLDS,
    TIMEFRAME_COMBO,
    TIMEFRAME_GROUP,
    TIMEFRAME_HINT,
    TIMERS
  ];

  var DECLARED_LISTS = [
    ALLOWED_TIMEFRAMES,
    BUS_EMITS,
    BUS_TOPICS,
    CALL_NAMES,
    CALLS,
    CHANGES,
    FALLBACK_TIMEFRAMES,
    STEPS,
    SUMMARY_ROWS,
    TIMEFRAMES,
    TIMER_DELAYS_MS
  ];

  // ACTION_NAMES lists the three settings, so no bag key order pairs them.
  var ENABLE_TOGGLED = "phantom_enable.toggled";
  var TIMEFRAME_PICKED = "timeframe_combo.changed";
  var LOCK_MOVED = "lock_spin.valueChanged";
  var ACTION_NAMES = [ENABLE_TOGGLED, TIMEFRAME_PICKED, LOCK_MOVED];

  var TITLE = "title";
  var TEXT = "text";
  var STYLE_SHEET = "style_sheet";
  var WORD_WRAP = "word_wrap";
  var SHOWN = "shown";
  var CHECKED = "checked";
  var SPACING_PX = "spacing_px";
  var MARGINS_SET = "margins_set";
  var CONFIGURED_BY_HOST = "configured_by_host";
  var CONFIGURED = "configured";
  var ROW_LABEL = "row_label";
  var ITEMS = "items";
  var CURRENT = "current";
  var PARENT = "parent";
  var REFUSAL = "refusal";
  var MINIMUM = "minimum";
  var MAXIMUM = "maximum";
  var REQUESTED = "requested";
  var VALUE = "value";
  var TOOLTIP = "tooltip";
  var COLUMNS = "columns";
  var COLUMN_COUNT = "column_count";
  var MAX_HEIGHT_PX = "max_height_px";
  var ROW_COUNT = "row_count";
  var ROWS = "rows";
  var ROW_COLORS = "row_colors";
  var HEADER_RESIZE_MODE = "header_resize_mode";
  var VERTICAL_HEADER_VISIBLE = "vertical_header_visible";
  var EDIT_TRIGGERS = "edit_triggers";
  var ALTERNATING_ROW_COLORS = "alternating_row_colors";

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
  var UNPLACED_FAULT = "unplaced";
  var MARKUP_FAULT = "markup";

  // NULLABLE_FIELDS names the four values a payload may carry as null.
  var NULLABLE_FIELDS = [EXCHANGE_ID, NO_CELL_COLOR, NO_CONFIG, NO_EXCHANGE_ID];

  var ROW_AT = "row:";
  var TIMEFRAME_AT = "timeframe:";
  var SETTING_AT = "setting:";
  var PATH_SPLIT = ".";
  var EMPTY = "";

  var NO_BRIDGE = "the preload bridge is not present";

  // MARKUP_OPEN is the mark a rich-text QLabel takes as formatting.
  var MARKUP_OPEN = "<";

  var TAB_CLASS = "acervator-phantom-bots";

  var DIV_TAG = "div";
  var SPAN_TAG = "span";
  var INPUT_TAG = "input";
  var TABLE_TAG = "table";
  var HEAD_TAG = "thead";
  var BODY_TAG = "tbody";
  var ROW_TAG = "tr";
  var HEAD_CELL_TAG = "th";
  var CELL_TAG = "td";
  var SELECT_TAG = "select";
  var OPTION_TAG = "option";
  var CHECKBOX_TYPE = "checkbox";
  var NUMBER_TYPE = "number";

  var TAB_PART = "phantom-bots-tab";
  var INFO_NOTE_PART = "info-note";
  var ENABLE_GROUP_PART = "enable-group";
  var ENABLE_TITLE_PART = "enable-group-title";
  var ENABLE_ROW_PART = "enable-check-row";
  var ENABLE_CHECK_PART = "enable-check";
  var ENABLE_TEXT_PART = "enable-check-text";
  var TIMEFRAME_GROUP_PART = "timeframe-group";
  var TIMEFRAME_TITLE_PART = "timeframe-group-title";
  var TIMEFRAME_HINT_PART = "timeframe-hint";
  var TIMEFRAME_ROW_PART = "timeframe-row";
  var TIMEFRAME_LABEL_PART = "timeframe-label";
  var TIMEFRAME_SELECT_PART = "timeframe-select";
  var TIMEFRAME_OPTION_PART = "timeframe-option";
  var TIMEFRAME_REFUSAL_PART = "timeframe-refusal";
  var LOCK_GROUP_PART = "lock-group";
  var LOCK_TITLE_PART = "lock-group-title";
  var LOCK_ROW_PART = "lock-row";
  var LOCK_LABEL_PART = "lock-label";
  var LOCK_SPIN_PART = "lock-spin";
  var SUMMARY_GROUP_PART = "summary-group";
  var SUMMARY_TITLE_PART = "summary-group-title";
  var SUMMARY_ROW_PART = "summary-row";
  var SUMMARY_LABEL_PART = "summary-label";
  var SUMMARY_VALUE_PART = "summary-value";
  var EMPTY_NOTE_PART = "empty-note";
  var STRETCH_PART = "tab-stretch";
  var CHANGE_LINE_PART = "change-line";

  var PHANTOM_KIND = "phantom";
  var LOCKS_KIND = "locks";

  var PHANTOM_PARTS = {
    group: "phantom-group",
    title: "phantom-group-title",
    box: "phantom-table-box",
    table: "phantom-table",
    head: "phantom-table-head",
    headRow: "phantom-head-row",
    corner: "phantom-corner",
    headerCell: "phantom-header-cell",
    body: "phantom-table-body",
    row: "phantom-row",
    number: "phantom-row-number",
    cell: "phantom-cell"
  };

  var LOCKS_PARTS = {
    group: "locks-group",
    title: "locks-group-title",
    box: "locks-table-box",
    table: "locks-table",
    head: "locks-table-head",
    headRow: "locks-head-row",
    corner: "locks-corner",
    headerCell: "locks-header-cell",
    body: "locks-table-body",
    row: "locks-row",
    number: "locks-row-number",
    cell: "locks-cell"
  };

  // One row per table: its own name, the two payload bags, its parts.
  var TABLE_PLAN = [
    [PHANTOM_KIND, PHANTOM_TABLE, PHANTOM_GROUP, PHANTOM_PARTS],
    [LOCKS_KIND, LOCKS_TABLE, LOCKS_GROUP, LOCKS_PARTS]
  ];

  // PAGE_PART is the space the Live Bot Settings window leaves for this tab.
  var PAGE_PART = "phantom-bots-page";

  var PART_ATTR = "data-part";
  var KEY_ATTR = "data-key";
  var NAME_ATTR = "data-name";
  var INDEX_ATTR = "data-index";
  var COLUMN_ATTR = "data-column";
  var ROW_ATTR = "data-row";
  var COUNT_ATTR = "data-count";
  var ENABLED_ATTR = "data-enabled";
  var CHECKED_ATTR = "data-checked";
  var ACTION_ATTR = "data-action";
  var STEP_ATTR = "data-step";
  var SHOWN_ATTR = "data-shown";
  var WRAP_ATTR = "data-word-wrap";
  var PAINTED_ATTR = "data-painted";
  var VALUE_ATTR = "data-value";
  var HOST_ATTR = "data-configured-by-host";
  var MATCHED_ATTR = "data-matched";
  var PARENT_ATTR = "data-parent";
  var MARGINS_ATTR = "data-margins-set";
  var ALTERNATING_ATTR = "data-alternating";
  var RESIZE_ATTR = "data-resize-mode";
  var EDIT_ATTR = "data-edit-triggers";
  var GUTTER_ATTR = "data-row-numbers";
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
  var FULL = "100%";
  var COLLAPSE = "collapse";
  var NOWRAP = "nowrap";
  var PRE = "pre";
  var PRE_WRAP = "pre-wrap";
  var AUTO = "auto";
  var CENTER = "center";

  var ZERO = Number(EMPTY);
  var STEP = Number(true);

  var held = null;
  var tabFaults = [];
  var loadFault = null;
  var asked = null;
  var roots = [];
  var lastPress = null;
  var dispatched = [];

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

  function objectField(node, field) {
    return isPlainObject(node) && isPlainObject(node[field]) ? node[field] : {};
  }

  function listField(node, field) {
    return isPlainObject(node) && Array.isArray(node[field]) ? node[field] : [];
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

  function numberOr(value, fallback) {
    return typeof value === "number" && value === value ? value : fallback;
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
    var worded = printed.split(EMPTY).filter(function (letter) {
      return DIGITS.indexOf(letter) < ZERO;
    });
    return !worded.length;
  }

  function carriesMarkup(value) {
    return typeof value === "string" && value.split(MARKUP_OPEN).length > STEP;
  }

  // table_cells.js owns the rule naming a token variable for one colour.
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

  function model() {
    return held === null ? null : held.model;
  }

  function field(name) {
    if (held === null || !owns(held.model, name)) {
      return undefined;
    }
    return held.model[name];
  }

  function bag(name) {
    return copyOf(objectField(model(), name));
  }

  function list(name) {
    return listField(model(), name).slice();
  }

  function noCellColour() {
    var found = model();
    return found === null ? null : found[NO_CELL_COLOR];
  }

  function action(name) {
    var found = objectField(model(), ACTIONS);
    return owns(found, name) ? found[name] : undefined;
  }

  // The step word one setting sends, named by the model method it runs.
  function stepFor(name) {
    var runs = String(action(name));
    var found = listField(model(), STEPS).filter(function (word) {
      return runs.split(String(word)).shift() === EMPTY && String(word).length;
    });
    return found.length === STEP ? found.shift() : undefined;
  }

  function actionNames() {
    return ACTION_NAMES.slice();
  }

  function timeframeCombo() {
    return objectField(model(), TIMEFRAME_COMBO);
  }

  function timeframeItems() {
    var held = timeframeCombo()[ITEMS];
    return Array.isArray(held) ? held.slice() : [];
  }

  function timeframeNames() {
    return timeframeItems().map(function (one) {
      return Array.isArray(one) ? text(one[ZERO]) : undefined;
    });
  }

  // One timeframe entry found by its own name, never by where it sits.
  function timeframeNamed(name) {
    var found = timeframeItems().filter(function (one) {
      return Array.isArray(one) && text(one[ZERO]) === text(name);
    });
    var one = found.shift();
    if (one === undefined) {
      return undefined;
    }
    return {
      name: text(one[ZERO]),
      supported: one[STEP] === true,
      tooltip: one[STEP + STEP]
    };
  }

  function timeframeCurrent() {
    return text(timeframeCombo()[CURRENT]);
  }

  function timeframeRefusal() {
    return text(timeframeCombo()[REFUSAL]);
  }

  // Whether the exchange serves this timeframe, matched by name.
  function isAllowed(name) {
    return (
      listField(model(), ALLOWED_TIMEFRAMES).filter(function (one) {
        return text(one) === text(name);
      }).length > ZERO
    );
  }

  // The one timeframe the picker holds, as the list a change carries.
  function pickedTimeframes() {
    var held = timeframeCurrent();
    return held === EMPTY ? [] : [held];
  }

  function summaryRows() {
    return listField(model(), SUMMARY_ROWS);
  }

  // One status row found by its own label, never by where it sits.
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

  function summarySheet(name) {
    var row = summaryRowNamed(name);
    return Array.isArray(row) && row.length > STEP + STEP
      ? row[STEP + STEP]
      : undefined;
  }

  function planFor(kind) {
    var found = TABLE_PLAN.filter(function (one) {
      return one.slice().shift() === kind;
    });
    var row = found.shift();
    if (row === undefined) {
      return undefined;
    }
    var one = row.slice();
    one.shift();
    return { table: one.shift(), group: one.shift(), parts: one.shift() };
  }

  function tableKinds() {
    return TABLE_PLAN.map(function (one) {
      return one.slice().shift();
    });
  }

  function tableBag(kind) {
    var plan = planFor(kind);
    return plan === undefined ? {} : objectField(model(), plan.table);
  }

  function groupBag(kind) {
    var plan = planFor(kind);
    return plan === undefined ? {} : objectField(model(), plan.group);
  }

  function columnsOf(kind) {
    return listField(tableBag(kind), COLUMNS).slice();
  }

  function rowsOf(kind) {
    return listField(tableBag(kind), ROWS);
  }

  function cellsOf(kind, at) {
    var found = rowsOf(kind)[at];
    return Array.isArray(found) ? found : [];
  }

  function cellColour(kind, at, column) {
    var painted = listField(tableBag(kind), ROW_COLORS)[at];
    return Array.isArray(painted) ? painted[column] : undefined;
  }

  function isPainted(value) {
    return value !== noCellColour() && value !== undefined;
  }

  function cellStyle(value) {
    return isPainted(value) ? { color: colour(value) } : {};
  }

  function calls() {
    return list(CALLS);
  }

  function changes() {
    return list(CHANGES);
  }

  // changedFields names each edited field in the order the tab recorded it.
  function changedFields() {
    return changes().map(function (one) {
      return Array.isArray(one) ? text(one.slice().shift()) : undefined;
    });
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
    var written = objectField(found, ACTIONS);
    ACTION_NAMES.forEach(function (name) {
      if (!owns(written, name)) {
        tabFaults.push(fault(null, ACTIONS, MISSING_FAULT, name));
        return;
      }
      if (stepFor(name) === undefined) {
        tabFaults.push(fault(SETTING_AT + name, STEPS, MISSING_FAULT, name));
      }
    });
    Object.keys(written).forEach(function (name) {
      if (ACTION_NAMES.indexOf(name) < ZERO) {
        tabFaults.push(fault(null, ACTIONS, UNKNOWN_ACTION_FAULT, name));
      }
    });
  }

  // Every table counts its own rows, its own columns and its own colours.
  function checkCounts(found) {
    tableKinds().forEach(function (kind) {
      var plan = planFor(kind);
      var table = objectField(found, plan.table);
      var drawn = listField(table, ROWS);
      if (drawn.length !== table[ROW_COUNT]) {
        tabFaults.push(fault(kind, ROW_COUNT, DISAGREES_FAULT, table[ROW_COUNT]));
      }
      if (listField(table, COLUMNS).length !== table[COLUMN_COUNT]) {
        tabFaults.push(
          fault(kind, COLUMN_COUNT, DISAGREES_FAULT, table[COLUMN_COUNT])
        );
      }
      if (listField(table, ROW_COLORS).length !== drawn.length) {
        tabFaults.push(
          fault(kind, ROW_COLORS, SHORT_LIST_FAULT, listField(table, ROW_COLORS).length)
        );
      }
      drawn.forEach(function (row, at) {
        if (!Array.isArray(row)) {
          tabFaults.push(
            fault(kind + ROW_AT + String(at), ROWS, NOT_A_LIST_FAULT, kindOf(row))
          );
          return;
        }
        if (row.length !== table[COLUMN_COUNT]) {
          tabFaults.push(
            fault(kind + ROW_AT + String(at), ROWS, SHORT_LIST_FAULT, row.length)
          );
        }
      });
      if (Boolean(drawn.length) !== (objectField(found, plan.group)[SHOWN] === true)) {
        tabFaults.push(fault(kind, SHOWN, DISAGREES_FAULT, drawn.length));
      }
    });
  }

  // Eleven entries against eight served timeframes, paired by name alone.
  function checkTimeframes(found) {
    var named = listField(found, TIMEFRAMES).map(function (one) {
      return text(one);
    });
    var drawn = timeframeNames();
    if (Boolean(drawn.length) && String(named) !== String(drawn)) {
      tabFaults.push(fault(null, TIMEFRAME_COMBO, DISAGREES_FAULT, drawn.length));
    }
    drawn.forEach(function (name, at) {
      var one = timeframeNamed(name);
      var where = TIMEFRAME_AT + String(name);
      if (one === undefined) {
        tabFaults.push(fault(where, TIMEFRAME_COMBO, UNPLACED_FAULT, at));
        return;
      }
      if (one.supported !== isAllowed(name)) {
        tabFaults.push(
          fault(where, ALLOWED_TIMEFRAMES, DISAGREES_FAULT, one.supported)
        );
      }
    });
    var held = timeframeCurrent();
    if (drawn.length && held !== EMPTY && drawn.indexOf(held) < ZERO) {
      tabFaults.push(fault(null, CURRENT, UNPLACED_FAULT, held));
    }
  }

  // Four status rows, each found by the label the payload names it with.
  function checkSummary(found) {
    var named = objectField(found, LABELS);
    var rows = listField(found, SUMMARY_ROWS);
    if (!rows.length) {
      return;
    }
    Object.keys(named).forEach(function (key) {
      if (summaryRowNamed(named[key]) === undefined) {
        tabFaults.push(fault(null, SUMMARY_ROWS, MISSING_FAULT, named[key]));
      }
    });
    if (rows.length !== Object.keys(named).length) {
      tabFaults.push(fault(null, SUMMARY_ROWS, SHORT_LIST_FAULT, rows.length));
    }
  }

  // The number box keeps a value inside the floor and the ceiling it carries.
  function checkLockSpin(found) {
    var spin = objectField(found, LOCK_SPIN);
    var kept = numberOr(spin[VALUE], ZERO);
    if (kept < numberOr(spin[MINIMUM], kept) || kept > numberOr(spin[MAXIMUM], kept)) {
      tabFaults.push(fault(null, LOCK_SPIN, UNPLACED_FAULT, spin[VALUE]));
    }
  }

  function checkColour(where, name, value) {
    if (isSwappedAlpha(value)) {
      tabFaults.push(fault(where, name, SWAPPED_ALPHA_FAULT, value));
    }
  }

  function sweptSheets(found) {
    var sheets = [
      [INFO_LABEL, objectField(found, INFO_LABEL)[STYLE_SHEET]],
      [TIMEFRAME_HINT, objectField(found, TIMEFRAME_HINT)[STYLE_SHEET]],
      [EMPTY_LABEL, objectField(found, EMPTY_LABEL)[STYLE_SHEET]]
    ];
    listField(found, SUMMARY_ROWS).forEach(function (row, at) {
      sheets.push([ROW_AT + String(at), Array.isArray(row) ? row[STEP + STEP] : null]);
    });
    return sheets;
  }

  function checkColours(found) {
    var painted = objectField(found, COLORS);
    Object.keys(painted).forEach(function (name) {
      checkColour(null, COLORS, painted[name]);
    });
    tableKinds().forEach(function (kind) {
      var table = objectField(found, planFor(kind).table);
      listField(table, ROW_COLORS).forEach(function (row, at) {
        (Array.isArray(row) ? row : []).forEach(function (value) {
          checkColour(kind + ROW_AT + String(at), ROW_COLORS, value);
        });
      });
    });
    sweptSheets(found).forEach(function (one) {
      var where = one.slice().shift();
      var sheet = one.slice().pop();
      declarations(sheet).forEach(function (written) {
        checkColour(where, SUMMARY_ROWS, written.value);
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

  // wordsDrawn lists every word this tab draws, so markup can be refused.
  function wordsDrawn(found) {
    var words = [
      [INFO_LABEL, objectField(found, INFO_LABEL)[TEXT]],
      [TIMEFRAME_HINT, objectField(found, TIMEFRAME_HINT)[TEXT]],
      [EMPTY_LABEL, objectField(found, EMPTY_LABEL)[TEXT]],
      [ENABLE_CHECK, objectField(found, ENABLE_CHECK)[TEXT]],
      [ENABLE_GROUP, objectField(found, ENABLE_GROUP)[TITLE]],
      [TIMEFRAME_GROUP, objectField(found, TIMEFRAME_GROUP)[TITLE]],
      [LOCK_GROUP, objectField(found, LOCK_GROUP)[TITLE]],
      [SUMMARY_GROUP, objectField(found, SUMMARY_GROUP)[TITLE]],
      [LOCK_SPIN, objectField(found, LOCK_SPIN)[ROW_LABEL]],
      [PHANTOM_GROUP, objectField(found, PHANTOM_GROUP)[TITLE]],
      [LOCKS_GROUP, objectField(found, LOCKS_GROUP)[TITLE]]
    ];
    listField(found, SUMMARY_ROWS).forEach(function (row) {
      (Array.isArray(row) ? row : []).slice(ZERO, STEP + STEP).forEach(function (one) {
        words.push([SUMMARY_ROWS, one]);
      });
    });
    tableKinds().forEach(function (kind) {
      var table = objectField(found, planFor(kind).table);
      listField(table, COLUMNS).forEach(function (one) {
        words.push([kind, one]);
      });
      listField(table, ROWS).forEach(function (row, at) {
        (Array.isArray(row) ? row : []).forEach(function (one) {
          words.push([kind + ROW_AT + String(at), one]);
        });
      });
    });
    timeframeItems().forEach(function (one) {
      (Array.isArray(one) ? one : []).forEach(function (value) {
        if (typeof value === "string") {
          words.push([TIMEFRAME_COMBO, value]);
        }
      });
    });
    words.push([TIMEFRAME_COMBO, timeframeRefusal()]);
    return words;
  }

  function checkMarkup(found) {
    wordsDrawn(found).forEach(function (one) {
      var where = one.slice().shift();
      var value = one.slice().pop();
      if (carriesMarkup(value)) {
        tabFaults.push(fault(where, MARKUP_FAULT, MARKUP_FAULT, MARKUP_OPEN));
      }
    });
  }

  function element() {
    return global.React.createElement.apply(null, arguments);
  }

  // noteStyle keeps the newline a wrapped Qt label breaks on.
  function noteStyle(note) {
    var style = styleOf(note[STYLE_SHEET]);
    style.whiteSpace = note[WORD_WRAP] === true ? PRE_WRAP : PRE;
    return style;
  }

  function Note(props) {
    var note = objectField(props.model, props.field);
    var noteProps = {
      className: TAB_CLASS,
      style: noteStyle(note),
      hidden: props.hides === true && note[SHOWN] !== true
    };
    noteProps[PART_ATTR] = props.part;
    noteProps[SHOWN_ATTR] = text(props.hides === true ? note[SHOWN] : undefined);
    noteProps[WRAP_ATTR] = text(note[WORD_WRAP]);
    return element(DIV_TAG, noteProps, text(note[TEXT]));
  }

  function GroupTitle(props) {
    var titleProps = { className: TAB_CLASS };
    titleProps[PART_ATTR] = props.part;
    return element(SPAN_TAG, titleProps, text(props.words));
  }

  function EnableGroup(props) {
    var found = props.model;
    var check = objectField(found, ENABLE_CHECK);
    var groupProps = {
      className: TAB_CLASS,
      style: { display: FLEX, flexDirection: COLUMN_DIRECTION }
    };
    groupProps[PART_ATTR] = ENABLE_GROUP_PART;
    var rowProps = {
      className: TAB_CLASS,
      style: { display: FLEX, flexDirection: ROW_DIRECTION, alignItems: CENTER }
    };
    rowProps[PART_ATTR] = ENABLE_ROW_PART;
    var boxProps = {
      className: TAB_CLASS,
      type: CHECKBOX_TYPE,
      checked: check[CHECKED] === true,
      onChange: function (event) {
        pressEnable(event.target.checked, props.onEnable);
      }
    };
    boxProps[PART_ATTR] = ENABLE_CHECK_PART;
    boxProps[CHECKED_ATTR] = text(check[CHECKED]);
    boxProps[ACTION_ATTR] = label(action(ENABLE_TOGGLED));
    boxProps[STEP_ATTR] = text(stepFor(ENABLE_TOGGLED));
    boxProps[ARIA_LABEL] = label(check[TEXT]);
    var wordsProps = { className: TAB_CLASS };
    wordsProps[PART_ATTR] = ENABLE_TEXT_PART;
    return element(
      DIV_TAG,
      groupProps,
      element(GroupTitle, {
        key: ENABLE_TITLE_PART,
        part: ENABLE_TITLE_PART,
        words: objectField(found, ENABLE_GROUP)[TITLE]
      }),
      element(
        DIV_TAG,
        rowProps,
        element(INPUT_TAG, boxProps),
        element(SPAN_TAG, wordsProps, text(check[TEXT]))
      )
    );
  }

  function TimeframeOption(props) {
    var one = props.one;
    var optionProps = {
      className: TAB_CLASS,
      value: text(one.name),
      disabled: !one.supported,
      title: label(one.tooltip)
    };
    optionProps[PART_ATTR] = TIMEFRAME_OPTION_PART;
    optionProps[KEY_ATTR] = text(one.name);
    optionProps[ENABLED_ATTR] = String(one.supported);
    return element(OPTION_TAG, optionProps, text(one.name));
  }

  function TimeframeGroup(props) {
    var found = props.model;
    var combo = objectField(found, TIMEFRAME_COMBO);
    var groupProps = {
      className: TAB_CLASS,
      style: { display: FLEX, flexDirection: COLUMN_DIRECTION }
    };
    groupProps[PART_ATTR] = TIMEFRAME_GROUP_PART;
    groupProps[COUNT_ATTR] = String(timeframeItems().length);
    var rowProps = {
      className: TAB_CLASS,
      style: { display: FLEX, flexDirection: ROW_DIRECTION, alignItems: CENTER }
    };
    rowProps[PART_ATTR] = TIMEFRAME_ROW_PART;
    var labelProps = { className: TAB_CLASS };
    labelProps[PART_ATTR] = TIMEFRAME_LABEL_PART;
    var selectProps = {
      className: TAB_CLASS,
      value: timeframeCurrent(),
      title: label(combo[TOOLTIP]),
      onChange: function (event) {
        pressTimeframe(event.target.value, props.onTimeframe);
      }
    };
    selectProps[PART_ATTR] = TIMEFRAME_SELECT_PART;
    selectProps[VALUE_ATTR] = timeframeCurrent();
    selectProps[PARENT_ATTR] = text(combo[PARENT]);
    selectProps[ACTION_ATTR] = label(action(TIMEFRAME_PICKED));
    selectProps[STEP_ATTR] = text(stepFor(TIMEFRAME_PICKED));
    selectProps[ARIA_LABEL] = label(combo[TOOLTIP]);
    var refusalProps = { className: TAB_CLASS };
    refusalProps[PART_ATTR] = TIMEFRAME_REFUSAL_PART;
    refusalProps[SHOWN_ATTR] = String(timeframeRefusal() !== EMPTY);
    var drawn = timeframeNames().map(function (name) {
      return element(TimeframeOption, {
        key: String(name),
        one: timeframeNamed(name)
      });
    });
    return element(
      DIV_TAG,
      groupProps,
      element(GroupTitle, {
        key: TIMEFRAME_TITLE_PART,
        part: TIMEFRAME_TITLE_PART,
        words: objectField(found, TIMEFRAME_GROUP)[TITLE]
      }),
      element(Note, {
        key: TIMEFRAME_HINT_PART,
        part: TIMEFRAME_HINT_PART,
        model: found,
        field: TIMEFRAME_HINT
      }),
      element(
        DIV_TAG,
        rowProps,
        element(SPAN_TAG, labelProps, text(combo[ROW_LABEL])),
        element(SELECT_TAG, selectProps, drawn)
      ),
      element(SPAN_TAG, refusalProps, timeframeRefusal())
    );
  }

  function LockGroup(props) {
    var found = props.model;
    var spin = objectField(found, LOCK_SPIN);
    var groupProps = {
      className: TAB_CLASS,
      style: { display: FLEX, flexDirection: COLUMN_DIRECTION }
    };
    groupProps[PART_ATTR] = LOCK_GROUP_PART;
    groupProps[HOST_ATTR] = text(objectField(found, FORMS)[CONFIGURED_BY_HOST]);
    var rowProps = {
      className: TAB_CLASS,
      style: { display: FLEX, flexDirection: ROW_DIRECTION, alignItems: CENTER }
    };
    rowProps[PART_ATTR] = LOCK_ROW_PART;
    var labelProps = { className: TAB_CLASS };
    labelProps[PART_ATTR] = LOCK_LABEL_PART;
    var spinProps = {
      className: TAB_CLASS,
      type: NUMBER_TYPE,
      min: text(spin[MINIMUM]),
      max: text(spin[MAXIMUM]),
      value: numberOr(spin[VALUE], ZERO),
      title: label(spin[TOOLTIP]),
      onChange: function (event) {
        pressLock(Number(event.target.value), props.onLock);
      }
    };
    spinProps[PART_ATTR] = LOCK_SPIN_PART;
    spinProps[VALUE_ATTR] = text(spin[VALUE]);
    spinProps[MATCHED_ATTR] = String(spin[VALUE] === spin[REQUESTED]);
    spinProps[ACTION_ATTR] = label(action(LOCK_MOVED));
    spinProps[STEP_ATTR] = text(stepFor(LOCK_MOVED));
    spinProps[ARIA_LABEL] = label(spin[ROW_LABEL]);
    return element(
      DIV_TAG,
      groupProps,
      element(GroupTitle, {
        key: LOCK_TITLE_PART,
        part: LOCK_TITLE_PART,
        words: objectField(found, LOCK_GROUP)[TITLE]
      }),
      element(
        DIV_TAG,
        rowProps,
        element(SPAN_TAG, labelProps, text(spin[ROW_LABEL])),
        element(INPUT_TAG, spinProps)
      )
    );
  }

  function SummaryRow(props) {
    var row = Array.isArray(props.row) ? props.row : [];
    var name = row.length ? row[ZERO] : undefined;
    var sheet = summarySheet(name);
    var rowProps = {
      className: TAB_CLASS,
      style: { display: FLEX, flexDirection: ROW_DIRECTION }
    };
    rowProps[PART_ATTR] = SUMMARY_ROW_PART;
    rowProps[KEY_ATTR] = text(name);
    rowProps[INDEX_ATTR] = text(props.at);
    var labelProps = { className: TAB_CLASS };
    labelProps[PART_ATTR] = SUMMARY_LABEL_PART;
    labelProps[KEY_ATTR] = text(name);
    var valueProps = { className: TAB_CLASS, style: styleOf(sheet) };
    valueProps[PART_ATTR] = SUMMARY_VALUE_PART;
    valueProps[KEY_ATTR] = text(name);
    valueProps[PAINTED_ATTR] = String(Boolean(declarations(sheet).length));
    return element(
      DIV_TAG,
      rowProps,
      element(SPAN_TAG, labelProps, text(name)),
      element(SPAN_TAG, valueProps, text(summaryValue(name)))
    );
  }

  function SummaryGroup(props) {
    var found = props.model;
    var groupProps = {
      className: TAB_CLASS,
      style: { display: FLEX, flexDirection: COLUMN_DIRECTION }
    };
    groupProps[PART_ATTR] = SUMMARY_GROUP_PART;
    groupProps[COUNT_ATTR] = String(summaryRows().length);
    groupProps[HOST_ATTR] = text(objectField(found, FORMS)[CONFIGURED_BY_HOST]);
    groupProps[MATCHED_ATTR] = text(objectField(found, FORMS)[CONFIGURED]);
    var drawn = summaryRows().map(function (row, at) {
      return element(SummaryRow, { key: String(at), row: row, at: at });
    });
    return element(
      DIV_TAG,
      groupProps,
      element(GroupTitle, {
        key: SUMMARY_TITLE_PART,
        part: SUMMARY_TITLE_PART,
        words: objectField(found, SUMMARY_GROUP)[TITLE]
      }),
      drawn
    );
  }

  function HeaderCell(props) {
    var headProps = { className: TAB_CLASS, style: { whiteSpace: NOWRAP } };
    headProps[PART_ATTR] = props.part;
    headProps[COLUMN_ATTR] = text(props.at);
    headProps[KEY_ATTR] = text(props.name);
    headProps[ARIA_LABEL] = label(props.name);
    return element(HEAD_CELL_TAG, headProps, text(props.name));
  }

  function StateCell(props) {
    var value = cellColour(props.kind, props.at, props.column);
    var cellProps = { className: TAB_CLASS, style: cellStyle(value) };
    cellProps[PART_ATTR] = props.parts.cell;
    cellProps[COLUMN_ATTR] = text(props.column);
    cellProps[KEY_ATTR] = text(columnsOf(props.kind)[props.column]);
    cellProps[PAINTED_ATTR] = String(isPainted(value));
    return element(CELL_TAG, cellProps, text(cellsOf(props.kind, props.at)[props.column]));
  }

  // Qt numbers every table row down its own left edge, from one.
  function StateRow(props) {
    var parts = props.parts;
    var rowProps = { className: TAB_CLASS };
    rowProps[PART_ATTR] = parts.row;
    rowProps[ROW_ATTR] = text(props.at);
    rowProps[NAME_ATTR] = text(cellsOf(props.kind, props.at)[ZERO]);
    var drawn = [];
    if (props.numbered) {
      var numberProps = { className: TAB_CLASS };
      numberProps[PART_ATTR] = parts.number;
      numberProps[ROW_ATTR] = text(props.at);
      drawn.push(element(HEAD_CELL_TAG, numberProps, String(props.at + STEP)));
    }
    columnsOf(props.kind).forEach(function (name, column) {
      drawn.push(
        element(StateCell, {
          key: String(column),
          kind: props.kind,
          parts: parts,
          at: props.at,
          column: column
        })
      );
    });
    return element(ROW_TAG, rowProps, drawn);
  }

  function StateTable(props) {
    var kind = props.kind;
    var parts = planFor(kind).parts;
    var table = tableBag(kind);
    var group = groupBag(kind);
    var rules = objectField(props.model, TABLE_RULES);
    var numbered = rules[VERTICAL_HEADER_VISIBLE] === true;
    var groupProps = {
      className: TAB_CLASS,
      style: { display: FLEX, flexDirection: COLUMN_DIRECTION },
      hidden: group[SHOWN] !== true
    };
    groupProps[PART_ATTR] = parts.group;
    groupProps[NAME_ATTR] = kind;
    groupProps[SHOWN_ATTR] = text(group[SHOWN]);
    groupProps[COUNT_ATTR] = text(table[ROW_COUNT]);
    // Qt clips the table at its own ceiling, so the box scrolls instead.
    var boxProps = {
      className: TAB_CLASS,
      style: { maxHeight: length(table[MAX_HEIGHT_PX]), overflow: AUTO }
    };
    boxProps[PART_ATTR] = parts.box;
    var tableProps = {
      className: TAB_CLASS,
      style: { tableLayout: AUTO, width: FULL, borderCollapse: COLLAPSE }
    };
    tableProps[PART_ATTR] = parts.table;
    tableProps[ALTERNATING_ATTR] = text(rules[ALTERNATING_ROW_COLORS]);
    tableProps[RESIZE_ATTR] = text(rules[HEADER_RESIZE_MODE]);
    tableProps[EDIT_ATTR] = text(rules[EDIT_TRIGGERS]);
    tableProps[GUTTER_ATTR] = String(numbered);
    var headProps = { className: TAB_CLASS };
    headProps[PART_ATTR] = parts.head;
    var headRowProps = { className: TAB_CLASS };
    headRowProps[PART_ATTR] = parts.headRow;
    headRowProps[COUNT_ATTR] = text(table[COLUMN_COUNT]);
    var bodyProps = { className: TAB_CLASS };
    bodyProps[PART_ATTR] = parts.body;
    bodyProps[COUNT_ATTR] = text(table[ROW_COUNT]);
    var headCells = [];
    if (numbered) {
      var cornerProps = { className: TAB_CLASS };
      cornerProps[PART_ATTR] = parts.corner;
      headCells.push(element(HEAD_CELL_TAG, cornerProps, null));
    }
    columnsOf(kind).forEach(function (name, at) {
      headCells.push(
        element(HeaderCell, {
          key: String(at),
          part: parts.headerCell,
          name: name,
          at: at
        })
      );
    });
    return element(
      DIV_TAG,
      groupProps,
      element(GroupTitle, { key: parts.title, part: parts.title, words: group[TITLE] }),
      element(
        DIV_TAG,
        boxProps,
        element(
          TABLE_TAG,
          tableProps,
          element(
            HEAD_TAG,
            headProps,
            element(ROW_TAG, headRowProps, headCells)
          ),
          element(
            BODY_TAG,
            bodyProps,
            rowsOf(kind).map(function (one, at) {
              return element(StateRow, {
                key: String(at),
                kind: kind,
                parts: parts,
                at: at,
                numbered: numbered
              });
            })
          )
        )
      )
    );
  }

  function ChangeLine(props) {
    var one = Array.isArray(props.change) ? props.change : [];
    var lineProps = { className: TAB_CLASS };
    lineProps[PART_ATTR] = CHANGE_LINE_PART;
    lineProps[KEY_ATTR] = text(one[ZERO]);
    lineProps[INDEX_ATTR] = text(props.at);
    lineProps[VALUE_ATTR] = text(JSON.stringify(one[STEP]));
    return element(DIV_TAG, lineProps, null);
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
    tabProps[MARGINS_ATTR] = text(box[MARGINS_SET]);
    tabProps[COUNT_ATTR] = String(changes().length);
    tabProps[ARIA_LABEL] = label(found[ACCESSIBLE_NAME]);
    var drawn = [
      element(Note, {
        key: INFO_NOTE_PART,
        part: INFO_NOTE_PART,
        model: found,
        field: INFO_LABEL
      }),
      element(EnableGroup, {
        key: ENABLE_GROUP_PART,
        model: found,
        onEnable: props.onEnable
      }),
      element(TimeframeGroup, {
        key: TIMEFRAME_GROUP_PART,
        model: found,
        onTimeframe: props.onTimeframe
      }),
      element(LockGroup, { key: LOCK_GROUP_PART, model: found, onLock: props.onLock }),
      element(SummaryGroup, { key: SUMMARY_GROUP_PART, model: found })
    ];
    tableKinds().forEach(function (kind) {
      drawn.push(
        element(StateTable, { key: kind, kind: kind, model: found })
      );
    });
    drawn.push(
      element(Note, {
        key: EMPTY_NOTE_PART,
        part: EMPTY_NOTE_PART,
        model: found,
        field: EMPTY_LABEL,
        hides: true
      })
    );
    changes().forEach(function (one, at) {
      drawn.push(
        element(ChangeLine, { key: CHANGE_LINE_PART + String(at), change: one, at: at })
      );
    });
    if (found[STRETCH_SHOWN] === true) {
      var stretchProps = { className: TAB_CLASS, style: { flex: AUTO } };
      stretchProps[PART_ATTR] = STRETCH_PART;
      drawn.push(element(DIV_TAG, stretchProps, null));
    }
    return element(DIV_TAG, tabProps, drawn);
  }

  function hasBridge() {
    return Boolean(global.acervator) && typeof global.acervator.call === "function";
  }

  // press records the setting moved, the step sent and its own argument.
  function press(name, step) {
    lastPress = {
      name: name,
      step: step.slice().shift(),
      argument: step.slice(STEP),
      action: action(name)
    };
    var params = {};
    params[STEPS] = [step];
    dispatched.push({ action: action(name), params: params });
    if (hasBridge()) {
      global.acervator.call(METHOD, params);
    }
    return lastPress;
  }

  function pressEnable(checked, then) {
    var found = press(ENABLE_TOGGLED, [stepFor(ENABLE_TOGGLED), checked === true]);
    if (typeof then === "function") {
      then(checked === true);
    }
    return found;
  }

  function pressTimeframe(name, then) {
    var one = timeframeNamed(name);
    if (one === undefined || !one.supported) {
      return null;
    }
    var found = press(TIMEFRAME_PICKED, [stepFor(TIMEFRAME_PICKED), one.name]);
    if (typeof then === "function") {
      then(one.name);
    }
    return found;
  }

  function pressLock(value, then) {
    var kept = numberOr(value, ZERO);
    var found = press(LOCK_MOVED, [stepFor(LOCK_MOVED), kept]);
    if (typeof then === "function") {
      then(kept);
    }
    return found;
  }

  function pressed() {
    return lastPress;
  }

  function sent() {
    return dispatched.slice();
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

  function heldFieldCount(found) {
    return DECLARED_FIELDS.filter(function (name) {
      return owns(found, name);
    }).length;
  }

  function report() {
    var found = held.model;
    var phantom = objectField(found, PHANTOM_TABLE);
    var locks = objectField(found, LOCKS_TABLE);
    return {
      declared: {
        fields: DECLARED_FIELDS.length,
        timeframes: listField(found, TIMEFRAMES).length,
        phantoms: phantom[ROW_COUNT],
        locks: locks[ROW_COUNT],
        columns: phantom[COLUMN_COUNT],
        lock_columns: locks[COLUMN_COUNT],
        actions: ACTION_NAMES.length,
        tables: TABLE_PLAN.length
      },
      held: {
        fields: heldFieldCount(found),
        timeframes: timeframeItems().length,
        phantoms: rowsOf(PHANTOM_KIND).length,
        locks: rowsOf(LOCKS_KIND).length,
        columns: columnsOf(PHANTOM_KIND).length,
        lock_columns: columnsOf(LOCKS_KIND).length,
        actions: Object.keys(objectField(found, ACTIONS)).length,
        tables: tableKinds().length
      },
      faults: tabFaults.slice()
    };
  }

  function setTab(found) {
    lastPress = null;
    dispatched = [];
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
    checkTimeframes(found);
    checkSummary(found);
    checkLockSpin(found);
    checkColours(found);
    checkBagOrder(found);
    checkMarkup(found);
    return report();
  }

  // Asks METHOD once, clearing asked so a refused first ask is retried.
  function loadTab(params) {
    if (asked !== null) {
      return asked;
    }
    if (!hasBridge()) {
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

  function bagNames() {
    return DECLARED_BAGS.slice();
  }

  function listNames() {
    return DECLARED_LISTS.slice();
  }

  function bagKeys(name) {
    return Object.keys(bag(name));
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
        model: model(),
        onEnable: wired.onEnable,
        onTimeframe: wired.onTimeframe,
        onLock: wired.onLock
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
    dispatched = [];
  }

  global.acervatorSetSimPhantomBotsTab = setTab;
  global.acervatorLoadSimPhantomBotsTab = loadTab;
  global.acervatorSimPhantomBotsTab = {
    method: METHOD,
    spacePart: PAGE_PART,
    pagePart: PAGE_PART,
    Tab: Tab,
    EnableGroup: EnableGroup,
    TimeframeGroup: TimeframeGroup,
    LockGroup: LockGroup,
    SummaryGroup: SummaryGroup,
    StateTable: StateTable,
    payload: payload,
    declaredNames: declaredNames,
    bagNames: bagNames,
    listNames: listNames,
    field: field,
    bag: bag,
    list: list,
    bagKeys: bagKeys,
    actionNames: actionNames,
    action: action,
    stepFor: stepFor,
    tableKinds: tableKinds,
    columnsOf: columnsOf,
    rowsOf: rowsOf,
    cellsOf: cellsOf,
    cellColour: cellColour,
    cellStyle: cellStyle,
    isPainted: isPainted,
    noCellColour: noCellColour,
    timeframeCombo: timeframeCombo,
    timeframeItems: timeframeItems,
    timeframeNames: timeframeNames,
    timeframeNamed: timeframeNamed,
    timeframeCurrent: timeframeCurrent,
    timeframeRefusal: timeframeRefusal,
    isAllowed: isAllowed,
    pickedTimeframes: pickedTimeframes,
    summaryRows: summaryRows,
    summaryRowNamed: summaryRowNamed,
    summaryValue: summaryValue,
    summarySheet: summarySheet,
    changes: changes,
    changedFields: changedFields,
    calls: calls,
    press: press,
    pressEnable: pressEnable,
    pressTimeframe: pressTimeframe,
    pressLock: pressLock,
    pressed: pressed,
    sent: sent,
    styleOf: styleOf,
    declarations: declarations,
    noteStyle: noteStyle,
    colour: colour,
    isSwappedAlpha: isSwappedAlpha,
    isReorderedKey: isReorderedKey,
    carriesMarkup: carriesMarkup,
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
