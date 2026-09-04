// Draws the Settings tab from the live_settings_tab.state payload.
(function (global) {
  "use strict";

  var METHOD = "live_settings_tab.state";

  var ACCESSIBLE_NAME = "accessible_name";
  var ACTIONS = "actions";
  var ALT_TARGETS = "alt_targets";
  var ATTRIBUTES = "attributes";
  var BARE_NUMBER_FIELDS = "bare_number_fields";
  var BOXES = "boxes";
  var BUDGET_ROW = "budget_row";
  var BUILT = "built";
  var BUS_EMITS = "bus_emits";
  var BUS_SUBSCRIBES = "bus_subscribes";
  var CALL_NAMES = "call_names";
  var CALLS = "calls";
  var CHANGED = "changed";
  var COLORS = "colors";
  var COMBO_INDEX = "combo_index";
  var COMPOUND_ROW = "compound_row";
  var CONTAINER = "container";
  var CONTROL_NAMES = "control_names";
  var CONTROL_SPECS = "control_specs";
  var DANGER_BUTTON = "danger_button";
  var DEFAULTS = "defaults";
  var DENOM_LABELS = "denom_labels";
  var DENOM_ROWS = "denom_rows";
  var DENOM_VISIBLE = "denom_visible";
  var FORMATS = "formats";
  var FORMS = "forms";
  var GROUP_TITLES = "group_titles";
  var GROUPS = "groups";
  var INFO_LABEL = "info_label";
  var ITEMS = "items";
  var MODES = "modes";
  var OUTCOMES = "outcomes";
  var OVER_CAP_ROW = "over_cap_row";
  var PROMPTS = "prompts";
  var READ_ONLY_LABELS = "read_only_labels";
  var READING_KINDS = "reading_kinds";
  var RESET_BUTTON = "reset_button";
  var ROW_COUNT = "row_count";
  var ROWS = "rows";
  var SIGNALS_DECLARED = "signals_declared";
  var SURPLUS_ROW = "surplus_row";
  var TEXTS = "texts";
  var THREADS = "threads";
  var THRESHOLDS = "thresholds";
  var TIMEFRAME_FALLBACK = "timeframe_fallback";
  var TIMEFRAME_FALLBACK_CHOICE = "timeframe_fallback_choice";
  var TIMEFRAME_ITEMS = "timeframe_items";
  var TIMER_DELAYS_MS = "timer_delays_ms";
  var TIMER_STARTED = "timer_started";
  var TIMERS = "timers";
  var TIMERS_STARTED = "timers_started";
  var TITLES = "titles";
  var TOOLTIPS = "tooltips";
  var TOOLTIPS_APPLIED = "tooltips_applied";
  var VALUES = "values";

  // Every top-level name the live_settings_tab.state payload carries.
  var DECLARED_FIELDS = [
    ACCESSIBLE_NAME,
    ACTIONS,
    ALT_TARGETS,
    ATTRIBUTES,
    BARE_NUMBER_FIELDS,
    BOXES,
    BUDGET_ROW,
    BUILT,
    BUS_EMITS,
    BUS_SUBSCRIBES,
    CALL_NAMES,
    CALLS,
    CHANGED,
    COLORS,
    COMBO_INDEX,
    COMPOUND_ROW,
    CONTAINER,
    CONTROL_NAMES,
    CONTROL_SPECS,
    DANGER_BUTTON,
    DEFAULTS,
    DENOM_LABELS,
    DENOM_ROWS,
    DENOM_VISIBLE,
    FORMATS,
    FORMS,
    GROUP_TITLES,
    GROUPS,
    INFO_LABEL,
    ITEMS,
    MODES,
    OUTCOMES,
    OVER_CAP_ROW,
    PROMPTS,
    READ_ONLY_LABELS,
    READING_KINDS,
    RESET_BUTTON,
    ROW_COUNT,
    ROWS,
    SIGNALS_DECLARED,
    SURPLUS_ROW,
    TEXTS,
    THREADS,
    THRESHOLDS,
    TIMEFRAME_FALLBACK,
    TIMEFRAME_FALLBACK_CHOICE,
    TIMEFRAME_ITEMS,
    TIMER_DELAYS_MS,
    TIMER_STARTED,
    TIMERS,
    TIMERS_STARTED,
    TITLES,
    TOOLTIPS,
    TOOLTIPS_APPLIED,
    VALUES
  ];

  var DECLARED_BAGS = [
    ACTIONS,
    ALT_TARGETS,
    ATTRIBUTES,
    COLORS,
    COMBO_INDEX,
    CONTAINER,
    DANGER_BUTTON,
    DEFAULTS,
    DENOM_LABELS,
    DENOM_ROWS,
    DENOM_VISIBLE,
    FORMATS,
    FORMS,
    GROUP_TITLES,
    INFO_LABEL,
    ITEMS,
    MODES,
    OUTCOMES,
    READ_ONLY_LABELS,
    READING_KINDS,
    RESET_BUTTON,
    TEXTS,
    THRESHOLDS,
    TIMERS,
    TITLES,
    TOOLTIPS,
    TOOLTIPS_APPLIED,
    VALUES
  ];

  var DECLARED_LISTS = [
    BARE_NUMBER_FIELDS,
    BOXES,
    BUDGET_ROW,
    BUS_EMITS,
    BUS_SUBSCRIBES,
    CALL_NAMES,
    CALLS,
    CHANGED,
    COMPOUND_ROW,
    CONTROL_NAMES,
    CONTROL_SPECS,
    GROUPS,
    OVER_CAP_ROW,
    PROMPTS,
    ROWS,
    SIGNALS_DECLARED,
    SURPLUS_ROW,
    THREADS,
    TIMEFRAME_FALLBACK,
    TIMEFRAME_ITEMS,
    TIMER_DELAYS_MS,
    TIMERS_STARTED
  ];

  var NAME_FIELD = "name";
  var KIND_FIELD = "kind";
  var FIELD_FIELD = "field";
  var TEXT_FIELD = "text";
  var ITEMS_FIELD = "items";
  var RANGE_FIELD = "range";
  var DECIMALS_FIELD = "decimals";
  var STEP_FIELD = "step";
  var SUFFIX_FIELD = "suffix";
  var PREFIX_FIELD = "prefix";
  var PLACEHOLDER_FIELD = "placeholder";
  var SPECIAL_VALUE_FIELD = "special_value_text";

  var COMBO_DATA_KIND = "combo_data";
  var COMBO_TEXT_KIND = "combo_text";
  var CHECK_KIND = "check";
  var DOUBLE_SPIN_KIND = "double_spin";
  var SPIN_KIND = "spin";
  var LINE_KIND = "line";
  var NUMBER_KINDS = [DOUBLE_SPIN_KIND, SPIN_KIND];
  var COMBO_KINDS = [COMBO_DATA_KIND, COMBO_TEXT_KIND];

  var SPACING_PX = "spacing_px";
  var MARGINS_SET = "margins_set";
  var TRAILING_STRETCH = "trailing_stretch";
  var CONFIGURED_BY_HOST = "configured_by_host";
  var EXPECTED = "expected";
  var CONFIGURED = "configured";
  var STYLE_SHEET = "style_sheet";
  var WORD_WRAP = "word_wrap";
  var CURRENT_TEXT = "current_text";
  var HINT_TEXT = "hint_text";
  var HINT_WORD_WRAP = "hint_word_wrap";
  var OUTCOME_FIELD = "outcome";
  var RESTORE_DELAY_MS = "restore_delay_ms";
  var PAIRS_FIELD = "pairs";
  var ACTIVE_FORMAT = "active_format";
  var JOIN_FIELD = "join";
  var EMPTY_TEXT_FIELD = "empty_text";
  var COUNT_TOKEN = "{count}";

  var BOX_ICON = "icon";
  var BOX_TITLE = "title";
  var BOX_TEXT = "text";
  var BOX_FIELDS = [BOX_ICON, BOX_TITLE, BOX_TEXT];

  // One row per read-only line: the name the row carries, the field it reads.
  var READ_ONLY_PLAN = [
    ["live_lbl", COMPOUND_ROW],
    ["surplus_lbl", SURPLUS_ROW],
    ["budget_lbl", BUDGET_ROW],
    ["over_lbl", OVER_CAP_ROW]
  ];

  // One row per cross-pair line: the name the row carries, the quote it reads.
  var DENOM_PLAN = [
    ["target_btc_lbl", "BTC"],
    ["target_eth_lbl", "ETH"]
  ];

  // One row per button: the name the row carries, the field holding its words.
  var BUTTON_PLAN = [
    ["cb_reset_all_btn", RESET_BUTTON],
    ["self_destruct_btn", DANGER_BUTTON]
  ];

  var ALT_INFO_ROW = "alt_info_lbl";
  var ALT_LIST_ROW = "alt_list_lbl";
  var ALT_PLAN = [ALT_INFO_ROW, ALT_LIST_ROW];

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
  var UNNAMED_ROW_FAULT = "unnamed-row";
  var UNSEEDED_ROW_FAULT = "unseeded-row";
  var DUPLICATE_NAME_FAULT = "duplicate-name";
  var UNKNOWN_GROUP_FAULT = "unknown-group";
  var NOT_CSS_FAULT = "not-css";

  var ROW_AT = "row:";
  var BOX_AT = "box:";
  var GROUP_AT = "group:";
  var QUOTE_AT = "quote:";
  var EMPTY = "";
  var DOT = ".";

  var NO_BRIDGE = "the preload bridge is not present";

  // Qt paints qlineargradient by name and no browser stylesheet runs it.
  var QT_ONLY = "qlineargradient";

  var TAB_CLASS = "acervator-live-settings";

  var DIV_TAG = "div";
  var SPAN_TAG = "span";
  var LABEL_TAG = "label";
  var BUTTON_TAG = "button";
  var SELECT_TAG = "select";
  var OPTION_TAG = "option";
  var INPUT_TAG = "input";
  var BUTTON_TYPE = "button";
  var CHECKBOX_TYPE = "checkbox";
  var NUMBER_TYPE = "number";
  var TEXT_TYPE = "text";

  var TAB_PART = "live-settings-tab";
  var INFO_PART = "info-label";
  var GROUP_PART = "settings-group";
  var GROUP_TITLE_PART = "group-title";
  var ROW_PART = "settings-row";
  var ROW_LABEL_PART = "row-label";
  var CONTROL_PART = "control";
  var CHECK_TEXT_PART = "check-text";
  var CHECK_BOX_PART = "check-box";
  var NUMBER_BOX_PART = "number-box";
  var BUTTON_BOX_PART = "button-box";
  var OPTION_PART = "combo-option";
  var PREFIX_PART = "value-prefix";
  var SUFFIX_PART = "value-suffix";
  var READ_ONLY_PART = "read-only-value";
  var DENOM_PART = "denom-value";
  var BUTTON_PART = "row-button";
  var DANGER_HINT_PART = "danger-hint";
  var ALT_LINE_PART = "alt-targets-line";
  var MESSAGE_BOX_PART = "message-box";
  var BOX_TITLE_PART = "box-title";
  var BOX_TEXT_PART = "box-text";
  var PROMPT_PART = "prompt";
  var PROMPT_TITLE_PART = "prompt-title";
  var PROMPT_TEXT_PART = "prompt-text";
  var OUTCOME_PART = "outcome";

  // PAGE_PART is the space the Live Bot Settings window leaves for this tab.
  var PAGE_PART = "settings-page";

  var PART_ATTR = "data-part";
  var KEY_ATTR = "data-key";
  var NAME_ATTR = "data-name";
  var INDEX_ATTR = "data-index";
  var GROUP_ATTR = "data-group";
  var KIND_ATTR = "data-kind";
  var ACTION_ATTR = "data-action";
  var FIELD_ATTR = "data-field";
  var VALUE_ATTR = "data-value";
  var SHOWN_ATTR = "data-shown";
  var STYLED_ATTR = "data-styled";
  var COUNT_ATTR = "data-count";
  var DELAY_ATTR = "data-delay-ms";
  var ICON_ATTR = "data-icon";
  var WRAP_ATTR = "data-word-wrap";
  var HOST_ATTR = "data-configured-by-host";
  var MARGINS_ATTR = "data-margins-set";
  var MATCHED_ATTR = "data-matched";
  var STRETCH_ATTR = "data-trailing-stretch";
  var BUILT_ATTR = "data-built";
  var TIMER_ATTR = "data-timer-started";
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
  var HEX_LETTERS = "abcdefABCDEF";

  var PX = "px";
  var FLEX = "flex";
  var COLUMN_DIRECTION = "column";
  var PRE = "pre";
  var PRE_WRAP = "pre-wrap";

  var ZERO = Number(EMPTY);
  var STEP = Number(true);
  var THIRD = STEP + STEP;

  var held = null;
  var tabFaults = [];
  var loadFault = null;
  var asked = null;
  var roots = [];
  var lastEdit = null;

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

  function first(row) {
    return Array.isArray(row) && row.length ? row[ZERO] : undefined;
  }

  function second(row) {
    return Array.isArray(row) && row.length > STEP ? row[STEP] : undefined;
  }

  function third(row) {
    return Array.isArray(row) && row.length > THIRD ? row[THIRD] : undefined;
  }

  // True for a colour written with eight hex digits, which Qt reads alpha-first.
  function isSwappedAlpha(value) {
    return (
      typeof value === "string" &&
      value.length === SWAPPED_LENGTH &&
      value.charAt(ZERO) === HEX_MARK
    );
  }

  function isHexLetter(letter) {
    return DIGITS.indexOf(letter) >= ZERO || HEX_LETTERS.indexOf(letter) >= ZERO;
  }

  // Every colour written anywhere in one sheet, including a disabled block.
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

  function model() {
    return held === null ? null : held.model;
  }

  function rows() {
    return listField(model(), ROWS);
  }

  function groups() {
    return listField(model(), GROUPS);
  }

  function groupNames() {
    return groups().map(first);
  }

  function rowNames() {
    return rows().map(third);
  }

  function rowsOfGroup(name) {
    return rows().filter(function (row) {
      return first(row) === name;
    });
  }

  function specs() {
    return listField(model(), CONTROL_SPECS);
  }

  function specNamed(name) {
    var found;
    specs().forEach(function (spec) {
      if (isPlainObject(spec) && spec[NAME_FIELD] === name) {
        found = spec;
      }
    });
    return found;
  }

  function readOnlyField(name) {
    var found;
    READ_ONLY_PLAN.forEach(function (pair) {
      if (first(pair) === name) {
        found = second(pair);
      }
    });
    return found;
  }

  function denomQuote(name) {
    var found;
    DENOM_PLAN.forEach(function (pair) {
      if (first(pair) === name) {
        found = second(pair);
      }
    });
    return found;
  }

  function buttonField(name) {
    var found;
    BUTTON_PLAN.forEach(function (pair) {
      if (first(pair) === name) {
        found = second(pair);
      }
    });
    return found;
  }

  // Every row name this module knows how to draw, from the payload it holds.
  function drawableNames() {
    var found = specs().map(function (spec) {
      return isPlainObject(spec) ? spec[NAME_FIELD] : undefined;
    });
    READ_ONLY_PLAN.forEach(function (pair) {
      found.push(first(pair));
    });
    DENOM_PLAN.forEach(function (pair) {
      found.push(first(pair));
    });
    BUTTON_PLAN.forEach(function (pair) {
      found.push(first(pair));
    });
    return found.concat(ALT_PLAN);
  }

  function valueOf(name) {
    var bag = objectField(model(), VALUES);
    return owns(bag, name) ? bag[name] : undefined;
  }

  function comboIndex(name) {
    var bag = objectField(model(), COMBO_INDEX);
    return owns(bag, name) ? bag[name] : undefined;
  }

  function tooltipOf(name) {
    var bag = objectField(model(), TOOLTIPS_APPLIED);
    return owns(bag, name) ? bag[name] : undefined;
  }

  // The wired name of one control, found by the control it opens with.
  function actionOf(name) {
    var bag = objectField(model(), ACTIONS);
    var found;
    Object.keys(bag).forEach(function (wired) {
      if (String(wired).split(DOT).shift() === name) {
        found = wired;
      }
    });
    return found;
  }

  function actionField(wired) {
    var bag = objectField(model(), ACTIONS);
    return owns(bag, wired) ? bag[wired] : undefined;
  }

  // The list one combo offers: its own when it declares one, the granularities otherwise.
  function comboItems(spec) {
    if (isPlainObject(spec) && Array.isArray(spec[ITEMS_FIELD])) {
      return spec[ITEMS_FIELD];
    }
    return listField(model(), TIMEFRAME_ITEMS);
  }

  function itemLabel(item) {
    return Array.isArray(item) ? first(item) : item;
  }

  function itemValue(item) {
    return Array.isArray(item) ? second(item) : item;
  }

  function denomRow(quote) {
    var bag = objectField(model(), DENOM_ROWS);
    return owns(bag, quote) && Array.isArray(bag[quote]) ? bag[quote] : [];
  }

  function denomShown(quote) {
    var bag = objectField(model(), DENOM_VISIBLE);
    return owns(bag, quote) ? bag[quote] === true : false;
  }

  function altLine(name) {
    var bag = objectField(model(), ALT_TARGETS);
    var pairs = listField(bag, PAIRS_FIELD);
    if (name === ALT_LIST_ROW) {
      return pairs.length ? pairs.join(String(bag[JOIN_FIELD])) : undefined;
    }
    if (!pairs.length) {
      return bag[EMPTY_TEXT_FIELD];
    }
    return String(bag[ACTIVE_FORMAT]).split(COUNT_TOKEN).join(String(pairs.length));
  }

  function boxes() {
    return listField(model(), BOXES);
  }

  function prompts() {
    return listField(model(), PROMPTS);
  }

  function calls() {
    return listField(model(), CALLS).slice();
  }

  function colourNamed(name) {
    var bag = objectField(model(), COLORS);
    return owns(bag, name) ? bag[name] : undefined;
  }

  // Every bare colour the tab paints a line with, each beside the field carrying it.
  function paintedColours() {
    var found = [];
    function keep(field, where, colour) {
      if (typeof colour === "string") {
        found.push({ field: field, where: where, colour: colour });
      }
    }
    var bag = objectField(model(), COLORS);
    Object.keys(bag).forEach(function (name) {
      keep(COLORS, name, bag[name]);
    });
    READ_ONLY_PLAN.forEach(function (pair) {
      var field = second(pair);
      keep(
        field,
        ROW_AT + String(first(pair)),
        second(listField(model(), field))
      );
    });
    Object.keys(objectField(model(), DENOM_ROWS)).forEach(function (quote) {
      keep(DENOM_ROWS, QUOTE_AT + String(quote), second(denomRow(quote)));
    });
    return found;
  }

  // Every style sheet the tab applies, each beside the field carrying it.
  function sheets() {
    return [{ field: INFO_LABEL, sheet: objectField(model(), INFO_LABEL)[STYLE_SHEET] }];
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
  }

  // Every name the payload wires a signal for: a control, a button or a timer.
  function wirableNames(given) {
    var found = given === undefined ? model() : given;
    var named = listField(found, CONTROL_SPECS).map(function (spec) {
      return isPlainObject(spec) ? spec[NAME_FIELD] : undefined;
    });
    BUTTON_PLAN.forEach(function (pair) {
      named.push(first(pair));
    });
    return named.concat(Object.keys(objectField(found, TIMERS)));
  }

  // A wired name must open with a control, a button or a timer the payload declares.
  function checkActions(found) {
    var bag = objectField(found, ACTIONS);
    var named = wirableNames(found);
    Object.keys(bag).forEach(function (wired) {
      if (named.indexOf(String(wired).split(DOT).shift()) < ZERO) {
        tabFaults.push(fault(null, ACTIONS, UNKNOWN_ACTION_FAULT, wired));
      }
    });
    listField(found, ROWS).forEach(function (row) {
      var name = third(row);
      if (named.indexOf(name) >= ZERO && actionOf(name) === undefined) {
        tabFaults.push(fault(ROW_AT + String(name), ACTIONS, MISSING_FAULT, name));
      }
    });
  }

  // Every drawn row must be one this module has a way to draw.
  function checkRows(found) {
    var drawable = drawableNames();
    var seeded = objectField(found, VALUES);
    var seen = [];
    listField(found, ROWS).forEach(function (row, at) {
      var where = ROW_AT + String(at);
      if (!Array.isArray(row)) {
        tabFaults.push(fault(where, ROWS, NOT_A_LIST_FAULT, kindOf(row)));
        return;
      }
      if (row.length <= THIRD) {
        tabFaults.push(fault(where, ROWS, SHORT_LIST_FAULT, row.length));
        return;
      }
      var name = third(row);
      if (drawable.indexOf(name) < ZERO) {
        tabFaults.push(fault(where, ROWS, UNNAMED_ROW_FAULT, name));
      } else if (specNamed(name) !== undefined && !owns(seeded, name)) {
        tabFaults.push(fault(where, VALUES, UNSEEDED_ROW_FAULT, name));
      }
      if (seen.indexOf(name) >= ZERO) {
        tabFaults.push(fault(where, ROWS, DUPLICATE_NAME_FAULT, name));
      }
      seen.push(name);
    });
    if (listField(found, ROWS).length !== found[ROW_COUNT]) {
      tabFaults.push(fault(null, ROW_COUNT, DISAGREES_FAULT, found[ROW_COUNT]));
    }
  }

  // A group draws a title the bag publishes, and every row names a drawn group.
  function checkGroups(found) {
    var titles = objectField(found, GROUP_TITLES);
    var published = Object.keys(titles).map(function (key) {
      return titles[key];
    });
    var named = [];
    listField(found, GROUPS).forEach(function (group, at) {
      named.push(first(group));
      if (published.indexOf(second(group)) < ZERO) {
        tabFaults.push(
          fault(GROUP_AT + String(at), GROUP_TITLES, MISSING_FAULT, second(group))
        );
      }
    });
    listField(found, ROWS).forEach(function (row, at) {
      if (Array.isArray(row) && named.indexOf(first(row)) < ZERO) {
        tabFaults.push(
          fault(ROW_AT + String(at), GROUPS, UNKNOWN_GROUP_FAULT, first(row))
        );
      }
    });
  }

  function checkColour(where, field, value) {
    if (isSwappedAlpha(value)) {
      tabFaults.push(fault(where, field, SWAPPED_ALPHA_FAULT, value));
    }
  }

  function checkColours() {
    paintedColours().forEach(function (one) {
      checkColour(one.where, one.field, one.colour);
    });
    sheets().forEach(function (one) {
      hexRuns(one.sheet).forEach(function (value) {
        checkColour(null, one.field, value);
      });
      declarations(one.sheet).forEach(function (written) {
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
    });
  }

  function element() {
    return global.React.createElement.apply(null, arguments);
  }

  // Every read-only line is written CSS, so an empty sheet paints nothing.
  function paintedStyle(sheet) {
    return declarations(sheet).length ? styleOf(sheet) : {};
  }

  function colourStyle(colour) {
    var style = { whiteSpace: PRE };
    if (typeof colour === "string" && colour.length) {
      style.color = colour;
    }
    return style;
  }

  // edit records the last control changed and the value it answered with.
  function edit(name, value) {
    var wired = actionOf(name);
    lastEdit = {
      name: name,
      value: value,
      action: wired,
      field: actionField(wired)
    };
    return lastEdit;
  }

  function edited() {
    return lastEdit;
  }

  function ComboControl(props) {
    var spec = props.spec;
    var items = comboItems(spec);
    var at = comboIndex(props.name);
    var chosen = at >= ZERO && at < items.length ? itemValue(items[at]) : undefined;
    var selectProps = {
      className: TAB_CLASS,
      value: chosen === undefined ? EMPTY : String(chosen),
      title: label(tooltipOf(props.name)),
      onChange: function (event) {
        props.onEdit(props.name, event.target.value);
      }
    };
    selectProps[PART_ATTR] = CONTROL_PART;
    selectProps[NAME_ATTR] = props.name;
    selectProps[KIND_ATTR] = text(spec[KIND_FIELD]);
    selectProps[FIELD_ATTR] = text(spec[FIELD_FIELD]);
    selectProps[INDEX_ATTR] = text(at);
    selectProps[VALUE_ATTR] = text(valueOf(props.name));
    selectProps[ACTION_ATTR] = label(actionOf(props.name));
    selectProps[COUNT_ATTR] = text(items.length);
    var drawn = items.map(function (item, place) {
      var optionProps = { key: String(place), value: String(itemValue(item)) };
      optionProps[PART_ATTR] = OPTION_PART;
      optionProps[NAME_ATTR] = props.name;
      optionProps[INDEX_ATTR] = String(place);
      return element(OPTION_TAG, optionProps, text(itemLabel(item)));
    });
    return element(SELECT_TAG, selectProps, drawn);
  }

  function CheckControl(props) {
    var spec = props.spec;
    var boxProps = {
      className: TAB_CLASS,
      type: CHECKBOX_TYPE,
      checked: valueOf(props.name) === true,
      title: label(tooltipOf(props.name)),
      onChange: function (event) {
        props.onEdit(props.name, event.target.checked);
      }
    };
    boxProps[PART_ATTR] = CONTROL_PART;
    boxProps[NAME_ATTR] = props.name;
    boxProps[KIND_ATTR] = text(spec[KIND_FIELD]);
    boxProps[FIELD_ATTR] = text(spec[FIELD_FIELD]);
    boxProps[VALUE_ATTR] = text(valueOf(props.name));
    boxProps[ACTION_ATTR] = label(actionOf(props.name));
    boxProps[ARIA_LABEL] = label(spec[TEXT_FIELD]);
    var wordsProps = { className: TAB_CLASS };
    wordsProps[PART_ATTR] = CHECK_TEXT_PART;
    wordsProps[NAME_ATTR] = props.name;
    var wrapProps = { className: TAB_CLASS };
    wrapProps[PART_ATTR] = CHECK_BOX_PART;
    wrapProps[NAME_ATTR] = props.name;
    return element(
      LABEL_TAG,
      wrapProps,
      element(INPUT_TAG, boxProps),
      element(SPAN_TAG, wordsProps, text(spec[TEXT_FIELD]))
    );
  }

  // A spin at its own lowest value prints the words Qt prints in its place.
  function trailingText(spec, name) {
    var span = Array.isArray(spec[RANGE_FIELD]) ? spec[RANGE_FIELD] : [];
    if (owns(spec, SPECIAL_VALUE_FIELD) && valueOf(name) === first(span)) {
      return spec[SPECIAL_VALUE_FIELD];
    }
    return spec[SUFFIX_FIELD];
  }

  function NumberControl(props) {
    var spec = props.spec;
    var span = Array.isArray(spec[RANGE_FIELD]) ? spec[RANGE_FIELD] : [];
    var boxProps = {
      key: CONTROL_PART,
      className: TAB_CLASS,
      type: NUMBER_TYPE,
      value: text(valueOf(props.name)),
      min: text(first(span)),
      max: text(second(span)),
      step: text(spec[STEP_FIELD]),
      title: label(tooltipOf(props.name)),
      onChange: function (event) {
        props.onEdit(props.name, event.target.value);
      }
    };
    boxProps[PART_ATTR] = CONTROL_PART;
    boxProps[NAME_ATTR] = props.name;
    boxProps[KIND_ATTR] = text(spec[KIND_FIELD]);
    boxProps[FIELD_ATTR] = text(spec[FIELD_FIELD]);
    boxProps[VALUE_ATTR] = text(valueOf(props.name));
    boxProps[ACTION_ATTR] = label(actionOf(props.name));
    boxProps[COUNT_ATTR] = text(spec[DECIMALS_FIELD]);
    var beforeProps = { key: PREFIX_FIELD, className: TAB_CLASS };
    beforeProps[PART_ATTR] = PREFIX_PART;
    beforeProps[NAME_ATTR] = props.name;
    var afterProps = { key: SUFFIX_FIELD, className: TAB_CLASS };
    afterProps[PART_ATTR] = SUFFIX_PART;
    afterProps[NAME_ATTR] = props.name;
    var wrapProps = { className: TAB_CLASS };
    wrapProps[PART_ATTR] = NUMBER_BOX_PART;
    wrapProps[NAME_ATTR] = props.name;
    return element(
      SPAN_TAG,
      wrapProps,
      element(SPAN_TAG, beforeProps, text(spec[PREFIX_FIELD])),
      element(INPUT_TAG, boxProps),
      element(SPAN_TAG, afterProps, text(trailingText(spec, props.name)))
    );
  }

  function LineControl(props) {
    var spec = props.spec;
    var boxProps = {
      className: TAB_CLASS,
      type: TEXT_TYPE,
      value: text(valueOf(props.name)),
      placeholder: label(spec[PLACEHOLDER_FIELD]),
      title: label(tooltipOf(props.name)),
      onChange: function (event) {
        props.onEdit(props.name, event.target.value);
      }
    };
    boxProps[PART_ATTR] = CONTROL_PART;
    boxProps[NAME_ATTR] = props.name;
    boxProps[KIND_ATTR] = text(spec[KIND_FIELD]);
    boxProps[FIELD_ATTR] = text(spec[FIELD_FIELD]);
    boxProps[VALUE_ATTR] = text(valueOf(props.name));
    boxProps[ACTION_ATTR] = label(actionOf(props.name));
    return element(INPUT_TAG, boxProps);
  }

  function Control(props) {
    var spec = specNamed(props.name);
    if (spec === undefined) {
      return null;
    }
    var kind = spec[KIND_FIELD];
    if (COMBO_KINDS.indexOf(kind) >= ZERO) {
      return element(ComboControl, { spec: spec, name: props.name, onEdit: props.onEdit });
    }
    if (kind === CHECK_KIND) {
      return element(CheckControl, { spec: spec, name: props.name, onEdit: props.onEdit });
    }
    if (NUMBER_KINDS.indexOf(kind) >= ZERO) {
      return element(NumberControl, { spec: spec, name: props.name, onEdit: props.onEdit });
    }
    if (kind === LINE_KIND) {
      return element(LineControl, { spec: spec, name: props.name, onEdit: props.onEdit });
    }
    return null;
  }

  function ReadOnlyValue(props) {
    var line = listField(model(), props.field);
    var valueProps = { className: TAB_CLASS, style: colourStyle(second(line)) };
    valueProps[PART_ATTR] = READ_ONLY_PART;
    valueProps[NAME_ATTR] = props.name;
    valueProps[KEY_ATTR] = props.field;
    valueProps[STYLED_ATTR] = String(typeof second(line) === "string");
    valueProps[ARIA_LABEL] = label(tooltipOf(props.name));
    valueProps.title = label(tooltipOf(props.name));
    return element(SPAN_TAG, valueProps, text(first(line)));
  }

  function DenomValue(props) {
    var line = denomRow(props.quote);
    var shown = denomShown(props.quote);
    var valueProps = {
      className: TAB_CLASS,
      style: colourStyle(second(line)),
      hidden: !shown,
      title: label(tooltipOf(props.name))
    };
    valueProps[PART_ATTR] = DENOM_PART;
    valueProps[NAME_ATTR] = props.name;
    valueProps[KEY_ATTR] = props.quote;
    valueProps[SHOWN_ATTR] = String(shown);
    valueProps[STYLED_ATTR] = String(typeof second(line) === "string");
    return element(SPAN_TAG, valueProps, text(first(line)));
  }

  function RowButton(props) {
    var one = objectField(model(), props.field);
    var words = owns(one, CURRENT_TEXT) ? one[CURRENT_TEXT] : one[TEXT_FIELD];
    var buttonProps = {
      key: BUTTON_PART,
      className: TAB_CLASS,
      type: BUTTON_TYPE,
      title: label(tooltipOf(props.name)),
      onClick: function () {
        props.onPress(props.name);
      }
    };
    buttonProps[PART_ATTR] = BUTTON_PART;
    buttonProps[NAME_ATTR] = props.name;
    buttonProps[KEY_ATTR] = props.field;
    buttonProps[VALUE_ATTR] = text(one[OUTCOME_FIELD]);
    buttonProps[DELAY_ATTR] = text(one[RESTORE_DELAY_MS]);
    buttonProps[ACTION_ATTR] = label(actionOf(props.name));
    buttonProps[ARIA_LABEL] = label(words);
    var drawn = [element(BUTTON_TAG, buttonProps, text(words))];
    if (owns(one, HINT_TEXT)) {
      var hintProps = {
        key: DANGER_HINT_PART,
        className: TAB_CLASS,
        style: { whiteSpace: one[HINT_WORD_WRAP] === true ? PRE_WRAP : PRE }
      };
      hintProps[PART_ATTR] = DANGER_HINT_PART;
      hintProps[NAME_ATTR] = props.name;
      hintProps[WRAP_ATTR] = text(one[HINT_WORD_WRAP]);
      drawn.push(element(DIV_TAG, hintProps, text(one[HINT_TEXT])));
    }
    var wrapProps = { className: TAB_CLASS };
    wrapProps[PART_ATTR] = BUTTON_BOX_PART;
    wrapProps[NAME_ATTR] = props.name;
    return element(DIV_TAG, wrapProps, drawn);
  }

  function AltLine(props) {
    var lineProps = { className: TAB_CLASS, style: { whiteSpace: PRE_WRAP } };
    lineProps[PART_ATTR] = ALT_LINE_PART;
    lineProps[NAME_ATTR] = props.name;
    lineProps[COUNT_ATTR] = text(listField(objectField(model(), ALT_TARGETS), PAIRS_FIELD).length);
    return element(SPAN_TAG, lineProps, text(altLine(props.name)));
  }

  function rowBody(name, handlers) {
    if (specNamed(name) !== undefined) {
      return element(Control, { name: name, onEdit: handlers.onEdit });
    }
    var field = readOnlyField(name);
    if (field !== undefined) {
      return element(ReadOnlyValue, { name: name, field: field });
    }
    var quote = denomQuote(name);
    if (quote !== undefined) {
      return element(DenomValue, { name: name, quote: quote });
    }
    var button = buttonField(name);
    if (button !== undefined) {
      return element(RowButton, { name: name, field: button, onPress: handlers.onPress });
    }
    if (ALT_PLAN.indexOf(name) >= ZERO) {
      return element(AltLine, { name: name });
    }
    return null;
  }

  function Row(props) {
    var row = props.row;
    var name = third(row);
    var rowProps = { className: TAB_CLASS, style: { display: FLEX } };
    rowProps[PART_ATTR] = ROW_PART;
    rowProps[NAME_ATTR] = text(name);
    rowProps[GROUP_ATTR] = text(first(row));
    rowProps[INDEX_ATTR] = text(props.at);
    var labelProps = { className: TAB_CLASS };
    labelProps[PART_ATTR] = ROW_LABEL_PART;
    labelProps[NAME_ATTR] = text(name);
    return element(
      DIV_TAG,
      rowProps,
      element(SPAN_TAG, labelProps, text(second(row))),
      rowBody(name, props.handlers)
    );
  }

  function Group(props) {
    var name = first(props.group);
    var mine = rowsOfGroup(name);
    var groupProps = {
      className: TAB_CLASS,
      style: { display: FLEX, flexDirection: COLUMN_DIRECTION }
    };
    groupProps[PART_ATTR] = GROUP_PART;
    groupProps[NAME_ATTR] = text(name);
    groupProps[INDEX_ATTR] = text(props.at);
    groupProps[COUNT_ATTR] = text(mine.length);
    var titleProps = { key: GROUP_TITLE_PART, className: TAB_CLASS };
    titleProps[PART_ATTR] = GROUP_TITLE_PART;
    titleProps[NAME_ATTR] = text(name);
    var drawn = [element(SPAN_TAG, titleProps, text(second(props.group)))];
    mine.forEach(function (row) {
      drawn.push(
        element(Row, {
          key: String(third(row)),
          row: row,
          at: rows().indexOf(row),
          handlers: props.handlers
        })
      );
    });
    return element(DIV_TAG, groupProps, drawn);
  }

  function InfoLabel(props) {
    var note = objectField(props.model, INFO_LABEL);
    var style = paintedStyle(note[STYLE_SHEET]);
    style.whiteSpace = note[WORD_WRAP] === true ? PRE_WRAP : PRE;
    var noteProps = { className: TAB_CLASS, style: style };
    noteProps[PART_ATTR] = INFO_PART;
    noteProps[WRAP_ATTR] = text(note[WORD_WRAP]);
    noteProps[STYLED_ATTR] = String(Boolean(declarations(note[STYLE_SHEET]).length));
    return element(DIV_TAG, noteProps, text(note[TEXT_FIELD]));
  }

  function MessageBox(props) {
    var box = isPlainObject(props.box) ? props.box : {};
    var boxProps = { className: TAB_CLASS };
    boxProps[PART_ATTR] = MESSAGE_BOX_PART;
    boxProps[INDEX_ATTR] = text(props.at);
    boxProps[ICON_ATTR] = text(box[BOX_ICON]);
    boxProps[KEY_ATTR] = text(box[BOX_TITLE]);
    var titleProps = { className: TAB_CLASS };
    titleProps[PART_ATTR] = BOX_TITLE_PART;
    var textProps = { className: TAB_CLASS, style: { whiteSpace: PRE_WRAP } };
    textProps[PART_ATTR] = BOX_TEXT_PART;
    return element(
      DIV_TAG,
      boxProps,
      element(SPAN_TAG, titleProps, text(box[BOX_TITLE])),
      element(DIV_TAG, textProps, text(box[BOX_TEXT]))
    );
  }

  function Prompt(props) {
    var one = Array.isArray(props.prompt) ? props.prompt : [];
    var promptProps = { className: TAB_CLASS };
    promptProps[PART_ATTR] = PROMPT_PART;
    promptProps[INDEX_ATTR] = text(props.at);
    promptProps[KEY_ATTR] = text(first(one));
    promptProps[VALUE_ATTR] = text(third(one));
    var titleProps = { className: TAB_CLASS };
    titleProps[PART_ATTR] = PROMPT_TITLE_PART;
    var textProps = { className: TAB_CLASS, style: { whiteSpace: PRE_WRAP } };
    textProps[PART_ATTR] = PROMPT_TEXT_PART;
    return element(
      DIV_TAG,
      promptProps,
      element(SPAN_TAG, titleProps, text(first(one))),
      element(DIV_TAG, textProps, text(second(one)))
    );
  }

  function tabAttributes(found, box, forms) {
    var tabProps = {
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
    tabProps[STRETCH_ATTR] = text(box[TRAILING_STRETCH]);
    tabProps[HOST_ATTR] = text(forms[CONFIGURED_BY_HOST]);
    tabProps[MATCHED_ATTR] = String(forms[EXPECTED] === forms[CONFIGURED]);
    tabProps[COUNT_ATTR] = text(found[ROW_COUNT]);
    tabProps[BUILT_ATTR] = text(found[BUILT]);
    tabProps[TIMER_ATTR] = text(found[TIMER_STARTED]);
    tabProps[ARIA_LABEL] = label(found[ACCESSIBLE_NAME]);
    return tabProps;
  }

  // Tab draws nothing for a payload that is not an object.
  function Tab(props) {
    if (!isPlainObject(props.model)) {
      return null;
    }
    var found = props.model;
    var handlers = {
      onEdit: function (name, value) {
        edit(name, value);
        if (typeof props.onEdit === "function") {
          props.onEdit(name, value);
        }
      },
      onPress: function (name) {
        edit(name, null);
        if (typeof props.onPress === "function") {
          props.onPress(name);
        }
      }
    };
    var outcomeProps = { key: OUTCOME_PART, className: TAB_CLASS };
    outcomeProps[PART_ATTR] = OUTCOME_PART;
    outcomeProps[VALUE_ATTR] = text(objectField(found, DANGER_BUTTON)[OUTCOME_FIELD]);
    outcomeProps[KEY_ATTR] = text(objectField(found, RESET_BUTTON)[OUTCOME_FIELD]);
    var drawn = [element(InfoLabel, { key: INFO_PART, model: found })];
    groups().forEach(function (group, at) {
      drawn.push(element(Group, { key: String(first(group)), group: group, at: at, handlers: handlers }));
    });
    drawn.push(element(SPAN_TAG, outcomeProps, null));
    prompts().forEach(function (one, at) {
      drawn.push(element(Prompt, { key: PROMPT_PART + String(at), prompt: one, at: at }));
    });
    boxes().forEach(function (one, at) {
      drawn.push(element(MessageBox, { key: MESSAGE_BOX_PART + String(at), box: one, at: at }));
    });
    return element(DIV_TAG, tabAttributes(found, objectField(found, CONTAINER), objectField(found, FORMS)), drawn);
  }

  function heldFieldCount(found) {
    return DECLARED_FIELDS.filter(function (name) {
      return owns(found, name);
    }).length;
  }

  function drawnRowCount() {
    var drawable = drawableNames();
    return rowNames().filter(function (name) {
      return drawable.indexOf(name) >= ZERO;
    }).length;
  }

  // Counts fields, rows, groups, controls and actions declared against those held.
  function report() {
    var found = held.model;
    return {
      declared: {
        fields: DECLARED_FIELDS.length,
        rows: found[ROW_COUNT],
        groups: Object.keys(objectField(found, GROUP_TITLES)).length,
        controls: listField(found, CONTROL_NAMES).length,
        actions: wirableNames(found).length
      },
      held: {
        fields: heldFieldCount(found),
        rows: drawnRowCount(),
        groups: listField(found, GROUPS).length,
        controls: listField(found, CONTROL_SPECS).length,
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
    checkRows(found);
    checkGroups(found);
    checkColours();
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

  function rowNamed(name) {
    var found;
    rows().forEach(function (row) {
      if (third(row) === name) {
        found = row;
      }
    });
    return found;
  }

  function rowLabel(name) {
    return second(rowNamed(name));
  }

  function walkPayload(visit) {
    function descend(path, value) {
      if (isPlainObject(value)) {
        walk(path, value);
        return;
      }
      if (Array.isArray(value)) {
        value.forEach(function (one, at) {
          var inner = path + DOT + String(at);
          visit(inner, one);
          descend(inner, one);
        });
      }
    }
    function walk(prefix, node) {
      Object.keys(node).forEach(function (name) {
        var path = prefix ? prefix + DOT + name : name;
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
        onEdit: wired.onEdit,
        onPress: wired.onPress
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
    lastEdit = null;
  }

  global.acervatorSetLiveSettingsTab = setTab;
  global.acervatorLoadLiveSettingsTab = loadTab;
  global.acervatorLiveSettingsTab = {
    method: METHOD,
    spacePart: PAGE_PART,
    Tab: Tab,
    Group: Group,
    Row: Row,
    Control: Control,
    InfoLabel: InfoLabel,
    MessageBox: MessageBox,
    Prompt: Prompt,
    payload: payload,
    declaredNames: declaredNames,
    field: field,
    bag: bag,
    list: list,
    bagKeys: bagKeys,
    groupNames: groupNames,
    rowNames: rowNames,
    rowNamed: rowNamed,
    rowLabel: rowLabel,
    rowsOfGroup: rowsOfGroup,
    drawableNames: drawableNames,
    wirableNames: wirableNames,
    specNamed: specNamed,
    comboItems: comboItems,
    itemLabel: itemLabel,
    itemValue: itemValue,
    valueOf: valueOf,
    comboIndex: comboIndex,
    tooltipOf: tooltipOf,
    actionOf: actionOf,
    actionField: actionField,
    readOnlyField: readOnlyField,
    denomQuote: denomQuote,
    denomRow: denomRow,
    denomShown: denomShown,
    buttonField: buttonField,
    altLine: altLine,
    boxes: boxes,
    prompts: prompts,
    calls: calls,
    colourNamed: colourNamed,
    paintedColours: paintedColours,
    sheets: sheets,
    paintedStyle: paintedStyle,
    colourStyle: colourStyle,
    edit: edit,
    edited: edited,
    isSwappedAlpha: isSwappedAlpha,
    hexRuns: hexRuns,
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
