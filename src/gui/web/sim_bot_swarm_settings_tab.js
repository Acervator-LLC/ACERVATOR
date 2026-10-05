// The Simulator's fork of bot_swarm_settings_tab.js under the Simulator's names;
// it answers the sim_bot_swarm_tab.state payload the Sim window pushes.
// Draws the Bot Swarm tab of the Live Bot Settings window from its payload.
(function (global) {
  "use strict";

  var METHOD = "sim_bot_swarm_tab.state";

  var ACCESSIBLE_NAME = "accessible_name";
  var ACTIONS = "actions";
  var ACTIVE = "active";
  var ATTRIBUTES = "attributes";
  var BUS_EMITS = "bus_emits";
  var BUS_TOPICS = "bus_topics";
  var CALL_NAMES = "call_names";
  var CALLS = "calls";
  var COLOURS = "colours";
  var CONTAINER = "container";
  var EMPTY_LABEL = "empty_label";
  var FIELDS = "fields";
  var FORMATS = "formats";
  var INBOUND_TABLE = "inbound_table";
  var KEYS = "keys";
  var LABELS = "labels";
  var MARKS = "marks";
  var METHOD_FIELD = "method";
  var NOT_ACTIVE_LABEL = "not_active_label";
  var OUTBOUND_TABLE = "outbound_table";
  var PENDING_TABLE = "pending_table";
  var PROVENANCE_GROUP = "provenance_group";
  var SIGNALS = "signals";
  var STYLES = "styles";
  var SUMMARY_GROUP = "summary_group";
  var TAB_LABEL = "tab_label";
  var TABLES = "tables";
  var TEXTS = "texts";
  var THREADS = "threads";
  var THRESHOLDS = "thresholds";
  var TIMER_DELAYS_MS = "timer_delays_ms";
  var TIMERS = "timers";
  var TITLES = "titles";
  var TRANSACTIONS_TABLE = "transactions_table";

  // Every top-level name the bot_swarm_tab.state payload carries.
  var DECLARED_FIELDS = [
    ACCESSIBLE_NAME,
    ACTIONS,
    ACTIVE,
    ATTRIBUTES,
    BUS_EMITS,
    BUS_TOPICS,
    CALL_NAMES,
    CALLS,
    COLOURS,
    CONTAINER,
    EMPTY_LABEL,
    FIELDS,
    FORMATS,
    INBOUND_TABLE,
    KEYS,
    LABELS,
    MARKS,
    METHOD_FIELD,
    NOT_ACTIVE_LABEL,
    OUTBOUND_TABLE,
    PENDING_TABLE,
    PROVENANCE_GROUP,
    SIGNALS,
    STYLES,
    SUMMARY_GROUP,
    TAB_LABEL,
    TABLES,
    TEXTS,
    THREADS,
    THRESHOLDS,
    TIMER_DELAYS_MS,
    TIMERS,
    TITLES,
    TRANSACTIONS_TABLE
  ];

  var DECLARED_BAGS = [
    ACTIONS,
    ATTRIBUTES,
    COLOURS,
    CONTAINER,
    EMPTY_LABEL,
    FIELDS,
    FORMATS,
    INBOUND_TABLE,
    KEYS,
    LABELS,
    MARKS,
    NOT_ACTIVE_LABEL,
    OUTBOUND_TABLE,
    PENDING_TABLE,
    PROVENANCE_GROUP,
    STYLES,
    SUMMARY_GROUP,
    TABLES,
    TEXTS,
    THRESHOLDS,
    TIMERS,
    TITLES,
    TRANSACTIONS_TABLE
  ];

  var DECLARED_LISTS = [
    BUS_EMITS,
    BUS_TOPICS,
    CALL_NAMES,
    CALLS,
    SIGNALS,
    THREADS,
    TIMER_DELAYS_MS
  ];

  // The four wire tables, as a list, because a bag would lose their order.
  var WIRE_TABLES = [
    OUTBOUND_TABLE,
    INBOUND_TABLE,
    PENDING_TABLE,
    TRANSACTIONS_TABLE
  ];

  var SHOWN = "shown";
  var TITLE = "title";
  var HEADERS = "headers";
  var ROWS = "rows";
  var COUNT = "count";
  var DIRECTION_COLOURS = "direction_colours";
  var STYLE_SHEET = "style_sheet";
  var TEXT_FIELD = "text";
  var WORD_WRAP = "word_wrap";
  var WORD_WRAPS = "word_wraps";
  var ROW_STYLES = "styles";
  var BREAKDOWN = "breakdown";
  var PREDOMINANT_REFUSED = "predominant_refused";
  var FORMS_CONFIGURED = "forms_configured";
  var CONFIGURED_BY_HOST = "configured_by_host";
  var SPACING_PX = "spacing_px";
  var MARGINS_SET = "margins_set";
  var LEAD = "lead";
  var STRONG = "strong";
  var BREAKS = "breaks";
  var TAIL = "tail";
  var STRONG_OPEN = "strong_open";
  var STRONG_CLOSE = "strong_close";
  var LINE_BREAK = "line_break";
  var STRONG_WEIGHT = "strong_weight";
  var PROVENANCE_JOIN = "provenance_join";
  var PROVENANCE_LABEL = "provenance";
  var OUT_DIRECTION = "out_direction";
  var IN_DIRECTION = "in_direction";
  var ALTERNATING_ROWS = "alternating_rows";
  var RESIZE_MODE = "resize_mode";
  var EDIT_TRIGGERS = "edit_triggers";
  var WIRE_MAX_HEIGHT_PX = "wire_max_height_px";
  var EVENTS_MAX_HEIGHT_PX = "transactions_max_height_px";

  // The four pieces the not-active line is written from, in written order.
  var MARK_PIECES = [LEAD, STRONG, BREAKS, TAIL];

  // The two tables whose first cell names a bot, so a repeat is a fault.
  var NAMED_TABLES = [OUTBOUND_TABLE, INBOUND_TABLE];

  var MISSING_FAULT = "missing";
  var NULL_FAULT = "null";
  var NOT_AN_OBJECT_FAULT = "not-an-object";
  var NOT_A_BAG_FAULT = "not-a-bag";
  var NOT_A_LIST_FAULT = "not-a-list";
  var SHORT_LIST_FAULT = "short-list";
  var SWAPPED_ALPHA_FAULT = "swapped-alpha";
  var REORDERED_KEY_FAULT = "reordered-key";
  var DISAGREES_FAULT = "disagrees";
  var DUPLICATE_NAME_FAULT = "duplicate-name";
  var UNKNOWN_STEP_FAULT = "unknown-step";
  var MARKUP_FAULT = "markup";
  var NOT_CSS_FAULT = "not-css";

  var ROW_AT = "row:";
  var PATH_SPLIT = ".";
  var EMPTY = "";

  var NO_BRIDGE = "the preload bridge is not present";

  // Qt paints this gradient by name and no browser stylesheet runs it.
  var QT_ONLY = "qlineargradient";

  // MARKUP_OPEN starts a tag a Qt rich-text label reads as formatting.
  var MARKUP_OPEN = "<";

  var TAB_CLASS = "acervator-bot-swarm-settings";

  var DIV_TAG = "div";
  var SPAN_TAG = "span";
  var STRONG_TAG = "strong";
  var TABLE_TAG = "table";
  var HEAD_TAG = "thead";
  var BODY_TAG = "tbody";
  var ROW_TAG = "tr";
  var HEAD_CELL_TAG = "th";
  var CELL_TAG = "td";

  var TAB_PART = "bot-swarm-tab";
  var NOT_ACTIVE_PART = "not-active-note";
  var MARK_LEAD_PART = "mark-lead";
  var MARK_STRONG_PART = "mark-strong";
  var MARK_TAIL_PART = "mark-tail";
  var SUMMARY_GROUP_PART = "summary-group";
  var SUMMARY_TITLE_PART = "summary-group-title";
  var SUMMARY_ROW_PART = "summary-row";
  var SUMMARY_LABEL_PART = "summary-label";
  var SUMMARY_VALUE_PART = "summary-value";
  var PROVENANCE_GROUP_PART = "provenance-group";
  var PROVENANCE_TITLE_PART = "provenance-group-title";
  var PROVENANCE_ROW_PART = "provenance-row";
  var PROVENANCE_LABEL_PART = "provenance-label";
  var PROVENANCE_VALUE_PART = "provenance-value";
  var BREAKDOWN_ENTRY_PART = "breakdown-entry";
  var BREAKDOWN_JOIN_PART = "breakdown-join";
  var WIRE_PANEL_PART = "wire-panel";
  var WIRE_TITLE_PART = "wire-title";
  var WIRE_TABLE_PART = "wire-table";
  var HEAD_PART = "table-head";
  var HEAD_ROW_PART = "head-row";
  var HEADER_CELL_PART = "header-cell";
  var BODY_PART = "table-body";
  var WIRE_ROW_PART = "wire-row";
  var WIRE_CELL_PART = "wire-cell";
  var EMPTY_NOTE_PART = "empty-note";
  var STEP_PART = "tab-step";

  // PAGE_PART is the space the Live Bot Settings window leaves for this tab.
  var PAGE_PART = "bot-swarm-page";

  var PART_ATTR = "data-part";
  var KEY_ATTR = "data-key";
  var NAME_ATTR = "data-name";
  var INDEX_ATTR = "data-index";
  var COLUMN_ATTR = "data-column";
  var ROW_ATTR = "data-row";
  var COUNT_ATTR = "data-count";
  var SHOWN_ATTR = "data-shown";
  var WRAP_ATTR = "data-word-wrap";
  var HOST_ATTR = "data-configured-by-host";
  var MARGINS_ATTR = "data-margins-set";
  var PAINTED_ATTR = "data-painted";
  var STYLED_ATTR = "data-styled";
  var REFUSED_ATTR = "data-refused";
  var MATCHED_ATTR = "data-matched";
  var TABLE_ATTR = "data-table";
  var ALTERNATING_ATTR = "data-alternating";
  var RESIZE_ATTR = "data-resize-mode";
  var EDIT_ATTR = "data-edit-triggers";
  var HEIGHT_ATTR = "data-max-height";
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
  var NEWLINE = decodeURIComponent("%0A");

  var PX = "px";
  var FLEX = "flex";
  var ROW_DIRECTION = "row";
  var COLUMN_DIRECTION = "column";
  var FIXED = "fixed";
  var FULL = "100%";
  var COLLAPSE = "collapse";
  var NOWRAP = "nowrap";
  var NORMAL = "normal";
  var AUTO = "auto";
  var STRING_KIND = "string";
  var NUMBER_KIND = "number";
  var BOOLEAN_KIND = "boolean";
  var FUNCTION_KIND = "function";

  var ZERO = Number(EMPTY);
  var STEP = Number(true);
  var SECOND = STEP + STEP;

  var held = null;
  var tabFaults = [];
  var loadFault = null;
  var asked = null;
  var roots = [];

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

  function note(where, field, kind, detail) {
    tabFaults.push(fault(where, field, kind, detail));
  }

  function text(value) {
    return value === null || value === undefined ? undefined : String(value);
  }

  function label(value) {
    return typeof value === STRING_KIND && value.length ? value : undefined;
  }

  function length(value) {
    return value === null || value === undefined ? undefined : String(value) + PX;
  }

  function carries(value, mark) {
    return String(value).indexOf(mark) >= ZERO;
  }

  function repeated(piece, times) {
    var found = EMPTY;
    var count = typeof times === NUMBER_KIND ? times : ZERO;
    var at = ZERO;
    while (at < count) {
      found += String(piece);
      at += STEP;
    }
    return found;
  }

  // True for a colour written with eight hex digits, which Qt reads alpha-first.
  function isSwappedAlpha(value) {
    return (
      typeof value === STRING_KIND &&
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
    if (!api || typeof api.colour !== FUNCTION_KIND) {
      return text(value);
    }
    return api.colour(value);
  }

  // header_strip.js owns the rule that turns a Qt style sheet into CSS.
  function styleOf(sheet) {
    var api = global.acervatorHeader;
    if (!api || typeof api.styleOf !== FUNCTION_KIND) {
      return {};
    }
    return api.styleOf(sheet);
  }

  function declarations(sheet) {
    var api = global.acervatorHeader;
    if (!api || typeof api.declarations !== FUNCTION_KIND) {
      return [];
    }
    return api.declarations(sheet);
  }

  // A selector carrying a colon names a state Qt paints on hover.
  function stateRules(sheet) {
    var api = global.acervatorHeader;
    if (!api || typeof api.stateRules !== FUNCTION_KIND) {
      return [];
    }
    return api.stateRules(sheet);
  }

  // Every declaration of one sheet, its state blocks read as well as its base.
  function wholeSheet(sheet) {
    var found = declarations(sheet).slice();
    stateRules(sheet).forEach(function (rule) {
      declarations(rule.body).forEach(function (one) {
        found.push(one);
      });
    });
    return found;
  }

  function model() {
    return held === null ? null : held.model;
  }

  function notActive() {
    return objectField(model(), NOT_ACTIVE_LABEL);
  }

  function summaryGroup() {
    return objectField(model(), SUMMARY_GROUP);
  }

  function provenanceGroup() {
    return objectField(model(), PROVENANCE_GROUP);
  }

  function summaryRows() {
    return listField(summaryGroup(), ROWS);
  }

  function summaryStyle(at) {
    return listField(summaryGroup(), ROW_STYLES)[at];
  }

  function provenanceRows() {
    return listField(provenanceGroup(), ROWS);
  }

  function provenanceStyle(at) {
    return listField(provenanceGroup(), ROW_STYLES)[at];
  }

  function provenanceWrap(at) {
    return listField(provenanceGroup(), WORD_WRAPS)[at];
  }

  // One row found by its own label, never by where it sits.
  function rowNamed(drawn, name) {
    var found;
    drawn.forEach(function (row) {
      if (Array.isArray(row) && row.length && row[ZERO] === name) {
        found = row;
      }
    });
    return found;
  }

  function summaryValue(name) {
    var row = rowNamed(summaryRows(), name);
    return Array.isArray(row) && row.length > STEP ? row[STEP] : undefined;
  }

  function provenanceValue(name) {
    var row = rowNamed(provenanceRows(), name);
    return Array.isArray(row) && row.length > STEP ? row[STEP] : undefined;
  }

  // Every row named by the label it carries, in the order it is drawn.
  function rowNames(drawn) {
    return drawn.map(function (row) {
      return text(Array.isArray(row) && row.length ? row[ZERO] : undefined);
    });
  }

  function labelNamed(name) {
    var bag = objectField(model(), LABELS);
    return owns(bag, name) ? bag[name] : undefined;
  }

  function textNamed(name) {
    var bag = objectField(model(), TEXTS);
    return owns(bag, name) ? bag[name] : undefined;
  }

  function colourNamed(name) {
    var bag = objectField(model(), COLOURS);
    return owns(bag, name) ? bag[name] : undefined;
  }

  function breakdown() {
    return listField(provenanceGroup(), BREAKDOWN);
  }

  // The funders the breakdown names, in the order it draws them.
  function breakdownSources() {
    return breakdown().map(function (one) {
      return text(Array.isArray(one) && one.length ? one[ZERO] : undefined);
    });
  }

  function breakdownFor(source) {
    var found;
    breakdown().forEach(function (one) {
      if (Array.isArray(one) && one.length && String(one[ZERO]) === String(source)) {
        found = one[STEP];
      }
    });
    return found;
  }

  // The joined line the breakdown entries build, in the order published.
  function breakdownLine() {
    var join = String(textNamed(PROVENANCE_JOIN));
    return breakdown()
      .map(function (one) {
        return String(Array.isArray(one) && one.length > STEP ? one[STEP] : EMPTY);
      })
      .join(join);
  }

  function tableNames() {
    return WIRE_TABLES.slice();
  }

  function tableBag(name) {
    return objectField(model(), name);
  }

  function headers(name) {
    return listField(tableBag(name), HEADERS).slice();
  }

  function tableRows(name) {
    return listField(tableBag(name), ROWS);
  }

  function rowCells(name, at) {
    var found = tableRows(name)[at];
    return Array.isArray(found) ? found : [];
  }

  // Every wire row named by the bot its first cell names.
  function wireNames(name) {
    return tableRows(name).map(function (row) {
      return text(Array.isArray(row) && row.length ? row[ZERO] : undefined);
    });
  }

  function wireRowNamed(name, wire) {
    var found;
    tableRows(name).forEach(function (row) {
      if (Array.isArray(row) && row.length && String(row[ZERO]) === String(wire)) {
        found = row;
      }
    });
    return found;
  }

  function directionColour(at) {
    return listField(tableBag(TRANSACTIONS_TABLE), DIRECTION_COLOURS)[at];
  }

  function markTags() {
    return objectField(model(), MARKS);
  }

  // The four pieces the not-active line is written from, in written order.
  function markPieces() {
    var note = notActive();
    return MARK_PIECES.map(function (name) {
      return note[name];
    });
  }

  // rebuiltNotActive names the marked-up line one set of pieces builds.
  function rebuiltNotActive() {
    var pieces = markPieces();
    var tags = markTags();
    return (
      String(pieces[ZERO]) +
      String(tags[STRONG_OPEN]) +
      String(pieces[STEP]) +
      String(tags[STRONG_CLOSE]) +
      repeated(tags[LINE_BREAK], pieces[SECOND]) +
      String(pieces[SECOND + STEP])
    );
  }

  function calls() {
    return listField(model(), CALLS).slice();
  }

  function callNames() {
    return listField(model(), CALL_NAMES).slice();
  }

  function checkFields(found) {
    DECLARED_FIELDS.forEach(function (name) {
      if (!owns(found, name)) {
        note(null, name, MISSING_FAULT, null);
      }
    });
    DECLARED_BAGS.forEach(function (name) {
      if (owns(found, name) && !isPlainObject(found[name])) {
        note(null, name, NOT_A_BAG_FAULT, kindOf(found[name]));
      }
    });
    DECLARED_LISTS.forEach(function (name) {
      if (owns(found, name) && !Array.isArray(found[name])) {
        note(null, name, NOT_A_LIST_FAULT, kindOf(found[name]));
      }
    });
    if (owns(found, METHOD_FIELD) && found[METHOD_FIELD] !== METHOD) {
      note(null, METHOD_FIELD, DISAGREES_FAULT, found[METHOD_FIELD]);
    }
  }

  function checkSteps(found) {
    var named = listField(found, CALL_NAMES);
    listField(found, CALLS).forEach(function (one, at) {
      if (named.indexOf(one) < ZERO) {
        note(ROW_AT + String(at), CALLS, UNKNOWN_STEP_FAULT, one);
      }
    });
  }

  function checkPairedList(where, field, drawn, paired, name) {
    if (paired.length !== drawn.length) {
      note(where, field, SHORT_LIST_FAULT, name + PATH_SPLIT + String(paired.length));
    }
  }

  function checkGroups(found) {
    var summary = objectField(found, SUMMARY_GROUP);
    checkPairedList(
      null,
      SUMMARY_GROUP,
      listField(summary, ROWS),
      listField(summary, ROW_STYLES),
      ROW_STYLES
    );
    var provenance = objectField(found, PROVENANCE_GROUP);
    checkPairedList(
      null,
      PROVENANCE_GROUP,
      listField(provenance, ROWS),
      listField(provenance, ROW_STYLES),
      ROW_STYLES
    );
    checkPairedList(
      null,
      PROVENANCE_GROUP,
      listField(provenance, ROWS),
      listField(provenance, WORD_WRAPS),
      WORD_WRAPS
    );
    [listField(summary, ROWS), listField(provenance, ROWS)].forEach(function (drawn) {
      var seen = {};
      rowNames(drawn).forEach(function (name, at) {
        if (owns(seen, String(name))) {
          note(ROW_AT + String(at), ROWS, DUPLICATE_NAME_FAULT, name);
        }
        seen[String(name)] = true;
      });
    });
  }

  function checkBreakdown(found) {
    var provenance = objectField(found, PROVENANCE_GROUP);
    var entries = listField(provenance, BREAKDOWN);
    var seen = {};
    entries.forEach(function (one, at) {
      if (!Array.isArray(one) || one.length !== SECOND) {
        note(ROW_AT + String(at), BREAKDOWN, NOT_A_LIST_FAULT, kindOf(one));
        return;
      }
      if (owns(seen, String(one[ZERO]))) {
        note(ROW_AT + String(at), BREAKDOWN, DUPLICATE_NAME_FAULT, one[ZERO]);
      }
      seen[String(one[ZERO])] = true;
    });
    if (!entries.length) {
      return;
    }
    var drawn = provenanceValue(labelNamed(PROVENANCE_LABEL));
    if (drawn !== undefined && breakdownLine() !== drawn) {
      note(null, BREAKDOWN, DISAGREES_FAULT, breakdownLine());
    }
  }

  function checkTables(found) {
    WIRE_TABLES.forEach(function (name) {
      var bag = objectField(found, name);
      var wide = listField(bag, HEADERS).length;
      var drawn = listField(bag, ROWS);
      if (owns(bag, COUNT) && bag[COUNT] !== drawn.length) {
        note(null, name, DISAGREES_FAULT, bag[COUNT]);
      }
      drawn.forEach(function (row, at) {
        if (!Array.isArray(row)) {
          note(ROW_AT + String(at), name, NOT_A_LIST_FAULT, kindOf(row));
          return;
        }
        if (row.length !== wide) {
          note(ROW_AT + String(at), name, SHORT_LIST_FAULT, row.length);
        }
      });
    });
    NAMED_TABLES.forEach(function (name) {
      var seen = {};
      wireNames(name).forEach(function (wire, at) {
        if (owns(seen, String(wire))) {
          note(ROW_AT + String(at), name, DUPLICATE_NAME_FAULT, wire);
        }
        seen[String(wire)] = true;
      });
    });
    var events = objectField(found, TRANSACTIONS_TABLE);
    checkPairedList(
      null,
      TRANSACTIONS_TABLE,
      listField(events, ROWS),
      listField(events, DIRECTION_COLOURS),
      DIRECTION_COLOURS
    );
  }

  function checkMarks(found) {
    var carried = objectField(found, NOT_ACTIVE_LABEL);
    MARK_PIECES.forEach(function (name) {
      if (!owns(carried, name)) {
        note(null, NOT_ACTIVE_LABEL, MISSING_FAULT, name);
      }
    });
    var listed = listField(carried, MARKS);
    if (listed.length !== MARK_PIECES.length) {
      note(null, MARKS, SHORT_LIST_FAULT, listed.length);
      return;
    }
    MARK_PIECES.forEach(function (name, at) {
      if (listed[at] !== carried[name]) {
        note(null, MARKS, DISAGREES_FAULT, name);
      }
    });
    if (rebuiltNotActive() !== carried[TEXT_FIELD]) {
      note(null, MARKS, DISAGREES_FAULT, TEXT_FIELD);
    }
  }

  function checkColour(where, field, value) {
    if (isSwappedAlpha(value)) {
      note(where, field, SWAPPED_ALPHA_FAULT, value);
    }
  }

  function sheetsOf(found) {
    var sheets = [
      { field: NOT_ACTIVE_LABEL, sheet: objectField(found, NOT_ACTIVE_LABEL)[STYLE_SHEET] },
      { field: EMPTY_LABEL, sheet: objectField(found, EMPTY_LABEL)[STYLE_SHEET] }
    ];
    Object.keys(objectField(found, STYLES)).forEach(function (name) {
      sheets.push({ field: STYLES, sheet: objectField(found, STYLES)[name] });
    });
    listField(objectField(found, SUMMARY_GROUP), ROW_STYLES).forEach(function (one, at) {
      sheets.push({ field: SUMMARY_GROUP, sheet: one, where: ROW_AT + String(at) });
    });
    listField(objectField(found, PROVENANCE_GROUP), ROW_STYLES).forEach(
      function (one, at) {
        sheets.push({ field: PROVENANCE_GROUP, sheet: one, where: ROW_AT + String(at) });
      }
    );
    return sheets;
  }

  function checkColours(found) {
    var bag = objectField(found, COLOURS);
    Object.keys(bag).forEach(function (name) {
      checkColour(null, COLOURS, bag[name]);
    });
    listField(objectField(found, TRANSACTIONS_TABLE), DIRECTION_COLOURS).forEach(
      function (value, at) {
        checkColour(ROW_AT + String(at), DIRECTION_COLOURS, value);
      }
    );
    sheetsOf(found).forEach(function (one) {
      checkColour(one.where || null, one.field, one.sheet);
      wholeSheet(one.sheet).forEach(function (written) {
        checkColour(one.where || null, one.field, written.value);
        if (carries(written.value, QT_ONLY)) {
          note(one.where || null, one.field, NOT_CSS_FAULT, written.property);
        }
      });
    });
  }

  function checkBagOrder(found) {
    DECLARED_BAGS.forEach(function (name) {
      Object.keys(objectField(found, name)).forEach(function (key) {
        if (isReorderedKey(key)) {
          note(null, name, REORDERED_KEY_FAULT, key);
        }
      });
    });
  }

  function checkMarkup(where, field, carried) {
    if (typeof carried === STRING_KIND && carries(carried, MARKUP_OPEN)) {
      note(where, field, MARKUP_FAULT, MARKUP_OPEN);
    }
  }

  // Every drawn word swept for the markup a Qt rich-text label would read.
  function checkDrawnMarkup(found) {
    [
      { field: SUMMARY_GROUP, drawn: listField(objectField(found, SUMMARY_GROUP), ROWS) },
      {
        field: PROVENANCE_GROUP,
        drawn: listField(objectField(found, PROVENANCE_GROUP), ROWS)
      }
    ].forEach(function (one) {
      one.drawn.forEach(function (row, at) {
        (Array.isArray(row) ? row : []).forEach(function (cell) {
          checkMarkup(ROW_AT + String(at), one.field, cell);
        });
      });
    });
    WIRE_TABLES.forEach(function (name) {
      listField(objectField(found, name), HEADERS).forEach(function (one) {
        checkMarkup(null, name, one);
      });
      listField(objectField(found, name), ROWS).forEach(function (row, at) {
        (Array.isArray(row) ? row : []).forEach(function (cell) {
          checkMarkup(ROW_AT + String(at), name, cell);
        });
      });
    });
    checkMarkup(null, EMPTY_LABEL, objectField(found, EMPTY_LABEL)[TEXT_FIELD]);
    MARK_PIECES.forEach(function (name) {
      checkMarkup(null, NOT_ACTIVE_LABEL, objectField(found, NOT_ACTIVE_LABEL)[name]);
    });
  }

  function element() {
    return global.React.createElement.apply(null, arguments);
  }

  // A bare colour carries no declaration, so it paints the text and nothing else.
  function paintedStyle(value) {
    if (value === undefined || value === null || value === EMPTY) {
      return {};
    }
    var written = declarations(value);
    if (!written.length) {
      return { color: colour(value) };
    }
    return styleOf(value);
  }

  function wrapStyle(style, wraps) {
    style.whiteSpace = wraps === true ? NORMAL : NOWRAP;
    return style;
  }

  // markedNodes draws the not-active line's pieces, its tags left as elements.
  function markedNodes() {
    var pieces = markPieces();
    var leadProps = { key: MARK_LEAD_PART, className: TAB_CLASS };
    leadProps[PART_ATTR] = MARK_LEAD_PART;
    var strongProps = {
      key: MARK_STRONG_PART,
      className: TAB_CLASS,
      style: { fontWeight: text(markTags()[STRONG_WEIGHT]) }
    };
    strongProps[PART_ATTR] = MARK_STRONG_PART;
    var tailProps = { key: MARK_TAIL_PART, className: TAB_CLASS };
    tailProps[PART_ATTR] = MARK_TAIL_PART;
    tailProps[COUNT_ATTR] = text(pieces[SECOND]);
    return [
      element(SPAN_TAG, leadProps, text(pieces[ZERO])),
      element(STRONG_TAG, strongProps, text(pieces[STEP])),
      element(
        SPAN_TAG,
        tailProps,
        repeated(NEWLINE, pieces[SECOND]) + String(pieces[SECOND + STEP])
      )
    ];
  }

  function NotActiveNote(props) {
    var one = objectField(props.model, NOT_ACTIVE_LABEL);
    var noteProps = {
      className: TAB_CLASS,
      style: wrapStyle(styleOf(one[STYLE_SHEET]), one[WORD_WRAP]),
      hidden: one[SHOWN] !== true
    };
    noteProps[PART_ATTR] = NOT_ACTIVE_PART;
    noteProps[SHOWN_ATTR] = text(one[SHOWN]);
    noteProps[WRAP_ATTR] = text(one[WORD_WRAP]);
    return element(DIV_TAG, noteProps, markedNodes());
  }

  function EmptyNote(props) {
    var one = objectField(props.model, EMPTY_LABEL);
    var noteProps = {
      className: TAB_CLASS,
      style: wrapStyle(styleOf(one[STYLE_SHEET]), one[WORD_WRAP]),
      hidden: one[SHOWN] !== true
    };
    noteProps[PART_ATTR] = EMPTY_NOTE_PART;
    noteProps[SHOWN_ATTR] = text(one[SHOWN]);
    noteProps[WRAP_ATTR] = text(one[WORD_WRAP]);
    return element(DIV_TAG, noteProps, text(one[TEXT_FIELD]));
  }

  function SummaryRow(props) {
    var row = Array.isArray(props.row) ? props.row : [];
    var name = row.length ? row[ZERO] : undefined;
    var sheet = summaryStyle(props.at);
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
    var valueProps = { className: TAB_CLASS, style: paintedStyle(sheet) };
    valueProps[PART_ATTR] = SUMMARY_VALUE_PART;
    valueProps[KEY_ATTR] = text(name);
    valueProps[PAINTED_ATTR] = String(sheet !== undefined && sheet !== EMPTY);
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
    var groupProps = {
      className: TAB_CLASS,
      style: { display: FLEX, flexDirection: COLUMN_DIRECTION },
      hidden: group[SHOWN] !== true
    };
    groupProps[PART_ATTR] = SUMMARY_GROUP_PART;
    groupProps[SHOWN_ATTR] = text(group[SHOWN]);
    groupProps[COUNT_ATTR] = text(summaryRows().length);
    groupProps[HOST_ATTR] = text(group[CONFIGURED_BY_HOST]);
    groupProps[MATCHED_ATTR] = text(group[FORMS_CONFIGURED]);
    var titleProps = { className: TAB_CLASS };
    titleProps[PART_ATTR] = SUMMARY_TITLE_PART;
    var drawn = [element(SPAN_TAG, titleProps, text(group[TITLE]))];
    summaryRows().forEach(function (row, at) {
      drawn.push(
        element(SummaryRow, { key: SUMMARY_ROW_PART + String(at), row: row, at: at })
      );
    });
    return element(DIV_TAG, groupProps, drawn);
  }

  // The breakdown row draws one element per funder, so each keeps its name.
  function breakdownNodes() {
    var join = text(textNamed(PROVENANCE_JOIN));
    var drawn = [];
    breakdown().forEach(function (one, at) {
      var source = Array.isArray(one) && one.length ? one[ZERO] : undefined;
      if (at > ZERO) {
        var joinProps = { key: BREAKDOWN_JOIN_PART + String(at), className: TAB_CLASS };
        joinProps[PART_ATTR] = BREAKDOWN_JOIN_PART;
        joinProps[INDEX_ATTR] = text(at);
        drawn.push(element(SPAN_TAG, joinProps, join));
      }
      var entryProps = { key: BREAKDOWN_ENTRY_PART + String(at), className: TAB_CLASS };
      entryProps[PART_ATTR] = BREAKDOWN_ENTRY_PART;
      entryProps[KEY_ATTR] = text(source);
      entryProps[INDEX_ATTR] = text(at);
      drawn.push(
        element(
          SPAN_TAG,
          entryProps,
          text(Array.isArray(one) && one.length > STEP ? one[STEP] : undefined)
        )
      );
    });
    return drawn;
  }

  function ProvenanceRow(props) {
    var row = Array.isArray(props.row) ? props.row : [];
    var name = row.length ? row[ZERO] : undefined;
    var sheet = provenanceStyle(props.at);
    var group = objectField(props.model, PROVENANCE_GROUP);
    var rowProps = {
      className: TAB_CLASS,
      style: { display: FLEX, flexDirection: ROW_DIRECTION }
    };
    rowProps[PART_ATTR] = PROVENANCE_ROW_PART;
    rowProps[KEY_ATTR] = text(name);
    rowProps[INDEX_ATTR] = text(props.at);
    var labelProps = { className: TAB_CLASS };
    labelProps[PART_ATTR] = PROVENANCE_LABEL_PART;
    labelProps[KEY_ATTR] = text(name);
    var valueProps = {
      className: TAB_CLASS,
      style: wrapStyle(paintedStyle(sheet), provenanceWrap(props.at))
    };
    valueProps[PART_ATTR] = PROVENANCE_VALUE_PART;
    valueProps[KEY_ATTR] = text(name);
    valueProps[WRAP_ATTR] = text(provenanceWrap(props.at));
    valueProps[PAINTED_ATTR] = String(sheet !== undefined && sheet !== EMPTY);
    valueProps[STYLED_ATTR] = String(Boolean(declarations(sheet).length));
    valueProps[REFUSED_ATTR] = String(group[PREDOMINANT_REFUSED] === true);
    var carried =
      name === labelNamed(PROVENANCE_LABEL) && breakdown().length
        ? breakdownNodes()
        : text(row.length > STEP ? row[STEP] : undefined);
    return element(
      DIV_TAG,
      rowProps,
      element(SPAN_TAG, labelProps, text(name)),
      element(SPAN_TAG, valueProps, carried)
    );
  }

  function ProvenanceGroup(props) {
    var group = objectField(props.model, PROVENANCE_GROUP);
    var groupProps = {
      className: TAB_CLASS,
      style: { display: FLEX, flexDirection: COLUMN_DIRECTION },
      hidden: group[SHOWN] !== true
    };
    groupProps[PART_ATTR] = PROVENANCE_GROUP_PART;
    groupProps[SHOWN_ATTR] = text(group[SHOWN]);
    groupProps[COUNT_ATTR] = text(provenanceRows().length);
    groupProps[REFUSED_ATTR] = String(group[PREDOMINANT_REFUSED] === true);
    var titleProps = { className: TAB_CLASS };
    titleProps[PART_ATTR] = PROVENANCE_TITLE_PART;
    var drawn = [element(SPAN_TAG, titleProps, text(group[TITLE]))];
    provenanceRows().forEach(function (row, at) {
      drawn.push(
        element(ProvenanceRow, {
          key: PROVENANCE_ROW_PART + String(at),
          model: props.model,
          row: row,
          at: at
        })
      );
    });
    return element(DIV_TAG, groupProps, drawn);
  }

  function HeaderCell(props) {
    var headProps = { className: TAB_CLASS, style: { whiteSpace: NORMAL } };
    headProps[PART_ATTR] = HEADER_CELL_PART;
    headProps[TABLE_ATTR] = props.table;
    headProps[COLUMN_ATTR] = text(props.at);
    headProps[KEY_ATTR] = text(props.name);
    headProps[ARIA_LABEL] = label(props.name);
    return element(HEAD_CELL_TAG, headProps, text(props.name));
  }

  // The painted cell is the one whose own word is a direction, never a column.
  function isDirectionCell(table, at, column) {
    if (table !== TRANSACTIONS_TABLE) {
      return false;
    }
    var carried = rowCells(table, at)[column];
    return (
      carried === textNamed(OUT_DIRECTION) || carried === textNamed(IN_DIRECTION)
    );
  }

  function WireCell(props) {
    var painted =
      isDirectionCell(props.table, props.at, props.column) &&
      props.painted !== undefined;
    var style = { whiteSpace: NORMAL };
    if (painted) {
      style.color = colour(props.painted);
    }
    var cellProps = { className: TAB_CLASS, style: style };
    cellProps[PART_ATTR] = WIRE_CELL_PART;
    cellProps[COLUMN_ATTR] = text(props.column);
    cellProps[KEY_ATTR] = text(headers(props.table)[props.column]);
    cellProps[PAINTED_ATTR] = String(painted);
    return element(
      CELL_TAG,
      cellProps,
      text(rowCells(props.table, props.at)[props.column])
    );
  }

  function WireRow(props) {
    var rowProps = { className: TAB_CLASS };
    rowProps[PART_ATTR] = WIRE_ROW_PART;
    rowProps[ROW_ATTR] = text(props.at);
    rowProps[TABLE_ATTR] = props.table;
    rowProps[NAME_ATTR] = text(rowCells(props.table, props.at)[ZERO]);
    var painted =
      props.table === TRANSACTIONS_TABLE ? directionColour(props.at) : undefined;
    var drawn = headers(props.table).map(function (one, column) {
      return element(WireCell, {
        key: String(column),
        table: props.table,
        at: props.at,
        column: column,
        painted: painted
      });
    });
    return element(ROW_TAG, rowProps, drawn);
  }

  function WirePanel(props) {
    var bag = objectField(props.model, props.table);
    var tables = objectField(props.model, TABLES);
    var panelProps = {
      className: TAB_CLASS,
      style: { display: FLEX, flexDirection: COLUMN_DIRECTION, overflow: AUTO },
      hidden: bag[SHOWN] !== true
    };
    panelProps[PART_ATTR] = WIRE_PANEL_PART;
    panelProps[TABLE_ATTR] = props.table;
    panelProps[SHOWN_ATTR] = text(bag[SHOWN]);
    panelProps[COUNT_ATTR] = text(bag[COUNT]);
    var titleProps = { className: TAB_CLASS };
    titleProps[PART_ATTR] = WIRE_TITLE_PART;
    titleProps[TABLE_ATTR] = props.table;
    var tableProps = {
      className: TAB_CLASS,
      style: {
        tableLayout: FIXED,
        width: FULL,
        borderCollapse: COLLAPSE,
        maxHeight: length(props.tall)
      }
    };
    tableProps[PART_ATTR] = WIRE_TABLE_PART;
    tableProps[TABLE_ATTR] = props.table;
    tableProps[ALTERNATING_ATTR] = text(tables[ALTERNATING_ROWS]);
    tableProps[RESIZE_ATTR] = text(tables[RESIZE_MODE]);
    tableProps[EDIT_ATTR] = text(tables[EDIT_TRIGGERS]);
    tableProps[HEIGHT_ATTR] = text(props.tall);
    var headProps = { className: TAB_CLASS };
    headProps[PART_ATTR] = HEAD_PART;
    headProps[TABLE_ATTR] = props.table;
    var headRowProps = { className: TAB_CLASS };
    headRowProps[PART_ATTR] = HEAD_ROW_PART;
    headRowProps[TABLE_ATTR] = props.table;
    headRowProps[COUNT_ATTR] = text(headers(props.table).length);
    var bodyProps = { className: TAB_CLASS };
    bodyProps[PART_ATTR] = BODY_PART;
    bodyProps[TABLE_ATTR] = props.table;
    bodyProps[COUNT_ATTR] = text(tableRows(props.table).length);
    return element(
      DIV_TAG,
      panelProps,
      element(SPAN_TAG, titleProps, text(bag[TITLE])),
      element(
        TABLE_TAG,
        tableProps,
        element(
          HEAD_TAG,
          headProps,
          element(
            ROW_TAG,
            headRowProps,
            headers(props.table).map(function (name, at) {
              return element(HeaderCell, {
                key: String(at),
                table: props.table,
                name: name,
                at: at
              });
            })
          )
        ),
        element(
          BODY_TAG,
          bodyProps,
          tableRows(props.table).map(function (one, at) {
            return element(WireRow, { key: String(at), table: props.table, at: at });
          })
        )
      )
    );
  }

  // The two wire tables share one asked height and the event table its own.
  function tallFor(found, name) {
    var tables = objectField(found, TABLES);
    return tables[
      name === TRANSACTIONS_TABLE ? EVENTS_MAX_HEIGHT_PX : WIRE_MAX_HEIGHT_PX
    ];
  }

  function TabStep(props) {
    var stepProps = { className: TAB_CLASS };
    stepProps[PART_ATTR] = STEP_PART;
    stepProps[NAME_ATTR] = text(props.name);
    stepProps[INDEX_ATTR] = text(props.at);
    return element(DIV_TAG, stepProps, null);
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
    tabProps[SHOWN_ATTR] = text(found[ACTIVE]);
    tabProps[ARIA_LABEL] = label(found[ACCESSIBLE_NAME]);
    var drawn = [
      element(NotActiveNote, { key: NOT_ACTIVE_PART, model: found }),
      element(SummaryGroup, { key: SUMMARY_GROUP_PART, model: found }),
      element(ProvenanceGroup, { key: PROVENANCE_GROUP_PART, model: found })
    ];
    WIRE_TABLES.forEach(function (name) {
      drawn.push(
        element(WirePanel, {
          key: name,
          model: found,
          table: name,
          tall: tallFor(found, name)
        })
      );
    });
    drawn.push(element(EmptyNote, { key: EMPTY_NOTE_PART, model: found }));
    listField(found, CALLS).forEach(function (one, at) {
      drawn.push(element(TabStep, { key: STEP_PART + String(at), name: one, at: at }));
    });
    return element(DIV_TAG, tabProps, drawn);
  }

  function heldFieldCount(found) {
    return DECLARED_FIELDS.filter(function (name) {
      return owns(found, name);
    }).length;
  }

  // Counts fields, rows and cells declared against those held.
  function report() {
    var found = held.model;
    var counted = { declared: {}, held: {} };
    WIRE_TABLES.forEach(function (name) {
      counted.declared[name] = listField(objectField(found, name), HEADERS).length;
      counted.held[name] = listField(objectField(found, name), ROWS).length;
    });
    return {
      declared: {
        fields: DECLARED_FIELDS.length,
        steps: listField(found, CALL_NAMES).length,
        summary: listField(objectField(found, SUMMARY_GROUP), ROW_STYLES).length,
        provenance: listField(objectField(found, PROVENANCE_GROUP), ROW_STYLES).length,
        columns: counted.declared
      },
      held: {
        fields: heldFieldCount(found),
        steps: listField(found, CALLS).length,
        summary: listField(objectField(found, SUMMARY_GROUP), ROWS).length,
        provenance: listField(objectField(found, PROVENANCE_GROUP), ROWS).length,
        rows: counted.held
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
    checkSteps(found);
    checkGroups(found);
    checkBreakdown(found);
    checkTables(found);
    checkMarks(found);
    checkColours(found);
    checkBagOrder(found);
    checkDrawnMarkup(found);
    return report();
  }

  // Asks METHOD once, clearing asked so a refused first ask is retried.
  function loadTab(params) {
    if (asked !== null) {
      return asked;
    }
    if (!global.acervator || typeof global.acervator.call !== FUNCTION_KIND) {
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
        kind === STRING_KIND ||
        kind === NUMBER_KIND ||
        kind === BOOLEAN_KIND ||
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
  function renderTab(target, found) {
    if (isPlainObject(found)) {
      setTab(found);
    }
    return draw(target, element(Tab, { model: held === null ? null : held.model }));
  }

  // The named empty space the Live Bot Settings window left, or root itself.
  function spaceIn(root) {
    if (!root || typeof root.getAttribute !== FUNCTION_KIND) {
      return null;
    }
    if (root.getAttribute(PART_ATTR) === PAGE_PART) {
      return root;
    }
    if (typeof root.querySelector !== FUNCTION_KIND) {
      return null;
    }
    return root.querySelector(
      SELECT_OPEN + PART_ATTR + SELECT_IS + PAGE_PART + SELECT_CLOSE
    );
  }

  function fill(root, found) {
    var space = spaceIn(root);
    return space === null ? null : renderTab(space, found);
  }

  function forget() {
    held = null;
    tabFaults = [];
    loadFault = null;
    asked = null;
  }

  global.acervatorSetSimBotSwarmSettingsTab = setTab;
  global.acervatorLoadSimBotSwarmSettingsTab = loadTab;
  global.acervatorSimBotSwarmSettingsTab = {
    method: METHOD,
    spacePart: PAGE_PART,
    Tab: Tab,
    SummaryGroup: SummaryGroup,
    ProvenanceGroup: ProvenanceGroup,
    WirePanel: WirePanel,
    NotActiveNote: NotActiveNote,
    payload: payload,
    declaredNames: declaredNames,
    field: field,
    bag: bag,
    list: list,
    bagKeys: bagKeys,
    calls: calls,
    callNames: callNames,
    tableNames: tableNames,
    headers: headers,
    tableRows: tableRows,
    rowCells: rowCells,
    wireNames: wireNames,
    wireRowNamed: wireRowNamed,
    directionColour: directionColour,
    summaryRows: summaryRows,
    summaryStyle: summaryStyle,
    summaryValue: summaryValue,
    provenanceRows: provenanceRows,
    provenanceStyle: provenanceStyle,
    provenanceWrap: provenanceWrap,
    provenanceValue: provenanceValue,
    rowNames: rowNames,
    labelNamed: labelNamed,
    textNamed: textNamed,
    colourNamed: colourNamed,
    breakdown: breakdown,
    breakdownSources: breakdownSources,
    breakdownFor: breakdownFor,
    breakdownLine: breakdownLine,
    markPieces: markPieces,
    markTags: markTags,
    rebuiltNotActive: rebuiltNotActive,
    wholeSheet: wholeSheet,
    paintedStyle: paintedStyle,
    isDirectionCell: isDirectionCell,
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
