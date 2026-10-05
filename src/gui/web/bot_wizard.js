// Draws the bot creation wizard from the bot_wizard.state payload.
(function (global) {
  "use strict";

  var METHOD = "bot_wizard.state";

  var ACTIONS = "actions";
  var ASSET_PAGE = "asset_page";
  var BUS_EMITS = "bus_emits";
  var BUS_TOPICS = "bus_topics";
  var CALL_NAMES = "call_names";
  var CALLS = "calls";
  var CONFIG = "config";
  var CONFIG_FIELDS = "config_fields";
  var EMPTY_TEXT = "empty_text";
  var FETCHED = "fetched";
  var FIELDS = "fields";
  var FORMATS = "formats";
  var GROUPS = "groups";
  var ICON = "icon";
  var INFO_BUTTON_COLOR = "info_button_color";
  var INT32_MAX = "int32_max";
  var INT32_MIN = "int32_min";
  var KEYS = "keys";
  var LAYOUT = "layout";
  var LOGGER_NAME = "logger_name";
  var METHOD_FIELD = "method";
  var MODES = "modes";
  var MUTED_VALUE = "muted_value";
  var PAGES = "pages";
  var PHANTOM_PAGE = "phantom_page";
  var POOL_PAGE = "pool_page";
  var UNIT_PAGE = "unit_page";
  var UNIT_NOTES = "notes";
  var UNIT_NOTE_NAMES = "note_names";
  var REFUSALS = "refusals";
  var RUNTIME_CONNECT_TOTAL = "runtime_connect_total";
  var SAFE_EVENTS_REASON = "safe_events_reason";
  var SIGNAL_EMIT_TOTAL = "signal_emit_total";
  var SIGNAL_NAMES = "signal_names";
  var SKIN = "skin";
  var SOURCE_CONNECT_TOTAL = "source_connect_total";
  var SPIN_DOUBLE = "spin_double";
  var SPIN_INT = "spin_int";
  var STEP_NAMES = "step_names";
  var THREADS_BUILT = "threads_built";
  var THREADS_STARTED = "threads_started";
  var THRESHOLDS = "thresholds";
  var TIMEFRAMES = "timeframes";
  var TIMER_DELAYS_MS = "timer_delays_ms";
  var TIMERS = "timers";
  var TIMERS_STARTED = "timers_started";
  var VALUES = "values";
  var WALK = "walk";
  var OUTCOME = "outcome";
  var OPEN_OUTCOME = "open_outcome";
  var WINDOW = "window";

  // Every top-level name the bot_wizard.state payload carries.
  var DECLARED_FIELDS = [
    ACTIONS,
    ASSET_PAGE,
    BUS_EMITS,
    BUS_TOPICS,
    CALL_NAMES,
    CALLS,
    CONFIG,
    CONFIG_FIELDS,
    EMPTY_TEXT,
    FETCHED,
    FIELDS,
    FORMATS,
    GROUPS,
    ICON,
    INFO_BUTTON_COLOR,
    INT32_MAX,
    INT32_MIN,
    KEYS,
    LAYOUT,
    LOGGER_NAME,
    METHOD_FIELD,
    MODES,
    MUTED_VALUE,
    PAGES,
    PHANTOM_PAGE,
    POOL_PAGE,
    REFUSALS,
    RUNTIME_CONNECT_TOTAL,
    SAFE_EVENTS_REASON,
    SIGNAL_EMIT_TOTAL,
    SIGNAL_NAMES,
    SKIN,
    SOURCE_CONNECT_TOTAL,
    SPIN_DOUBLE,
    SPIN_INT,
    STEP_NAMES,
    THREADS_BUILT,
    THREADS_STARTED,
    THRESHOLDS,
    TIMEFRAMES,
    TIMER_DELAYS_MS,
    TIMERS,
    TIMERS_STARTED,
    VALUES,
    WALK,
    WINDOW
  ];

  var DECLARED_BAGS = [
    ACTIONS,
    ASSET_PAGE,
    CONFIG,
    FIELDS,
    FORMATS,
    GROUPS,
    ICON,
    KEYS,
    LAYOUT,
    MODES,
    PAGES,
    PHANTOM_PAGE,
    POOL_PAGE,
    REFUSALS,
    SKIN,
    THRESHOLDS,
    TIMEFRAMES,
    TIMERS,
    UNIT_PAGE,
    VALUES,
    WALK,
    WINDOW
  ];

  var DECLARED_LISTS = [
    BUS_EMITS,
    BUS_TOPICS,
    CALL_NAMES,
    CALLS,
    CONFIG_FIELDS,
    FETCHED,
    SIGNAL_NAMES,
    STEP_NAMES,
    THREADS_BUILT,
    THREADS_STARTED,
    TIMER_DELAYS_MS,
    TIMERS_STARTED
  ];

  var NAMES = "names";
  var IDS = "ids";
  var CURRENT = "current";
  var IS_FINAL = "is_final";
  var TITLES = "titles";
  var SUBTITLES = "subtitles";
  var ROWS = "rows";
  var REGISTER_ORDER = "register_order";
  var VISIBLE = "visible";
  var PARAMS_SUBTITLE = "params_subtitle";

  var NUMBERS = "numbers";
  var CHECKS = "checks";
  var RADIOS = "radios";
  var COMBOS = "combos";
  var COMBO_INDEXES = "combo_indexes";
  var TEXTS = "texts";
  var PLACEHOLDERS = "placeholders";
  var ROW_LABELS = "row_labels";
  var CHECK_TEXTS = "check_texts";
  var RADIO_TEXTS = "radio_texts";
  var BUTTON_TEXTS = "button_texts";
  var LABEL_TEXTS = "label_texts";
  var TOOL_TIPS = "tool_tips";

  var KIND = "kind";
  var MINIMUM = "minimum";
  var MAXIMUM = "maximum";
  var DECIMALS = "decimals";
  var STEP_KEY = "step";
  var PREFIX = "prefix";
  var SUFFIX = "suffix";
  var VALUE = "value";

  var EXCHANGE_INDEX = "exchange_index";
  var EXCHANGE_ITEMS = "exchange_items";
  var TARGET_ITEMS = "target_items";
  var TARGET_INDEX = "target_index";
  var TARGET_HUES = "target_hues";
  var TARGET_DATA = "target_data";
  var STATUS = "status";
  var INFO_TOOL_TIP = "info_tool_tip";
  var INFO_BOX = "info_box";
  var INFO_BUTTON_STYLE = "info_button_style";
  var TARGET_MINIMUM_WIDTH_PX = "target_minimum_width_px";
  var ALT_ITEMS = "alt_items";
  var ALT_LIST_MINIMUM_HEIGHT_PX = "alt_list_minimum_height_px";
  var ALT_LIST_ACCESSIBLE_NAME = "alt_list_accessible_name";

  var CHECKED = "checked";
  var ENABLED = "enabled";
  var SELECTION = "selection";
  var WARNING_BOX = "warning_box";

  var TITLE = "title";
  var ACCESSIBLE_NAME = "accessible_name";
  var ACCESSIBLE_DESCRIPTION = "accessible_description";

  var REFUSAL = "refusal";
  // The sentence a refusal carries, where it has one. Falls back to the name.
  var REFUSAL_TEXT = "refusal_text";
  var STEPS = "steps";

  var GROUPS_SPACING_PX = "groups_spacing_px";
  var FORM_HORIZONTAL_SPACING_PX = "form_horizontal_spacing_px";
  var FORM_VERTICAL_SPACING_PX = "form_vertical_spacing_px";
  var MUTED_LABELS = "muted_labels";
  var WORD_WRAPPED_LABELS = "word_wrapped_labels";

  var TA_ITEMS = "ta_items";

  var MISSING_FAULT = "missing";
  var NULL_FAULT = "null";
  var NOT_AN_OBJECT_FAULT = "not-an-object";
  var NOT_A_BAG_FAULT = "not-a-bag";
  var NOT_A_LIST_FAULT = "not-a-list";
  var SHORT_LIST_FAULT = "short-list";
  var SWAPPED_ALPHA_FAULT = "swapped-alpha";
  var REORDERED_KEY_FAULT = "reordered-key";
  var UNKNOWN_ACTION_FAULT = "unknown-action";
  var UNPLACED_FAULT = "unplaced";
  var UNNAMED_FAULT = "unnamed";
  var MARKUP_FAULT = "markup";
  var OUT_OF_RANGE_FAULT = "out-of-range";
  var OFF_STEP_FAULT = "off-step";
  var DUPLICATE_FAULT = "duplicate";

  // NULLABLE_FIELDS names the values a healthy payload may carry as null.
  var NULLABLE_FIELDS = [INFO_BOX, WARNING_BOX, TARGET_DATA];

  // The five page names the payload keys its titles, rows and groups by.
  var ASSET_PAGE_NAME = "asset";
  var MODE_PAGE_NAME = "mode";
  var PARAMS_PAGE_NAME = "params";
  var PHANTOM_PAGE_NAME = "phantom";
  var POOL_PAGE_NAME = "extractor_pool";
  var PAGE_NAMES_READ = [
    ASSET_PAGE_NAME,
    MODE_PAGE_NAME,
    PARAMS_PAGE_NAME,
    PHANTOM_PAGE_NAME,
    POOL_PAGE_NAME
  ];

  var EXCHANGE_ROW = "exchange";
  var POOL_EXCHANGE_TIP = "pool_exchange";
  var EXCHANGE_STEP = "exchange_index";
  var POOL_EXCHANGE_STEP = "pool_exchange_index";
  var PHANTOM_TIMEFRAMES_STEP = "phantom_timeframes";
  var SHOW_INFO_STEP = "show_info";

  var TA_COMBO = "ta_combo";
  var DESCRIPTION_SUFFIX = "_description";
  var ALT_HEADING = "alt_list_heading";
  var PHANTOM_HEADING = "phantom_timeframes_heading";
  var INFO_KEY = "info";

  var PAGE_AT = "page:";
  var GROUP_AT = "group:";
  var FIELD_AT = "field:";
  var ALT_AT = "alt:";
  var TIMEFRAME_AT = "timeframe:";
  var PATH_SPLIT = ".";
  var EMPTY = "";

  var NO_BRIDGE = "the preload bridge is not present";

  // MARKUP_OPEN is the mark a rich-text QLabel takes as formatting.
  var MARKUP_OPEN = "<";

  var WIZARD_CLASS = "acervator-bot-wizard";

  var DIV_TAG = "div";
  var SPAN_TAG = "span";
  var INPUT_TAG = "input";
  var SELECT_TAG = "select";
  var OPTION_TAG = "option";
  var BUTTON_TAG = "button";
  var CHECKBOX_TYPE = "checkbox";
  var RADIO_TYPE = "radio";
  var NUMBER_TYPE = "number";
  var TEXT_TYPE = "text";

  var PAGE_PART = "bot-wizard-page";
  var WIZARD_PART = "bot-wizard";
  var TITLE_PART = "wizard-title";
  var RAIL_PART = "page-rail";
  var RAIL_STOP_PART = "page-rail-stop";
  var HEAD_PART = "page-head";
  var PAGE_TITLE_PART = "page-title";
  var PAGE_SUBTITLE_PART = "page-subtitle";
  var BODY_PART = "page-body";
  var GROUP_PART = "field-group";
  var GROUP_TITLE_PART = "field-group-title";
  var ROW_PART = "field-row";
  var ROW_LABEL_PART = "field-row-label";
  var FIELD_PART = "field";
  var PREFIX_PART = "field-prefix";
  var SUFFIX_PART = "field-suffix";
  var CHECK_TEXT_PART = "field-check-text";
  var STATUS_PART = "page-status";
  var NOTE_PART = "page-note";
  var UNIT_NOTE_PART = "unit-note";
  var TARGET_PART = "target-combo";
  var TARGET_ICON_PART = "target-icon";
  var OPTION_PART = "field-option";
  var INFO_BUTTON_PART = "info-button";
  var INFO_BOX_PART = "info-box";
  var ALT_LIST_PART = "alt-list";
  var ALT_ROW_PART = "alt-row";
  var ALT_TEXT_PART = "alt-text";
  var TIMEFRAME_STRIP_PART = "timeframe-strip";
  var TIMEFRAME_ROW_PART = "timeframe-row";
  var TIMEFRAME_CHECK_PART = "timeframe-check";
  var TIMEFRAME_TEXT_PART = "timeframe-text";
  var WARNING_PART = "warning-box";
  var WARNING_TITLE_PART = "warning-title";
  var WARNING_TEXT_PART = "warning-text";
  var WARNING_INFORMATIVE_PART = "warning-informative";
  var WALK_ROW_PART = "walk-row";
  var WALK_STEP_PART = "walk-step";
  var REFUSAL_PART = "refusal-line";
  var MODE_NOTE_PART = "mode-note";

  var PART_ATTR = "data-part";
  var NAME_ATTR = "data-name";
  var KIND_ATTR = "data-kind";
  var INDEX_ATTR = "data-index";
  var COUNT_ATTR = "data-count";
  var PAGE_ATTR = "data-page";
  var GROUP_ATTR = "data-group";
  var STEP_ATTR = "data-step";
  var SHOWN_ATTR = "data-shown";
  var CHECKED_ATTR = "data-checked";
  var ENABLED_ATTR = "data-enabled";
  var CURRENT_ATTR = "data-current";
  var VALUE_ATTR = "data-value";
  var WRAP_ATTR = "data-word-wrap";
  var MUTED_ATTR = "data-muted";
  var FINAL_ATTR = "data-final";
  var ARIA_LABEL = "aria-label";
  var ARIA_DESCRIPTION = "aria-description";

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
  var WRAP = "wrap";
  var FULL = "100%";
  var NOWRAP = "nowrap";
  var PRE_WRAP = "pre-wrap";
  var AUTO = "auto";
  var CENTER = "center";
  var BOLD = "bold";
  var FLEX_END = "flex-end";

  var ZERO = Number(EMPTY);
  var STEP = Number(true);
  var TWO = STEP + STEP;
  var TEN = DIGITS.length;

  var held = null;
  var wizardFaults = [];
  var loadFault = null;
  var asked = null;
  var roots = [];
  var lastPress = null;
  var dispatched = [];
  var lastAnswer = null;
  var heldSteps = {};

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
    return printed.length > ZERO && DIGITS.indexOf(printed.charAt(ZERO)) >= ZERO;
  }

  function carriesMarkup(value) {
    return typeof value === "string" && value.split(MARKUP_OPEN).length > STEP;
  }

  // table_cells.js owns the rule naming a token variable for one colour.
  function colour(value) {
    var api = global.acervatorCells;
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

  // A selector carrying a colon names a state Qt paints on hover.
  function stateRules(sheet) {
    var api = global.acervatorHeader;
    if (!api || typeof api.stateRules !== "function") {
      return [];
    }
    return api.stateRules(sheet);
  }

  // Every declaration of one sheet, the sub-blocks a base walk skips included.
  function sweptDeclarations(sheet) {
    var found = declarations(sheet).slice();
    stateRules(sheet).forEach(function (rule) {
      declarations(rule.body).forEach(function (one) {
        found.push(one);
      });
    });
    return found;
  }

  function model() {
    return held === null ? {} : held.model;
  }

  function field(name) {
    var found = model();
    return owns(found, name) ? found[name] : undefined;
  }

  function bag(name) {
    return objectField(model(), name);
  }

  function list(name) {
    return listField(model(), name);
  }

  function pageNames() {
    return listField(bag(PAGES), NAMES).slice();
  }

  function currentPage() {
    return text(bag(PAGES)[CURRENT]);
  }

  function pageTitle(name) {
    return objectField(bag(PAGES), TITLES)[name];
  }

  function pageSubtitle(name) {
    if (name === PARAMS_PAGE_NAME && label(bag(GROUPS)[PARAMS_SUBTITLE])) {
      return bag(GROUPS)[PARAMS_SUBTITLE];
    }
    return objectField(bag(PAGES), SUBTITLES)[name];
  }

  function pageRows(name) {
    return listField(objectField(bag(PAGES), ROWS), name).slice();
  }

  function pageGroups(name) {
    return listField(objectField(bag(PAGES), GROUPS), name).slice();
  }

  function groupRows(name) {
    return listField(objectField(bag(GROUPS), ROWS), name).slice();
  }

  function groupTitle(name) {
    return objectField(bag(GROUPS), TITLES)[name];
  }

  function groupNames() {
    return Object.keys(objectField(bag(GROUPS), ROWS));
  }

  function isGroupShown(name) {
    var shown = objectField(bag(GROUPS), VISIBLE);
    return owns(shown, name) ? shown[name] === true : true;
  }

  function numberSpec(name) {
    return objectField(objectField(bag(FIELDS), NUMBERS), name);
  }

  // The venue's own list refills the one drop-down the payload names.
  function comboItems(name) {
    if (name === bag(TIMEFRAMES)[TA_COMBO]) {
      var served = listField(bag(TIMEFRAMES), TA_ITEMS);
      if (served.length) {
        return served;
      }
    }
    return listField(objectField(bag(FIELDS), COMBOS), name);
  }

  function fieldKind(name) {
    if (owns(objectField(bag(FIELDS), NUMBERS), name)) {
      return NUMBERS;
    }
    if (owns(objectField(bag(FIELDS), CHECKS), name)) {
      return CHECKS;
    }
    if (owns(objectField(bag(FIELDS), RADIOS), name)) {
      return RADIOS;
    }
    if (owns(objectField(bag(FIELDS), COMBOS), name)) {
      return COMBOS;
    }
    if (owns(objectField(bag(FIELDS), TEXTS), name)) {
      return TEXTS;
    }
    return undefined;
  }

  function heldValue(kind, name) {
    var values = objectField(bag(VALUES), kind === COMBOS ? COMBO_INDEXES : kind);
    return owns(values, name) ? values[name] : undefined;
  }

  function rowLabel(name) {
    return objectField(bag(FIELDS), ROW_LABELS)[name];
  }

  function checkText(name) {
    return objectField(bag(FIELDS), CHECK_TEXTS)[name];
  }

  function radioText(name) {
    return objectField(bag(FIELDS), RADIO_TEXTS)[name];
  }

  function toolTip(name) {
    return objectField(bag(FIELDS), TOOL_TIPS)[name];
  }

  function placeholder(name) {
    return objectField(bag(FIELDS), PLACEHOLDERS)[name];
  }

  function buttonText(name) {
    return objectField(bag(FIELDS), BUTTON_TEXTS)[name];
  }

  function labelText(name) {
    return objectField(bag(FIELDS), LABEL_TEXTS)[name];
  }

  function isMuted(name) {
    return listField(bag(LAYOUT), MUTED_LABELS).indexOf(name) >= ZERO;
  }

  function isWrapped(name) {
    return listField(bag(LAYOUT), WORD_WRAPPED_LABELS).indexOf(name) >= ZERO;
  }

  function targetItems() {
    return listField(bag(ASSET_PAGE), TARGET_ITEMS);
  }

  function targetHues() {
    return listField(bag(ASSET_PAGE), TARGET_HUES);
  }

  function exchangeItems(page) {
    return listField(bag(page), EXCHANGE_ITEMS);
  }

  function exchangeIndex(page) {
    return bag(page)[EXCHANGE_INDEX];
  }

  function altItems() {
    return listField(bag(POOL_PAGE), ALT_ITEMS);
  }


  function timeframeNames() {
    return listField(bag(PHANTOM_PAGE), TIMEFRAMES).slice();
  }

  function timeframeChecked(name) {
    var found = objectField(bag(PHANTOM_PAGE), CHECKED);
    return owns(found, name) ? found[name] === true : false;
  }

  function timeframeEnabled(name) {
    var found = objectField(bag(PHANTOM_PAGE), ENABLED);
    return owns(found, name) ? found[name] === true : false;
  }

  function timeframeToolTip(name) {
    return objectField(bag(PHANTOM_PAGE), TOOL_TIPS)[name];
  }

  function walkSteps() {
    return listField(bag(WALK), STEPS).slice();
  }

  function actionNames() {
    return Object.keys(bag(ACTIONS));
  }

  function calls() {
    return list(CALLS).slice();
  }

  function config() {
    return copyOf(bag(CONFIG));
  }

  // -- the checks ------------------------------------------------------

  function checkFields(found) {
    DECLARED_FIELDS.forEach(function (name) {
      if (!owns(found, name)) {
        wizardFaults.push(fault(null, name, MISSING_FAULT, undefined));
        return;
      }
      if (found[name] === null && NULLABLE_FIELDS.indexOf(name) < ZERO) {
        wizardFaults.push(fault(null, name, NULL_FAULT, undefined));
      }
    });
    DECLARED_BAGS.forEach(function (name) {
      if (owns(found, name) && !isPlainObject(found[name])) {
        wizardFaults.push(fault(null, name, NOT_A_BAG_FAULT, kindOf(found[name])));
      }
    });
    DECLARED_LISTS.forEach(function (name) {
      if (owns(found, name) && !Array.isArray(found[name])) {
        wizardFaults.push(fault(null, name, NOT_A_LIST_FAULT, kindOf(found[name])));
      }
    });
  }

  function checkPages(found) {
    var pages = objectField(found, PAGES);
    var names = listField(pages, NAMES);
    var titles = objectField(pages, TITLES);
    var subtitles = objectField(pages, SUBTITLES);
    var ids = objectField(pages, IDS);
    names.forEach(function (name) {
      if (!owns(titles, name)) {
        wizardFaults.push(fault(PAGE_AT + name, TITLES, MISSING_FAULT, undefined));
      }
      if (!owns(subtitles, name)) {
        wizardFaults.push(fault(PAGE_AT + name, SUBTITLES, MISSING_FAULT, undefined));
      }
      if (!owns(ids, name)) {
        wizardFaults.push(fault(PAGE_AT + name, IDS, MISSING_FAULT, undefined));
      }
    });
    if (listField(pages, REGISTER_ORDER).length !== names.length) {
      wizardFaults.push(
        fault(null, REGISTER_ORDER, SHORT_LIST_FAULT, names.length)
      );
    }
    var here = text(pages[CURRENT]);
    if (here !== undefined && names.indexOf(here) < ZERO) {
      wizardFaults.push(fault(PAGE_AT + here, CURRENT, UNKNOWN_ACTION_FAULT, here));
    }
    PAGE_NAMES_READ.forEach(function (name) {
      if (names.indexOf(name) < ZERO) {
        wizardFaults.push(fault(PAGE_AT + name, NAMES, MISSING_FAULT, undefined));
      }
    });
    names.forEach(function (name) {
      if (PAGE_NAMES_READ.indexOf(name) < ZERO) {
        wizardFaults.push(fault(PAGE_AT + name, NAMES, UNKNOWN_ACTION_FAULT, name));
      }
    });
  }

  function checkGroups(found) {
    var groups = objectField(found, GROUPS);
    var rows = objectField(groups, ROWS);
    var titles = objectField(groups, TITLES);
    Object.keys(rows).forEach(function (name) {
      if (!owns(titles, name)) {
        wizardFaults.push(fault(GROUP_AT + name, TITLES, MISSING_FAULT, undefined));
      }
      if (!Array.isArray(rows[name])) {
        wizardFaults.push(fault(GROUP_AT + name, ROWS, NOT_A_LIST_FAULT, kindOf(rows[name])));
      }
    });
    listField(objectField(found, PAGES), NAMES).forEach(function (page) {
      listField(objectField(objectField(found, PAGES), GROUPS), page).forEach(
        function (name) {
          if (!owns(rows, name)) {
            wizardFaults.push(fault(PAGE_AT + page, name, UNKNOWN_ACTION_FAULT, name));
          }
        }
      );
    });
  }

  // Every field the payload carries reaches one group or one page, once.
  function checkPlacement(found) {
    var fieldsBag = objectField(found, FIELDS);
    var every = [];
    [NUMBERS, CHECKS, RADIOS, COMBOS, TEXTS].forEach(function (kind) {
      Object.keys(objectField(fieldsBag, kind)).forEach(function (name) {
        every.push(name);
      });
    });
    var placed = {};
    var groups = objectField(objectField(found, GROUPS), ROWS);
    Object.keys(groups).forEach(function (name) {
      listField(groups, name).forEach(function (one) {
        placed[one] = owns(placed, one) ? placed[one] + STEP : STEP;
      });
    });
    var pages = objectField(objectField(found, PAGES), ROWS);
    Object.keys(pages).forEach(function (name) {
      listField(pages, name).forEach(function (one) {
        placed[one] = owns(placed, one) ? placed[one] + STEP : STEP;
      });
    });
    every.forEach(function (name) {
      if (!owns(placed, name)) {
        wizardFaults.push(fault(FIELD_AT + name, ROWS, UNPLACED_FAULT, undefined));
        return;
      }
      if (placed[name] > STEP) {
        wizardFaults.push(fault(FIELD_AT + name, ROWS, DUPLICATE_FAULT, placed[name]));
      }
    });
  }

  // A row drawn from a group needs its own wording, paired by name.
  function checkWording(found) {
    var fieldsBag = objectField(found, FIELDS);
    var labels = objectField(fieldsBag, ROW_LABELS);
    var checkWords = objectField(fieldsBag, CHECK_TEXTS);
    var radioWords = objectField(fieldsBag, RADIO_TEXTS);
    Object.keys(objectField(fieldsBag, CHECKS)).forEach(function (name) {
      if (!owns(checkWords, name)) {
        wizardFaults.push(fault(FIELD_AT + name, CHECK_TEXTS, MISSING_FAULT, undefined));
      }
    });
    Object.keys(objectField(fieldsBag, RADIOS)).forEach(function (name) {
      if (!owns(radioWords, name)) {
        wizardFaults.push(fault(FIELD_AT + name, RADIO_TEXTS, MISSING_FAULT, undefined));
      }
    });
    Object.keys(objectField(fieldsBag, NUMBERS)).forEach(function (name) {
      if (!owns(labels, name)) {
        wizardFaults.push(fault(FIELD_AT + name, ROW_LABELS, MISSING_FAULT, undefined));
      }
    });
  }

  // Every value the payload holds pairs with a field the payload declares.
  function checkValues(found) {
    var fieldsBag = objectField(found, FIELDS);
    var values = objectField(found, VALUES);
    var pairs = [
      [NUMBERS, NUMBERS],
      [CHECKS, CHECKS],
      [RADIOS, RADIOS],
      [COMBOS, COMBO_INDEXES],
      [TEXTS, TEXTS]
    ];
    pairs.forEach(function (pair) {
      var declared = Object.keys(objectField(fieldsBag, pair[ZERO]));
      var carried = objectField(values, pair[STEP]);
      declared.forEach(function (name) {
        if (!owns(carried, name)) {
          wizardFaults.push(fault(FIELD_AT + name, pair[STEP], MISSING_FAULT, undefined));
        }
      });
      Object.keys(carried).forEach(function (name) {
        if (declared.indexOf(name) < ZERO) {
          wizardFaults.push(
            fault(FIELD_AT + name, pair[STEP], UNKNOWN_ACTION_FAULT, name)
          );
        }
      });
    });
  }

  // A number outside its own range, or one its own step cannot reach.
  function checkNumbers(found) {
    var specs = objectField(objectField(found, FIELDS), NUMBERS);
    var carried = objectField(objectField(found, VALUES), NUMBERS);
    Object.keys(specs).forEach(function (name) {
      var spec = objectField(specs, name);
      var value = carried[name];
      if (typeof value !== "number" || value !== value) {
        return;
      }
      var low = numberOr(spec[MINIMUM], value);
      var high = numberOr(spec[MAXIMUM], value);
      if (value < low || value > high) {
        wizardFaults.push(fault(FIELD_AT + name, VALUE, OUT_OF_RANGE_FAULT, value));
      }
      var step = numberOr(spec[STEP_KEY], ZERO);
      var scale = Math.pow(TEN, numberOr(spec[DECIMALS], ZERO));
      if (step > ZERO && Math.round((value - low) * scale) % Math.round(step * scale)) {
        wizardFaults.push(fault(FIELD_AT + name, STEP_KEY, OFF_STEP_FAULT, value));
      }
    });
  }

  function checkAlts(found) {
    var pool = objectField(found, POOL_PAGE);
    var items = listField(pool, ALT_ITEMS);
    var seen = {};
    items.forEach(function (one, at) {
      var named = Array.isArray(one) ? text(one[STEP]) : undefined;
      if (named === undefined || !named.length) {
        wizardFaults.push(fault(ALT_AT + String(at), ALT_ITEMS, UNNAMED_FAULT, at));
        return;
      }
      if (owns(seen, named)) {
        wizardFaults.push(fault(ALT_AT + named, ALT_ITEMS, DUPLICATE_FAULT, at));
      }
      seen[named] = true;
    });
  }

  function checkPhantom(found) {
    var phantom = objectField(found, PHANTOM_PAGE);
    var names = listField(phantom, TIMEFRAMES);
    [CHECKED, ENABLED, TOOL_TIPS].forEach(function (key) {
      var carried = objectField(phantom, key);
      names.forEach(function (name) {
        if (!owns(carried, name)) {
          wizardFaults.push(fault(TIMEFRAME_AT + name, key, MISSING_FAULT, undefined));
        }
      });
      if (Object.keys(carried).length !== names.length) {
        wizardFaults.push(fault(null, key, SHORT_LIST_FAULT, names.length));
      }
    });
    listField(phantom, SELECTION).forEach(function (name) {
      if (names.indexOf(name) < ZERO) {
        wizardFaults.push(
          fault(TIMEFRAME_AT + name, SELECTION, UNKNOWN_ACTION_FAULT, name)
        );
      }
    });
  }

  function checkColour(where, name, value) {
    if (isSwappedAlpha(value)) {
      wizardFaults.push(fault(where, name, SWAPPED_ALPHA_FAULT, value));
    }
  }

  function sweptSheets(found) {
    var sheets = [];
    var asset = objectField(found, ASSET_PAGE);
    if (owns(asset, INFO_BUTTON_STYLE)) {
      sheets.push([ASSET_PAGE, asset[INFO_BUTTON_STYLE]]);
    }
    return sheets;
  }

  function checkColours(found) {
    var skin = objectField(found, SKIN);
    Object.keys(skin).forEach(function (name) {
      checkColour(SKIN, name, skin[name]);
    });
    checkColour(null, INFO_BUTTON_COLOR, found[INFO_BUTTON_COLOR]);
    var icon = objectField(found, ICON);
    Object.keys(icon).forEach(function (name) {
      checkColour(ICON, name, icon[name]);
    });
    sweptSheets(found).forEach(function (pair) {
      sweptDeclarations(pair[STEP]).forEach(function (one) {
        checkColour(pair[ZERO], one.property, one.value);
      });
    });
  }

  function checkBagOrder(found) {
    DECLARED_BAGS.forEach(function (name) {
      Object.keys(objectField(found, name)).forEach(function (key) {
        if (isReorderedKey(key)) {
          wizardFaults.push(fault(name, key, REORDERED_KEY_FAULT, key));
        }
      });
    });
  }

  // Every word the wizard paints through a rich-text QLabel or box.
  function wordsDrawn(found) {
    var drawn = [];
    var asset = objectField(found, ASSET_PAGE);
    var pool = objectField(found, POOL_PAGE);
    drawn.push([ASSET_PAGE, STATUS, asset[STATUS]]);
    drawn.push([ASSET_PAGE, INFO_TOOL_TIP, asset[INFO_TOOL_TIP]]);
    drawn.push([POOL_PAGE, STATUS, pool[STATUS]]);
    var labels = objectField(objectField(found, FIELDS), LABEL_TEXTS);
    Object.keys(labels).forEach(function (name) {
      drawn.push([FIELDS, name, labels[name]]);
    });
    var tips = objectField(objectField(found, FIELDS), TOOL_TIPS);
    Object.keys(tips).forEach(function (name) {
      drawn.push([TOOL_TIPS, name, tips[name]]);
    });
    (Array.isArray(asset[INFO_BOX]) ? asset[INFO_BOX] : []).forEach(function (one, at) {
      drawn.push([INFO_BOX, String(at), one]);
    });
    var phantom = objectField(found, PHANTOM_PAGE);
    (Array.isArray(phantom[WARNING_BOX]) ? phantom[WARNING_BOX] : []).forEach(
      function (one, at) {
        drawn.push([WARNING_BOX, String(at), one]);
      }
    );
    var units = objectField(found, UNIT_PAGE);
    var unitNamed = objectField(units, UNIT_NOTES);
    listField(units, UNIT_NOTE_NAMES).forEach(function (one) {
      if (typeof unitNamed[one] === "string" && unitNamed[one].length) {
        drawn.push([UNIT_PAGE, one, unitNamed[one]]);
      }
    });
    return drawn;
  }

  function checkMarkup(found) {
    wordsDrawn(found).forEach(function (one) {
      if (carriesMarkup(one[TWO])) {
        wizardFaults.push(fault(one[ZERO], one[STEP], MARKUP_FAULT, one[TWO]));
      }
    });
  }

  function checkActions(found) {
    var carried = objectField(found, ACTIONS);
    var declared = numberOr(found[SOURCE_CONNECT_TOTAL], ZERO);
    if (Object.keys(carried).length !== declared) {
      wizardFaults.push(
        fault(null, ACTIONS, SHORT_LIST_FAULT, Object.keys(carried).length)
      );
    }
  }

  function element() {
    return global.React.createElement.apply(null, arguments);
  }

  // Every option carries its own name, so no drawn child is unnamed.
  function optionAt(at, body) {
    var optionBody = { key: String(at), value: String(at) };
    optionBody[PART_ATTR] = OPTION_PART;
    optionBody[INDEX_ATTR] = String(at);
    return element(OPTION_TAG, optionBody, body);
  }

  // The muted look is the host's own property, so this style writes no dimming.
  function noteStyle(wrapped) {
    return { whiteSpace: wrapped ? PRE_WRAP : NOWRAP };
  }

  function Note(props) {
    var body = { key: props.name };
    body[PART_ATTR] = props.part;
    body[NAME_ATTR] = props.name;
    body[MUTED_ATTR] = String(Boolean(props.muted));
    body[WRAP_ATTR] = String(Boolean(props.wrapped));
    body.style = noteStyle(props.wrapped);
    body.title = label(props.tip);
    return element(DIV_TAG, body, text(props.value));
  }

  function GroupTitle(props) {
    var body = {};
    body[PART_ATTR] = GROUP_TITLE_PART;
    body[NAME_ATTR] = props.name;
    body.style = { fontWeight: BOLD };
    return element(DIV_TAG, body, text(props.value));
  }

  function NumberField(props) {
    var spec = props.spec;
    var body = {
      type: NUMBER_TYPE,
      value: props.value === undefined ? EMPTY : String(props.value),
      onChange: function (event) {
        if (props.onNumber) {
          props.onNumber(props.name, Number(event.target.value));
        }
      }
    };
    body[PART_ATTR] = FIELD_PART;
    body[NAME_ATTR] = props.name;
    body[KIND_ATTR] = spec[KIND];
    body[VALUE_ATTR] = text(props.value);
    body.min = text(spec[MINIMUM]);
    body.max = text(spec[MAXIMUM]);
    body.step = text(spec[STEP_KEY]);
    body.title = label(props.tip);
    body[ARIA_LABEL] = label(props.aria);
    return body;
  }

  function FieldRow(props) {
    var name = props.name;
    var kind = props.kind;
    var pieces = [];
    var rowLabelText = props.label;
    if (label(rowLabelText)) {
      var labelBody = { key: ROW_LABEL_PART };
      labelBody[PART_ATTR] = ROW_LABEL_PART;
      labelBody[NAME_ATTR] = name;
      pieces.push(element(SPAN_TAG, labelBody, text(rowLabelText)));
    }
    if (kind === NUMBERS) {
      var spec = props.spec;
      if (label(spec[PREFIX])) {
        var prefixBody = { key: PREFIX_PART };
        prefixBody[PART_ATTR] = PREFIX_PART;
        prefixBody[NAME_ATTR] = name;
        pieces.push(element(SPAN_TAG, prefixBody, text(spec[PREFIX])));
      }
      var numberBody = NumberField(props);
      numberBody.key = FIELD_PART;
      pieces.push(element(INPUT_TAG, numberBody));
      if (label(spec[SUFFIX])) {
        var suffixBody = { key: SUFFIX_PART };
        suffixBody[PART_ATTR] = SUFFIX_PART;
        suffixBody[NAME_ATTR] = name;
        pieces.push(element(SPAN_TAG, suffixBody, text(spec[SUFFIX])));
      }
    } else if (kind === CHECKS || kind === RADIOS) {
      var boxBody = {
        key: FIELD_PART,
        type: kind === CHECKS ? CHECKBOX_TYPE : RADIO_TYPE,
        checked: props.value === true,
        onChange: function (event) {
          if (props.onFlag) {
            props.onFlag(name, event.target.checked === true);
          }
        }
      };
      boxBody[PART_ATTR] = FIELD_PART;
      boxBody[NAME_ATTR] = name;
      boxBody[KIND_ATTR] = kind;
      boxBody[CHECKED_ATTR] = String(props.value === true);
      boxBody.title = label(props.tip);
      boxBody[ARIA_LABEL] = label(props.aria);
      pieces.push(element(INPUT_TAG, boxBody));
      var wordBody = { key: CHECK_TEXT_PART };
      wordBody[PART_ATTR] = CHECK_TEXT_PART;
      wordBody[NAME_ATTR] = name;
      pieces.push(element(SPAN_TAG, wordBody, text(props.word)));
    } else if (kind === COMBOS) {
      var options = props.items.map(function (one, at) {
        return optionAt(at, text(Array.isArray(one) ? one[ZERO] : one));
      });
      var selectBody = {
        key: FIELD_PART,
        value: String(numberOr(props.value, ZERO)),
        onChange: function (event) {
          if (props.onIndex) {
            props.onIndex(name, Number(event.target.value));
          }
        }
      };
      selectBody[PART_ATTR] = FIELD_PART;
      selectBody[NAME_ATTR] = name;
      selectBody[KIND_ATTR] = kind;
      selectBody[INDEX_ATTR] = text(props.value);
      selectBody[COUNT_ATTR] = String(props.items.length);
      selectBody.title = label(props.tip);
      selectBody[ARIA_LABEL] = label(props.aria);
      pieces.push(element(SELECT_TAG, selectBody, options));
    } else if (kind === TEXTS) {
      var textBody = {
        key: FIELD_PART,
        type: TEXT_TYPE,
        value: props.value === undefined ? EMPTY : String(props.value),
        onChange: function (event) {
          if (props.onText) {
            props.onText(name, event.target.value);
          }
        }
      };
      textBody[PART_ATTR] = FIELD_PART;
      textBody[NAME_ATTR] = name;
      textBody[KIND_ATTR] = kind;
      textBody[VALUE_ATTR] = text(props.value);
      textBody.placeholder = label(props.placeholder);
      textBody.title = label(props.tip);
      textBody[ARIA_LABEL] = label(props.aria);
      pieces.push(element(INPUT_TAG, textBody));
    }
    var rowBody = { key: name };
    rowBody[PART_ATTR] = ROW_PART;
    rowBody[NAME_ATTR] = name;
    rowBody[KIND_ATTR] = text(kind);
    rowBody.style = {
      display: FLEX,
      flexDirection: ROW_DIRECTION,
      alignItems: CENTER,
      gap: length(props.gap)
    };
    return element(DIV_TAG, rowBody, pieces);
  }

  // The venue drop-down, whose entries the payload carries per page.
  function VenueRow(props) {
    var body = { key: EXCHANGE_ROW };
    body[PART_ATTR] = ROW_PART;
    body[NAME_ATTR] = EXCHANGE_ROW;
    body.style = { display: FLEX, flexDirection: ROW_DIRECTION, alignItems: CENTER };
    var labelBody = { key: ROW_LABEL_PART };
    labelBody[PART_ATTR] = ROW_LABEL_PART;
    labelBody[NAME_ATTR] = EXCHANGE_ROW;
    var selectBody = {
      key: FIELD_PART,
      value: String(numberOr(props.index, ZERO)),
      onChange: function (event) {
        if (props.onVenue) {
          props.onVenue(props.page, Number(event.target.value));
        }
      }
    };
    selectBody[PART_ATTR] = FIELD_PART;
    selectBody[NAME_ATTR] = EXCHANGE_ROW;
    selectBody[INDEX_ATTR] = text(props.index);
    selectBody[COUNT_ATTR] = String(props.items.length);
    selectBody.title = label(props.tip);
    selectBody[ARIA_LABEL] = label(props.label);
    return element(DIV_TAG, body, [
      element(SPAN_TAG, labelBody, text(props.label)),
      element(
        SELECT_TAG,
        selectBody,
        props.items.map(function (one, at) {
          return optionAt(at, text(one[ZERO]));
        })
      )
    ]);
  }

  function rowFor(name, handlers) {
    if (name === EXCHANGE_ROW) {
      return element(VenueRow, {
        key: name,
        page: handlers.page,
        items: exchangeItems(handlers.page),
        index: exchangeIndex(handlers.page),
        label: rowLabel(name),
        tip: toolTip(handlers.venueTip),
        onVenue: handlers.onVenue
      });
    }
    var kind = fieldKind(name);
    if (kind === undefined) {
      return null;
    }
    return element(FieldRow, {
      key: name,
      name: name,
      kind: kind,
      spec: numberSpec(name),
      items: comboItems(name),
      value: heldValue(kind, name),
      label: rowLabel(name),
      word: kind === CHECKS ? checkText(name) : radioText(name),
      tip: toolTip(name),
      aria: rowLabel(name) || checkText(name) || radioText(name),
      placeholder: placeholder(name),
      gap: bag(LAYOUT)[FORM_HORIZONTAL_SPACING_PX],
      onNumber: handlers.onNumber,
      onFlag: handlers.onFlag,
      onIndex: handlers.onIndex,
      onText: handlers.onText
    });
  }

  function FieldGroup(props) {
    var body = { key: props.name };
    body[PART_ATTR] = GROUP_PART;
    body[NAME_ATTR] = props.name;
    body[GROUP_ATTR] = props.name;
    body[SHOWN_ATTR] = String(Boolean(props.shown));
    body[COUNT_ATTR] = String(props.rows.length);
    body.hidden = !props.shown;
    body.style = {
      display: props.shown ? FLEX : undefined,
      flexDirection: COLUMN_DIRECTION,
      gap: length(props.gap)
    };
    var pieces = [element(GroupTitle, { key: GROUP_TITLE_PART, name: props.name, value: props.title })];
    props.rows.forEach(function (one) {
      if (one !== null) {
        pieces.push(one);
      }
    });
    return element(DIV_TAG, body, pieces);
  }

  function StatusNote(props) {
    return element(Note, {
      key: props.name,
      part: STATUS_PART,
      name: props.name,
      value: props.value,
      wrapped: props.wrapped,
      muted: false
    });
  }

  function AssetBody(props) {
    var pieces = [];
    props.rows.forEach(function (one) {
      pieces.push(one);
    });
    var targetBody = { key: TARGET_PART };
    targetBody[PART_ATTR] = TARGET_PART;
    targetBody[INDEX_ATTR] = text(props.targetIndex);
    targetBody[COUNT_ATTR] = String(props.items.length);
    targetBody[VALUE_ATTR] = text(props.targetData);
    targetBody.style = { minWidth: length(props.minimumWidth) };
    targetBody.value = String(numberOr(props.targetIndex, ZERO));
    targetBody.onChange = function (event) {
      if (props.onTarget) {
        props.onTarget(Number(event.target.value));
      }
    };
    var options = props.items.map(function (one, at) {
      return optionAt(at, text(one[ZERO]));
    });
    pieces.push(element(SELECT_TAG, targetBody, options));
    // Qt paints the lettered circle from a hue on a nought-to-360 wheel.
    var hueBody = { key: TARGET_ICON_PART };
    hueBody[PART_ATTR] = TARGET_ICON_PART;
    hueBody[VALUE_ATTR] = text(props.hues[numberOr(props.targetIndex, ZERO)]);
    hueBody[COUNT_ATTR] = String(props.hues.length);
    pieces.push(element(SPAN_TAG, hueBody, EMPTY));
    var infoBody = { key: INFO_BUTTON_PART, type: BUTTON_TAG };
    infoBody[PART_ATTR] = INFO_BUTTON_PART;
    infoBody.title = label(props.infoTip);
    infoBody.style = styleOf(props.infoStyle);
    infoBody.onClick = function () {
      if (props.onInfo) {
        props.onInfo();
      }
    };
    pieces.push(element(BUTTON_TAG, infoBody, text(props.infoText)));
    pieces.push(
      element(StatusNote, { key: STATUS_PART, name: STATUS, value: props.status, wrapped: true })
    );
    if (Array.isArray(props.infoBox)) {
      var boxBody = { key: INFO_BOX_PART };
      boxBody[PART_ATTR] = INFO_BOX_PART;
      boxBody[COUNT_ATTR] = String(props.infoBox.length);
      boxBody.style = { whiteSpace: PRE_WRAP };
      pieces.push(element(DIV_TAG, boxBody, props.infoBox.map(function (one, at) {
        var lineBody = { key: String(at) };
        lineBody[PART_ATTR] = NOTE_PART;
        lineBody[INDEX_ATTR] = String(at);
        return element(DIV_TAG, lineBody, text(one));
      })));
    }
    return pieces;
  }

  function AltRow(props) {
    var body = { key: props.name };
    body[PART_ATTR] = ALT_ROW_PART;
    body[NAME_ATTR] = props.name;
    body[INDEX_ATTR] = String(props.at);
    body[ARIA_LABEL] = label(props.label);
    var wordBody = { key: ALT_TEXT_PART };
    wordBody[PART_ATTR] = ALT_TEXT_PART;
    wordBody[NAME_ATTR] = props.name;
    return element(DIV_TAG, body, [
      element(SPAN_TAG, wordBody, text(props.label))
    ]);
  }

  function PoolBody(props) {
    var pieces = [];
    props.rows.forEach(function (one) {
      pieces.push(one);
    });
    pieces.push(
      element(StatusNote, { key: STATUS_PART, name: STATUS, value: props.status, wrapped: true })
    );
    var headingBody = { key: NOTE_PART };
    headingBody[PART_ATTR] = NOTE_PART;
    headingBody[NAME_ATTR] = props.headingName;
    pieces.push(element(DIV_TAG, headingBody, text(props.heading)));
    var listBody = { key: ALT_LIST_PART };
    listBody[PART_ATTR] = ALT_LIST_PART;
    listBody[COUNT_ATTR] = String(props.items.length);
    listBody[ARIA_LABEL] = label(props.listName);
    listBody.style = { minHeight: length(props.minimumHeight), overflowY: AUTO };
    pieces.push(
      element(
        DIV_TAG,
        listBody,
        props.items.map(function (one, at) {
          return element(AltRow, {
            key: String(at),
            at: at,
            name: text(one[STEP]),
            label: text(one[ZERO])
          });
        })
      )
    );
    return pieces;
  }

  function TimeframeCheck(props) {
    var body = { key: props.name };
    body[PART_ATTR] = TIMEFRAME_ROW_PART;
    body[NAME_ATTR] = props.name;
    body[CHECKED_ATTR] = String(Boolean(props.checked));
    body[ENABLED_ATTR] = String(Boolean(props.enabled));
    var boxBody = {
      key: TIMEFRAME_CHECK_PART,
      type: CHECKBOX_TYPE,
      checked: props.checked === true,
      disabled: props.enabled !== true
    };
    boxBody[PART_ATTR] = TIMEFRAME_CHECK_PART;
    boxBody[NAME_ATTR] = props.name;
    boxBody.title = label(props.tip);
    boxBody[ARIA_LABEL] = props.name;
    boxBody.onChange = function (event) {
      if (props.onTimeframe) {
        props.onTimeframe(props.name, event.target.checked === true);
      }
    };
    var wordBody = { key: TIMEFRAME_TEXT_PART };
    wordBody[PART_ATTR] = TIMEFRAME_TEXT_PART;
    wordBody[NAME_ATTR] = props.name;
    return element(DIV_TAG, body, [
      element(INPUT_TAG, boxBody),
      element(SPAN_TAG, wordBody, props.name)
    ]);
  }

  function WarningBox(props) {
    var body = { key: WARNING_PART };
    body[PART_ATTR] = WARNING_PART;
    body[COUNT_ATTR] = String(props.lines.length);
    var parts = [WARNING_TITLE_PART, WARNING_TEXT_PART, WARNING_INFORMATIVE_PART];
    return element(
      DIV_TAG,
      body,
      props.lines.map(function (one, at) {
        var lineBody = { key: String(at) };
        lineBody[PART_ATTR] = at < parts.length ? parts[at] : NOTE_PART;
        lineBody[INDEX_ATTR] = String(at);
        lineBody.style = { whiteSpace: PRE_WRAP };
        return element(DIV_TAG, lineBody, text(one));
      })
    );
  }

  function PhantomBody(props) {
    var pieces = [];
    props.rows.forEach(function (one) {
      pieces.push(one);
    });
    var headingBody = { key: NOTE_PART };
    headingBody[PART_ATTR] = NOTE_PART;
    headingBody[NAME_ATTR] = props.headingName;
    pieces.push(element(DIV_TAG, headingBody, text(props.heading)));
    var stripBody = { key: TIMEFRAME_STRIP_PART };
    stripBody[PART_ATTR] = TIMEFRAME_STRIP_PART;
    stripBody[COUNT_ATTR] = String(props.timeframes.length);
    stripBody.style = { display: FLEX, flexDirection: ROW_DIRECTION, flexWrap: WRAP };
    pieces.push(
      element(
        DIV_TAG,
        stripBody,
        props.timeframes.map(function (name) {
          return element(TimeframeCheck, {
            key: name,
            name: name,
            checked: props.checkedNamed(name),
            enabled: props.enabledNamed(name),
            tip: props.tipNamed(name),
            onTimeframe: props.onTimeframe
          });
        })
      )
    );
    props.groups.forEach(function (one) {
      pieces.push(one);
    });
    if (Array.isArray(props.warning)) {
      pieces.push(element(WarningBox, { key: WARNING_PART, lines: props.warning }));
    }
    return pieces;
  }

  function PageRail(props) {
    var body = {};
    body[PART_ATTR] = RAIL_PART;
    body[COUNT_ATTR] = String(props.names.length);
    body.style = { display: FLEX, flexDirection: ROW_DIRECTION, flexWrap: WRAP };
    return element(
      DIV_TAG,
      body,
      props.names.map(function (name) {
        var stopBody = { key: name };
        stopBody[PART_ATTR] = RAIL_STOP_PART;
        stopBody[NAME_ATTR] = name;
        stopBody[CURRENT_ATTR] = String(name === props.current);
        return element(SPAN_TAG, stopBody, text(props.titles[name]));
      })
    );
  }

  function WalkRow(props) {
    var body = {};
    body[PART_ATTR] = WALK_ROW_PART;
    body[COUNT_ATTR] = String(props.steps.length);
    body[FINAL_ATTR] = String(Boolean(props.isFinal));
    body.style = { display: FLEX, flexDirection: ROW_DIRECTION, justifyContent: FLEX_END };
    return element(
      DIV_TAG,
      body,
      props.steps.map(function (name) {
        var stepBody = { key: name, type: BUTTON_TAG };
        stepBody[PART_ATTR] = WALK_STEP_PART;
        stepBody[NAME_ATTR] = name;
        stepBody[STEP_ATTR] = name;
        stepBody.onClick = function () {
          if (props.onWalk) {
            props.onWalk(name);
          }
        };
        return element(BUTTON_TAG, stepBody, name);
      })
    );
  }

  function unitNotes() {
    var held = bag(UNIT_PAGE);
    var named = objectField(held, UNIT_NOTES);
    var drawn = [];
    listField(held, UNIT_NOTE_NAMES).forEach(function (one) {
      var line = named[one];
      if (typeof line === "string" && line.length) {
        drawn.push(
          element(Note, {
            key: one,
            part: UNIT_NOTE_PART,
            name: one,
            value: line,
            muted: false,
            wrapped: true
          })
        );
      }
    });
    return drawn;
  }

  function pageBody(name, wired) {
    var handlers = copyOf(wired);
    handlers.page = name === POOL_PAGE_NAME ? POOL_PAGE : ASSET_PAGE;
    handlers.venueTip = name === POOL_PAGE_NAME ? POOL_EXCHANGE_TIP : EXCHANGE_ROW;
    var rows = pageRows(name).map(function (one) {
      return rowFor(one, handlers);
    });
    var groups = pageGroups(name).map(function (one) {
      return element(FieldGroup, {
        key: one,
        name: one,
        title: groupTitle(one),
        shown: isGroupShown(one),
        gap: bag(LAYOUT)[FORM_VERTICAL_SPACING_PX],
        rows: groupRows(one).map(function (two) {
          return rowFor(two, handlers);
        })
      });
    });
    var asset = bag(ASSET_PAGE);
    var pool = bag(POOL_PAGE);
    var phantom = bag(PHANTOM_PAGE);
    if (name === ASSET_PAGE_NAME) {
      return AssetBody({
        rows: rows,
        items: targetItems(),
        targetIndex: asset[TARGET_INDEX],
        targetData: asset[TARGET_DATA],
        hues: targetHues(),
        minimumWidth: asset[TARGET_MINIMUM_WIDTH_PX],
        status: asset[STATUS],
        infoTip: asset[INFO_TOOL_TIP],
        infoBox: asset[INFO_BOX],
        infoStyle: asset[INFO_BUTTON_STYLE],
        infoText: buttonText(INFO_KEY),
        onTarget: handlers.onTarget,
        onInfo: handlers.onInfo
      });
    }
    if (name === POOL_PAGE_NAME) {
      return PoolBody({
        rows: rows,
        items: altItems(),
        status: pool[STATUS],
        heading: labelText(ALT_HEADING),
        headingName: ALT_HEADING,
        listName: pool[ALT_LIST_ACCESSIBLE_NAME],
        minimumHeight: pool[ALT_LIST_MINIMUM_HEIGHT_PX]
      });
    }
    if (name === PHANTOM_PAGE_NAME) {
      return PhantomBody({
        rows: rows,
        groups: groups,
        timeframes: timeframeNames(),
        checkedNamed: timeframeChecked,
        enabledNamed: timeframeEnabled,
        tipNamed: timeframeToolTip,
        heading: labelText(PHANTOM_HEADING),
        headingName: PHANTOM_HEADING,
        warning: phantom[WARNING_BOX],
        onTimeframe: handlers.onTimeframe
      });
    }
    if (name === PARAMS_PAGE_NAME) {
      return rows.concat(groups).concat(unitNotes());
    }
    if (name === MODE_PAGE_NAME) {
      listField(bag(MODES), NAMES).forEach(function (one) {
        rows.push(
          element(Note, {
            key: one + DESCRIPTION_SUFFIX,
            part: MODE_NOTE_PART,
            name: one + DESCRIPTION_SUFFIX,
            value: labelText(one + DESCRIPTION_SUFFIX),
            muted: isMuted(one + DESCRIPTION_SUFFIX),
            wrapped: isWrapped(one + DESCRIPTION_SUFFIX),
            tip: toolTip(one)
          })
        );
      });
      return rows;
    }
    return rows.concat(groups);
  }

  function Wizard(props) {
    var here = props.current;
    var body = { className: WIZARD_CLASS };
    body[PART_ATTR] = WIZARD_PART;
    body[PAGE_ATTR] = text(here);
    body[ARIA_LABEL] = label(props.accessibleName);
    body[ARIA_DESCRIPTION] = label(props.accessibleDescription);
    body.style = {
      display: FLEX,
      flexDirection: COLUMN_DIRECTION,
      width: FULL,
      gap: length(props.gap)
    };
    var titleBody = { key: TITLE_PART };
    titleBody[PART_ATTR] = TITLE_PART;
    titleBody.style = { fontWeight: BOLD, whiteSpace: NOWRAP };
    var headBody = { key: HEAD_PART };
    headBody[PART_ATTR] = HEAD_PART;
    var pageTitleBody = { key: PAGE_TITLE_PART };
    pageTitleBody[PART_ATTR] = PAGE_TITLE_PART;
    pageTitleBody[NAME_ATTR] = text(here);
    var pageSubBody = { key: PAGE_SUBTITLE_PART };
    pageSubBody[PART_ATTR] = PAGE_SUBTITLE_PART;
    pageSubBody[NAME_ATTR] = text(here);
    pageSubBody.style = { whiteSpace: PRE_WRAP };
    var bodyBody = { key: BODY_PART };
    bodyBody[PART_ATTR] = BODY_PART;
    bodyBody[PAGE_ATTR] = text(here);
    bodyBody.style = { display: FLEX, flexDirection: COLUMN_DIRECTION, gap: length(props.gap) };
    var refusalBody = { key: REFUSAL_PART };
    refusalBody[PART_ATTR] = REFUSAL_PART;
    refusalBody[VALUE_ATTR] = text(props.refusal);
    return element(DIV_TAG, body, [
      element(DIV_TAG, titleBody, text(props.title)),
      element(PageRail, {
        key: RAIL_PART,
        names: props.names,
        titles: props.titles,
        current: here
      }),
      element(DIV_TAG, headBody, [
        element(DIV_TAG, pageTitleBody, text(props.pageTitle)),
        element(DIV_TAG, pageSubBody, text(props.pageSubtitle))
      ]),
      element(DIV_TAG, bodyBody, props.body),
      element(DIV_TAG, refusalBody, text(props.refusal)),
      element(WalkRow, {
        key: WALK_ROW_PART,
        steps: props.steps,
        isFinal: props.isFinal,
        onWalk: props.onWalk
      })
    ]);
  }

  // -- the bridge ------------------------------------------------------

  function hasBridge() {
    return Boolean(global.acervator) && typeof global.acervator.call === "function";
  }

  // The surface lays out fresh pages on every call and keeps nothing, so a
  // press sends every step taken so far, not the one just made.
  function remember(step) {
    var name;
    for (name in step) {
      if (Object.prototype.hasOwnProperty.call(step, name)) {
        heldSteps[name] = merge(heldSteps[name], step[name]);
      }
    }
    return heldSteps;
  }

  function merge(kept, value) {
    if (Array.isArray(kept) && Array.isArray(value)) {
      return kept.concat(value);
    }
    if (isPlainObject(kept) && isPlainObject(value)) {
      var found = copyOf(kept);
      var name;
      for (name in value) {
        if (Object.prototype.hasOwnProperty.call(value, name)) {
          found[name] = value[name];
        }
      }
      return found;
    }
    return value;
  }

  // setWizard clears the press history, which is the host's record of what
  // it asked for, so it is put back after the answer replaces the payload.
  function take(found) {
    if (!isPlainObject(found)) {
      return found;
    }
    var history = dispatched.slice();
    var last = lastPress;
    setWizard(found);
    dispatched = history;
    lastPress = last;
    redraw();
    return found;
  }

  function press(name, step) {
    lastPress = { name: name, step: step };
    dispatched.push(lastPress);
    remember(step);
    lastAnswer = hasBridge()
      ? global.acervator.call(METHOD, copyOf(heldSteps)).then(take)
      : Promise.resolve(null);
    return lastPress;
  }

  function answer() {
    return lastAnswer;
  }

  function steps() {
    return copyOf(heldSteps);
  }

  function isOpen() {
    var walk = bag(WALK);
    return text(walk[OUTCOME]) === text(walk[OPEN_OUTCOME]);
  }

  // Tells the host, once the surface has answered, that the walk ended.
  function closesWith(then) {
    if (typeof then !== "function") {
      return null;
    }
    return Promise.resolve(lastAnswer).then(function () {
      return isOpen() ? null : then();
    });
  }

  function pressNumber(name, value, then) {
    var step = {};
    step[NUMBERS] = {};
    step[NUMBERS][name] = value;
    if (then) {
      then(name, value);
    }
    return press(name, step);
  }

  function pressFlag(name, value, then) {
    var step = {};
    var kind = fieldKind(name);
    step[kind === RADIOS ? RADIOS : CHECKS] = {};
    step[kind === RADIOS ? RADIOS : CHECKS][name] = value;
    if (then) {
      then(name, value);
    }
    return press(name, step);
  }

  function pressIndex(name, value, then) {
    var step = {};
    step[COMBO_INDEXES] = {};
    step[COMBO_INDEXES][name] = value;
    if (then) {
      then(name, value);
    }
    return press(name, step);
  }

  function pressText(name, value, then) {
    var step = {};
    step[TEXTS] = {};
    step[TEXTS][name] = value;
    if (then) {
      then(name, value);
    }
    return press(name, step);
  }

  function pressTimeframe(name, value, then) {
    var step = {};
    step[PHANTOM_TIMEFRAMES_STEP] = {};
    step[PHANTOM_TIMEFRAMES_STEP][name] = value;
    if (then) {
      then(name, value);
    }
    return press(name, step);
  }

  function pressVenue(page, at, then) {
    var step = {};
    step[page === POOL_PAGE ? POOL_EXCHANGE_STEP : EXCHANGE_STEP] = at;
    if (then) {
      then(page, at);
    }
    return press(String(at), step);
  }

  function pressTarget(at, then) {
    var step = {};
    step[TARGET_INDEX] = at;
    if (then) {
      then(at);
    }
    return press(String(at), step);
  }

  function pressButton(step, then) {
    var body = {};
    body[step] = true;
    if (then) {
      then(step);
    }
    return press(step, body);
  }

  function pressWalk(name, then) {
    var step = {};
    step[WALK] = [name];
    if (then) {
      then(name);
    }
    return press(name, step);
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

  function declaredFieldCount(found) {
    var fieldsBag = objectField(found, FIELDS);
    var total = ZERO;
    [NUMBERS, CHECKS, RADIOS, COMBOS, TEXTS].forEach(function (kind) {
      total += Object.keys(objectField(fieldsBag, kind)).length;
    });
    return total;
  }

  // Only a placement naming a field the payload declares is counted.
  function placedFieldCount(found) {
    var fieldsBag = objectField(found, FIELDS);
    var declared = {};
    [NUMBERS, CHECKS, RADIOS, COMBOS, TEXTS].forEach(function (kind) {
      Object.keys(objectField(fieldsBag, kind)).forEach(function (name) {
        declared[name] = true;
      });
    });
    var total = ZERO;
    [
      objectField(objectField(found, GROUPS), ROWS),
      objectField(objectField(found, PAGES), ROWS)
    ].forEach(function (where) {
      Object.keys(where).forEach(function (name) {
        listField(where, name).forEach(function (one) {
          total += owns(declared, one) ? STEP : ZERO;
        });
      });
    });
    return total;
  }

  function report() {
    var found = held.model;
    return {
      declared: {
        fields: DECLARED_FIELDS.length,
        pages: listField(objectField(found, PAGES), NAMES).length,
        groups: Object.keys(objectField(objectField(found, GROUPS), ROWS)).length,
        rows: declaredFieldCount(found),
        timeframes: listField(objectField(found, PHANTOM_PAGE), TIMEFRAMES).length,
        alts: listField(objectField(found, POOL_PAGE), ALT_ITEMS).length,
        actions: numberOr(found[SOURCE_CONNECT_TOTAL], ZERO),
        steps: listField(objectField(found, WALK), STEPS).length
      },
      held: {
        fields: heldFieldCount(found),
        pages: Object.keys(objectField(objectField(found, PAGES), TITLES)).length,
        groups: Object.keys(objectField(objectField(found, GROUPS), TITLES)).length,
        rows: placedFieldCount(found),
        timeframes: Object.keys(objectField(objectField(found, PHANTOM_PAGE), CHECKED))
          .length,
        alts: listField(objectField(found, POOL_PAGE), ALT_ITEMS).length,
        actions: Object.keys(objectField(found, ACTIONS)).length,
        steps: listField(objectField(found, WALK), STEPS).length
      },
      faults: wizardFaults.slice()
    };
  }

  function setWizard(found) {
    lastPress = null;
    dispatched = [];
    if (!isPlainObject(found)) {
      held = null;
      wizardFaults = [fault(null, null, NOT_AN_OBJECT_FAULT, kindOf(found))];
      return { declared: null, held: null, faults: wizardFaults.slice() };
    }
    held = { model: found };
    wizardFaults = [];
    checkFields(found);
    checkPages(found);
    checkGroups(found);
    checkPlacement(found);
    checkWording(found);
    checkValues(found);
    checkNumbers(found);
    checkAlts(found);
    checkPhantom(found);
    checkColours(found);
    checkBagOrder(found);
    checkMarkup(found);
    checkActions(found);
    return report();
  }

  // Asks METHOD once, clearing asked so a refused first ask is retried.
  function loadWizard(params) {
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
        setWizard(found);
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
    return wizardFaults.slice();
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
      roots.push({ node: target, root: found, handlers: null });
    }
    return found;
  }

  function keepHandlers(target, handlers) {
    roots.forEach(function (pair) {
      if (pair.node === target) {
        pair.handlers = handlers;
      }
    });
    return handlers;
  }

  // Every host this module has drawn into, drawn again from the held payload.
  function redraw() {
    roots.forEach(function (pair) {
      renderWizard(pair.node, null, pair.handlers);
    });
    return roots.length;
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
  function renderWizard(target, found, handlers) {
    if (isPlainObject(found)) {
      setWizard(found);
    }
    var wired = isPlainObject(handlers) ? handlers : {};
    var here = currentPage();
    var bound = {
      onNumber: function (name, value) {
        pressNumber(name, value, wired.onNumber);
      },
      onFlag: function (name, value) {
        pressFlag(name, value, wired.onFlag);
      },
      onIndex: function (name, value) {
        pressIndex(name, value, wired.onIndex);
      },
      onText: function (name, value) {
        pressText(name, value, wired.onText);
      },
      onTimeframe: function (name, value) {
        pressTimeframe(name, value, wired.onTimeframe);
      },
      onTarget: function (at) {
        pressTarget(at, wired.onTarget);
      },
      onVenue: function (page, at) {
        pressVenue(page, at, wired.onVenue);
      },
      onInfo: function () {
        pressButton(SHOW_INFO_STEP, wired.onInfo);
      },
      onWalk: function (name) {
        var moved = pressWalk(name, wired.onWalk);
        closesWith(wired.onClosed);
        return moved;
      }
    };
    var shown = draw(
      target,
      element(Wizard, {
        current: here,
        names: pageNames(),
        titles: objectField(bag(PAGES), TITLES),
        title: bag(WINDOW)[TITLE],
        accessibleName: bag(WINDOW)[ACCESSIBLE_NAME],
        accessibleDescription: bag(WINDOW)[ACCESSIBLE_DESCRIPTION],
        pageTitle: pageTitle(here),
        pageSubtitle: pageSubtitle(here),
        body: here === undefined ? [] : pageBody(here, bound),
        refusal: text(bag(WALK)[REFUSAL_TEXT]) || bag(WALK)[REFUSAL],
        steps: walkSteps(),
        isFinal: bag(PAGES)[IS_FINAL],
        gap: bag(LAYOUT)[GROUPS_SPACING_PX],
        onWalk: bound.onWalk
      })
    );
    keepHandlers(target, wired);
    return shown;
  }

  // The named empty space the main window left, or root itself.
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
    return space === null ? null : renderWizard(space, found, handlers);
  }

  function forget() {
    held = null;
    wizardFaults = [];
    loadFault = null;
    asked = null;
    lastPress = null;
    dispatched = [];
    lastAnswer = null;
    heldSteps = {};
  }

  global.acervatorSetBotWizard = setWizard;
  global.acervatorLoadBotWizard = loadWizard;
  global.acervatorBotWizard = {
    method: METHOD,
    spacePart: PAGE_PART,
    pagePart: PAGE_PART,
    Wizard: Wizard,
    FieldRow: FieldRow,
    FieldGroup: FieldGroup,
    PageRail: PageRail,
    WalkRow: WalkRow,
    TimeframeCheck: TimeframeCheck,
    AltRow: AltRow,
    WarningBox: WarningBox,
    payload: payload,
    declaredNames: declaredNames,
    bagNames: bagNames,
    listNames: listNames,
    field: field,
    bag: bag,
    list: list,
    bagKeys: bagKeys,
    pageNames: pageNames,
    currentPage: currentPage,
    pageTitle: pageTitle,
    pageSubtitle: pageSubtitle,
    pageRows: pageRows,
    pageGroups: pageGroups,
    groupNames: groupNames,
    groupRows: groupRows,
    groupTitle: groupTitle,
    isGroupShown: isGroupShown,
    fieldKind: fieldKind,
    numberSpec: numberSpec,
    comboItems: comboItems,
    heldValue: heldValue,
    rowLabel: rowLabel,
    checkText: checkText,
    radioText: radioText,
    toolTip: toolTip,
    placeholder: placeholder,
    buttonText: buttonText,
    labelText: labelText,
    isMuted: isMuted,
    isWrapped: isWrapped,
    targetItems: targetItems,
    altItems: altItems,
    timeframeNames: timeframeNames,
    timeframeChecked: timeframeChecked,
    timeframeEnabled: timeframeEnabled,
    timeframeToolTip: timeframeToolTip,
    walkSteps: walkSteps,
    actionNames: actionNames,
    calls: calls,
    config: config,
    pageNamesRead: function () {
      return PAGE_NAMES_READ.slice();
    },
    press: press,
    pressNumber: pressNumber,
    pressFlag: pressFlag,
    pressIndex: pressIndex,
    pressText: pressText,
    pressTimeframe: pressTimeframe,
    pressTarget: pressTarget,
    pressVenue: pressVenue,
    pressButton: pressButton,
    pressWalk: pressWalk,
    targetHues: targetHues,
    exchangeItems: exchangeItems,
    exchangeIndex: exchangeIndex,
    pressed: pressed,
    sent: sent,
    steps: steps,
    answer: answer,
    isOpen: isOpen,
    redraw: redraw,
    styleOf: styleOf,
    declarations: declarations,
    stateRules: stateRules,
    sweptDeclarations: sweptDeclarations,
    colour: colour,
    isSwappedAlpha: isSwappedAlpha,
    isReorderedKey: isReorderedKey,
    carriesMarkup: carriesMarkup,
    kinds: kinds,
    notPlainData: notPlainData,
    faults: faults,
    loadError: loadError,
    isLoaded: isLoaded,
    renderWizard: renderWizard,
    spaceIn: spaceIn,
    fill: fill,
    forget: forget
  };
})(window);
