// The settings_dialog.state payload draws this dialog. Its tabs list names
// every page, so no tab name is written here.
(function (global) {
  "use strict";
  var METHOD = "settings_dialog.state";

  var ACCEPTED = "accepted";
  var ACTIONS = "actions";
  var BANNER_FIELD = "banner";
  var BUS = "bus";
  var BUTTON_NAMES = "button_names";
  var BUTTONS = "buttons";
  var CALL_NAMES = "call_names";
  var CALLS = "calls";
  var CONNECT_ORDER = "connect_order";
  var CONNECTIONS = "connections";
  var CONTROL_SPECS = "control_specs";
  var EMITTED = "emitted";
  var ENABLED = "enabled";
  var EXCHANGE_ITEMS = "exchange_items";
  var GROUPS = "groups";
  var HEADINGS = "headings";
  var LAYOUT = "layout";
  var LISTED_EXCHANGES = "listed_exchanges";
  var MESSAGE_BOXES = "message_boxes";
  var METHOD_FIELD = "method";
  var MINIMUM_SIZE = "minimum_size";
  var PAINTED = "painted";
  var PRINTS = "prints";
  var PROCESSED_EVENTS = "processed_events";
  var REJECTED = "rejected";
  var ROWS = "rows";
  var SCROLLING_TABS = "scrolling_tabs";
  var SOUND_TEST_BUTTONS = "sound_test_buttons";
  var SPACING = "spacing";
  var STYLES = "styles";
  var TA_ROWS_FIELD = "ta_rows";
  var TABS = "tabs";
  var TEXT_ROWS = "text_rows";
  var TEXTS = "texts";
  var THREADS = "threads";
  var TIMERS = "timers";
  var TOOLTIPS = "tooltips";
  var VALUES = "values";
  var VISIBLE = "visible";
  var WINDOW_TITLE = "window_title";
  var WING = "wing";

  // DECLARED_FIELDS names every top-level value the payload carries.
  var DECLARED_FIELDS = [
    ACCEPTED,
    ACTIONS,
    BANNER_FIELD,
    BUS,
    BUTTON_NAMES,
    BUTTONS,
    CALL_NAMES,
    CALLS,
    CONNECT_ORDER,
    CONNECTIONS,
    CONTROL_SPECS,
    EMITTED,
    ENABLED,
    EXCHANGE_ITEMS,
    GROUPS,
    HEADINGS,
    LAYOUT,
    LISTED_EXCHANGES,
    MESSAGE_BOXES,
    MINIMUM_SIZE,
    PAINTED,
    PRINTS,
    PROCESSED_EVENTS,
    REJECTED,
    ROWS,
    SCROLLING_TABS,
    SOUND_TEST_BUTTONS,
    SPACING,
    STYLES,
    TA_ROWS_FIELD,
    TABS,
    TEXT_ROWS,
    TEXTS,
    THREADS,
    TIMERS,
    TOOLTIPS,
    VALUES,
    VISIBLE,
    WINDOW_TITLE,
    WING
  ];

  var DECLARED_BAGS = [
    ACTIONS,
    BANNER_FIELD,
    BUS,
    BUTTONS,
    CONNECTIONS,
    ENABLED,
    GROUPS,
    HEADINGS,
    LAYOUT,
    PAINTED,
    SPACING,
    STYLES,
    TEXTS,
    THREADS,
    TIMERS,
    TOOLTIPS,
    VALUES,
    VISIBLE
  ];

  var DECLARED_LISTS = [
    BUTTON_NAMES,
    CALL_NAMES,
    CALLS,
    CONNECT_ORDER,
    CONTROL_SPECS,
    EMITTED,
    EXCHANGE_ITEMS,
    LISTED_EXCHANGES,
    MESSAGE_BOXES,
    MINIMUM_SIZE,
    PRINTS,
    PROCESSED_EVENTS,
    ROWS,
    SCROLLING_TABS,
    SOUND_TEST_BUTTONS,
    TA_ROWS_FIELD,
    TABS,
    TEXT_ROWS
  ];

  // The three per-tab bags, as a list, because a bag would lose their order.
  var PER_TAB_BAGS = [LAYOUT, GROUPS, PAINTED];

  // PER_CONTROL_BAGS names the bags every named widget appears in.
  var PER_CONTROL_BAGS = [VALUES, ENABLED, VISIBLE];

  var NAME = "name";
  var KIND = "kind";
  var TAB = "tab";
  var GROUP_KEY = "group";
  var LABEL_KEY = "label";
  var TEXT_KEY = "text";
  var ITEMS = "items";
  var RANGE = "range";
  var DECIMALS = "decimals";
  var SUFFIX = "suffix";
  var PREFIX = "prefix";
  var PLACEHOLDER = "placeholder";
  var ECHO = "echo";
  var EDITABLE = "editable";
  var MIN_HEIGHT = "min_height";
  var MAX_HEIGHT = "max_height";
  var CURRENT_TEXT = "current_text";

  var CONTENT = "content";
  var GROUP_FORM = "group_form";
  var GROUP_MARGINS = "group_margins";
  var NO_HORIZONTAL_BAR = "no_horizontal_bar";

  var RUN_TIME = "run_time";
  var SUBSCRIBES = "subscribes";
  var EMITS = "emits";
  var BUILT = "built";
  var STARTED = "started";

  var CANCEL = "cancel";
  var SAVE = "save";
  var SAVE_STYLE = "save_style";
  var AI_TEST = "ai_test";
  var AI_TEST_STYLE = "ai_test_style";

  var SMS_GATEWAY = "sms_gateway";
  var SMS_GATEWAY_STYLE = "sms_gateway_style";
  var AI_INFO = "ai_info";
  var AI_INFO_STYLE = "ai_info_style";

  var SHOWN = "shown";
  var LEAD = "lead";
  var TAIL = "tail";
  var PIECES = "pieces";
  var MARKS = "marks";
  var STRONG_OPEN = "strong_open";
  var STRONG_CLOSE = "strong_close";
  var STRONG_WEIGHT = "strong_weight";
  var STYLE_SHEET = "style_sheet";
  var WORD_WRAP = "word_wrap";
  var TINT = "tint";
  var RGB = "rgb";
  var ALPHA = "alpha";
  var SCALE = "scale";
  var RECIPROCAL = "reciprocal";
  var FILL = "fill";
  var EDGE = "edge";
  var COLOUR_MARKS = "colour_marks";
  var OPEN_MARK = "open";
  var JOIN_MARK = "join";
  var CLOSE_MARK = "close";
  var BORDER_WIDTH = "border_width_px";
  var BORDER_KIND = "border_kind";
  var PADDING = "padding_px";
  var RADIUS = "radius_px";

  // Each layout role below names one step this module draws.
  var ROW_ROLE = "row";
  var SCROLL_ROLE = "scroll";
  var GROUP_ROLE = "group";
  var LABEL_ROLE = "label";
  var TEXT_ROLE = "text";
  var BUTTON_ROLE = "button";
  var STRETCH_ROLE = "stretch";
  var BANNER_ROLE = "banner";
  var TA_ROWS_ROLE = "ta_rows";
  var SOUND_ROW_ROLE = "sound_row";
  var ADD_GROUP_ROLE = "add_group";

  var TEXT_AREA_KIND = "text_area";
  var COMBO_TEXT_KIND = "combo_text";
  var COMBO_DATA_KIND = "combo_data";
  var CHECK_KIND = "check";
  var RADIO_KIND = "radio";
  var SPIN_KIND = "spin";
  var DOUBLE_SPIN_KIND = "double_spin";
  var SLIDER_KIND = "slider";
  var LIST_KIND = "list";

  var PASSWORD_ECHO = "password";

  var MISSING_FAULT = "missing";
  var NOT_AN_OBJECT_FAULT = "not-an-object";
  var NOT_A_BAG_FAULT = "not-a-bag";
  var NOT_A_LIST_FAULT = "not-a-list";
  var SHORT_LIST_FAULT = "short-list";
  var SWAPPED_ALPHA_FAULT = "swapped-alpha";
  var REORDERED_KEY_FAULT = "reordered-key";
  var DISAGREES_FAULT = "disagrees";
  var DUPLICATE_NAME_FAULT = "duplicate-name";
  var UNKNOWN_STEP_FAULT = "unknown-step";
  var UNKNOWN_NAME_FAULT = "unknown-name";
  var OUT_OF_RANGE_FAULT = "out-of-range";
  var MARKUP_FAULT = "markup";
  var NOT_CSS_FAULT = "not-css";
  var NEVER_FILLED_FAULT = "never-filled";

  var AT = "at:";
  var PATH_SPLIT = ".";
  var EMPTY = "";

  var NO_BRIDGE = "the preload bridge is not present";

  // Qt paints this gradient by name and no browser stylesheet runs it.
  var QT_ONLY = "qlineargradient";

  // MARKUP_OPEN starts a tag a Qt rich-text label reads as formatting.
  var MARKUP_OPEN = "<";

  var DIALOG_CLASS = "acervator-settings-dialog";

  var DIV_TAG = "div";
  var SPAN_TAG = "span";
  var STRONG_TAG = "strong";
  var BUTTON_TAG = "button";
  var INPUT_TAG = "input";
  var TEXTAREA_TAG = "textarea";
  var SELECT_TAG = "select";
  var OPTION_TAG = "option";
  var LIST_TAG = "ul";
  var LIST_ITEM_TAG = "li";

  var TEXT_TYPE = "text";
  var PASSWORD_TYPE = "password";
  var NUMBER_TYPE = "number";
  var CHECKBOX_TYPE = "checkbox";
  var RADIO_TYPE = "radio";
  var RANGE_TYPE = "range";

  var DIALOG_PART = "settings-dialog";
  var TITLE_PART = "window-title";
  var TAB_BAR_PART = "tab-bar";
  var TAB_BUTTON_PART = "tab-button";
  var TAB_PAGES_PART = "tab-pages";
  var TAB_PAGE_PART = "tab-page";
  var BLOCK_PART = "block";
  var FORM_ROW_PART = "form-row";
  var ROW_LABEL_PART = "row-label";
  var CHECK_TEXT_PART = "check-text";
  var VALUE_PREFIX_PART = "value-prefix";
  var VALUE_SUFFIX_PART = "value-suffix";
  var GROUP_PART = "group";
  var GROUP_TITLE_PART = "group-title";
  var GROUP_BODY_PART = "group-body";
  var LABEL_PART = "label";
  var TEXT_PART = "named-text";
  var BUTTON_PART = "button";
  var STRETCH_PART = "stretch";
  var BANNER_PART = "banner";
  var BANNER_LEAD_PART = "banner-lead";
  var BANNER_TAIL_PART = "banner-tail";
  var CONTROL_PART = "control";
  var COMBO_ITEM_PART = "combo-item";
  var LIST_BOX_PART = "list-box";
  var LIST_ITEM_PART = "list-item";
  var TA_ROWS_PART = "ta-rows";
  var TA_ROW_PART = "ta-row";
  var TA_LABEL_PART = "ta-label";
  var TA_SLIDER_PART = "ta-slider";
  var TA_VALUE_PART = "ta-value";
  var SOUND_ROW_PART = "sound-row";
  var SOUND_BUTTON_PART = "sound-button";
  var FOOTER_PART = "footer";
  var STEP_PART = "dialog-step";

  // PAGE_PART is the space the renderer leaves for this window.
  var PAGE_PART = "settings-dialog-page";

  var PART_ATTR = "data-part";
  var KEY_ATTR = "data-key";
  var NAME_ATTR = "data-name";
  var INDEX_ATTR = "data-index";
  var KIND_ATTR = "data-kind";
  var TAB_ATTR = "data-tab";
  var ROLE_ATTR = "data-role";
  var COUNT_ATTR = "data-count";
  var SHOWN_ATTR = "data-shown";
  var WRAP_ATTR = "data-word-wrap";
  var ENABLED_ATTR = "data-enabled";
  var CURRENT_ATTR = "data-current";
  var PAINTED_ATTR = "data-painted";
  var STYLED_ATTR = "data-styled";
  var SCROLLS_ATTR = "data-scrolls";
  var BAR_ATTR = "data-horizontal-bar";
  var MARGINS_ATTR = "data-margins";
  var SPACING_ATTR = "data-spacing";
  var RANGE_LOW_ATTR = "data-low";
  var RANGE_HIGH_ATTR = "data-high";
  var STEP_ATTR = "data-step";
  var ECHO_ATTR = "data-echo";
  var HEIGHT_ATTR = "data-height";
  var TICKED_ATTR = "data-ticked";
  var ARIA_LABEL = "aria-label";
  var TITLE_ATTR = "title";

  var SELECT_OPEN = "[";
  var SELECT_IS = "=\"";
  var SELECT_CLOSE = "\"]";

  // HASH_ESCAPE decodes to the mark every colour opens with.
  var HASH_ESCAPE = "%23";
  var HEX_MARK = decodeURIComponent(HASH_ESCAPE);
  // SWAPPED_LENGTH is the width of a colour written with eight hex digits.
  var SWAPPED_LENGTH = HEX_MARK.length + "aabbccdd".length;

  var DIGITS = "0123456789";
  var HEX_LETTERS = "0123456789abcdefABCDEF";

  var PX = "px";
  var FLEX = "flex";
  var DISPLAY_NONE = "none";
  var ROW_DIRECTION = "row";
  var COLUMN_DIRECTION = "column";
  var NOWRAP = "nowrap";
  var NORMAL = "normal";
  var AUTO = "auto";
  var HIDDEN = "hidden";
  var STRING_KIND = "string";
  var NUMBER_KIND = "number";
  var BOOLEAN_KIND = "boolean";
  var FUNCTION_KIND = "function";
  var NULL_KIND = "null";

  var ZERO = Number(EMPTY);
  var STEP = Number(true);
  var SECOND = STEP + STEP;
  var THIRD = SECOND + STEP;

  // A ta_rows row carries a label, a position, a figure and its slider's name.
  var TA_ROW_WIDTH = THIRD + STEP;

  // Every drawn control and TA slider carries both, so one selector reaches all.
  var DRAWN_SELECT = SELECT_OPEN + NAME_ATTR + "]" + SELECT_OPEN + KIND_ATTR + "]";

  var held = null;
  var dialogFaults = [];
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
    return value === null ? NULL_KIND : typeof value;
  }

  function objectField(node, field) {
    return isPlainObject(node) && isPlainObject(node[field]) ? node[field] : {};
  }

  function listField(node, field) {
    return isPlainObject(node) && Array.isArray(node[field]) ? node[field] : [];
  }

  function at(list, index) {
    return Array.isArray(list) ? list[index] : undefined;
  }

  function fault(where, field, kind, detail) {
    return { where: where, field: field, fault: kind, detail: detail };
  }

  function note(where, field, kind, detail) {
    dialogFaults.push(fault(where, field, kind, detail));
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

  function isFiniteNumber(value) {
    return typeof value === NUMBER_KIND && isFinite(value);
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

  // Every hex colour in one whole rule, its state blocks read as well as base.
  function coloursIn(sheet) {
    var printed = String(sheet);
    var found = [];
    var cursor = ZERO;
    while (cursor < printed.length) {
      if (printed.charAt(cursor) !== HEX_MARK) {
        cursor += STEP;
        continue;
      }
      var end = cursor + STEP;
      while (end < printed.length && HEX_LETTERS.indexOf(printed.charAt(end)) >= ZERO) {
        end += STEP;
      }
      found.push(printed.slice(cursor, end));
      cursor = end;
    }
    return found;
  }

  function colour(value) {
    var api = global.acervatorCells;
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

  // stateRules reads the blocks Qt paints on hover.
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

  function tabNames() {
    return listField(model(), TABS).slice();
  }

  function scrollingTabs() {
    return listField(model(), SCROLLING_TABS).slice();
  }

  function layoutOf(tab) {
    var bag = objectField(model(), LAYOUT);
    return owns(bag, tab) ? bag[tab] : undefined;
  }

  function groupTitlesOn(tab) {
    var bag = objectField(model(), GROUPS);
    return Array.isArray(bag[tab]) ? bag[tab].slice() : [];
  }

  function paintedOn(tab) {
    var bag = objectField(model(), PAINTED);
    return Array.isArray(bag[tab]) ? bag[tab].slice() : [];
  }

  function specs() {
    return listField(model(), CONTROL_SPECS);
  }

  function specNames() {
    return specs().map(function (one) {
      return text(isPlainObject(one) ? one[NAME] : undefined);
    });
  }

  // specFor answers by name, never by where a spec sits.
  function specFor(name) {
    var found;
    specs().forEach(function (one) {
      if (isPlainObject(one) && String(one[NAME]) === String(name)) {
        found = one;
      }
    });
    return found;
  }

  function fromBag(field, name) {
    var bag = objectField(model(), field);
    return owns(bag, name) ? bag[name] : undefined;
  }

  function valueOf(name) {
    return fromBag(VALUES, name);
  }

  function enabledOf(name) {
    return fromBag(ENABLED, name);
  }

  function visibleOf(name) {
    return fromBag(VISIBLE, name);
  }

  function tooltipOf(name) {
    return fromBag(TOOLTIPS, name);
  }

  function textNamed(name) {
    return fromBag(TEXTS, name);
  }

  function styleNamed(name) {
    return fromBag(STYLES, name);
  }

  function buttonNamed(name) {
    return fromBag(BUTTONS, name);
  }

  function headingNamed(name) {
    return fromBag(HEADINGS, name);
  }

  function rows() {
    return listField(model(), ROWS);
  }

  // rowNames answers with the name each labelled row carries last.
  function rowNames() {
    return rows().map(function (row) {
      return text(at(row, THIRD));
    });
  }

  function rowFor(name) {
    var found;
    rows().forEach(function (row) {
      if (Array.isArray(row) && String(at(row, THIRD)) === String(name)) {
        found = row;
      }
    });
    return found;
  }

  function rowLabel(name) {
    var row = rowFor(name);
    return row === undefined ? undefined : text(at(row, SECOND));
  }

  function textRows() {
    return listField(model(), TEXT_ROWS);
  }

  function textRowNames() {
    return textRows().map(function (row) {
      return text(at(row, THIRD));
    });
  }

  function taRows() {
    return listField(model(), TA_ROWS_FIELD);
  }

  // name is the slider's control name, the key the engine weights, the same
  // column TaRows draws into the row's NAME_ATTR.
  function taRowNamed(name) {
    var found;
    taRows().forEach(function (row) {
      if (Array.isArray(row) && String(at(row, THIRD)) === String(name)) {
        found = row;
      }
    });
    return found;
  }

  function soundButtons() {
    return listField(model(), SOUND_TEST_BUTTONS);
  }

  function soundButtonNamed(name) {
    var found;
    soundButtons().forEach(function (row) {
      if (Array.isArray(row) && String(at(row, STEP)) === String(name)) {
        found = row;
      }
    });
    return found;
  }

  function exchangeItems() {
    return listField(model(), EXCHANGE_ITEMS);
  }

  function exchangeItemNamed(id) {
    var found;
    exchangeItems().forEach(function (row) {
      if (Array.isArray(row) && String(at(row, STEP)) === String(id)) {
        found = row;
      }
    });
    return found;
  }

  // The items one combo draws, the exchange list read from the payload.
  function comboItems(name) {
    var spec = specFor(name);
    if (!isPlainObject(spec)) {
      return [];
    }
    if (Array.isArray(spec[ITEMS])) {
      return spec[ITEMS];
    }
    return exchangeItems();
  }

  function comboItemText(one) {
    return Array.isArray(one) ? text(at(one, ZERO)) : text(one);
  }

  function comboItemKey(one) {
    return Array.isArray(one) ? text(at(one, STEP)) : text(one);
  }

  function buttonNames() {
    return listField(model(), BUTTON_NAMES);
  }

  // One button's wiring name found by the words it draws, never by its place.
  function nameForButton(words) {
    var found;
    buttonNames().forEach(function (pair) {
      if (Array.isArray(pair) && String(at(pair, ZERO)) === String(words)) {
        found = text(at(pair, STEP));
      }
    });
    return found;
  }

  function connectOrder() {
    return listField(model(), CONNECT_ORDER);
  }

  function connectSignals() {
    return connectOrder().map(function (pair) {
      return text(at(pair, ZERO));
    });
  }

  function handlerFor(signal) {
    var found;
    connectOrder().forEach(function (pair) {
      if (Array.isArray(pair) && String(at(pair, ZERO)) === String(signal)) {
        found = text(at(pair, STEP));
      }
    });
    return found;
  }

  // handlersOn lists the handlers one name runs, in wired order.
  function handlersOn(name) {
    var found = [];
    connectOrder().forEach(function (pair) {
      var signal = String(at(pair, ZERO)).split(PATH_SPLIT);
      if (signal[ZERO] === String(name)) {
        found.push(text(at(pair, STEP)));
      }
    });
    return found;
  }

  function calls() {
    return listField(model(), CALLS).slice();
  }

  function callNames() {
    return listField(model(), CALL_NAMES).slice();
  }

  function banner() {
    return objectField(model(), BANNER_FIELD);
  }

  function bannerMarks() {
    return objectField(banner(), MARKS);
  }

  function bannerPieces() {
    return listField(banner(), PIECES).slice();
  }

  // rebuiltBanner names the marked-up line one set of pieces builds.
  function rebuiltBanner() {
    var one = banner();
    var marks = bannerMarks();
    return (
      String(marks[STRONG_OPEN]) +
      String(one[LEAD]) +
      String(marks[STRONG_CLOSE]) +
      String(one[TAIL])
    );
  }

  // A whole-number alpha turned into the fraction a browser reads.
  function bannerColour(alpha) {
    var one = banner();
    var marks = objectField(one, COLOUR_MARKS);
    var scale = objectField(one, ALPHA)[RECIPROCAL];
    var parts = listField(one, RGB).map(function (value) {
      return String(value);
    });
    parts.push(String(Number(alpha) * Number(scale)));
    return (
      String(marks[OPEN_MARK]) +
      parts.join(String(marks[JOIN_MARK])) +
      String(marks[CLOSE_MARK])
    );
  }

  function bannerStyle() {
    var one = banner();
    var alpha = objectField(one, ALPHA);
    return {
      backgroundColor: bannerColour(alpha[FILL]),
      color: colour(one[TINT]),
      borderStyle: text(one[BORDER_KIND]),
      borderWidth: length(one[BORDER_WIDTH]),
      borderColor: bannerColour(alpha[EDGE]),
      padding: length(one[PADDING]),
      borderRadius: length(one[RADIUS]),
      whiteSpace: one[WORD_WRAP] === true ? NORMAL : NOWRAP
    };
  }

  function spacingBag(field) {
    return objectField(objectField(model(), SPACING), field);
  }

  function contentSpacing(tab) {
    var bag = spacingBag(CONTENT);
    return owns(bag, tab) ? bag[tab] : undefined;
  }

  function groupSpacing(title) {
    var bag = spacingBag(GROUP_FORM);
    return owns(bag, title) ? bag[title] : undefined;
  }

  function groupMargins(title) {
    var bag = spacingBag(GROUP_MARGINS);
    return Array.isArray(bag[title]) ? bag[title].slice() : [];
  }

  function horizontalBarOff(tab) {
    var listed = listField(objectField(model(), SPACING), NO_HORIZONTAL_BAR);
    return listed.indexOf(tab) >= ZERO;
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

  function checkTabs(found) {
    var named = listField(found, TABS);
    var seen = {};
    named.forEach(function (tab, index) {
      if (owns(seen, String(tab))) {
        note(AT + String(index), TABS, DUPLICATE_NAME_FAULT, tab);
      }
      seen[String(tab)] = true;
      PER_TAB_BAGS.forEach(function (field) {
        if (!owns(objectField(found, field), String(tab))) {
          note(AT + String(index), field, MISSING_FAULT, tab);
        }
      });
    });
    PER_TAB_BAGS.forEach(function (field) {
      Object.keys(objectField(found, field)).forEach(function (key) {
        if (named.indexOf(key) < ZERO) {
          note(null, field, UNKNOWN_NAME_FAULT, key);
        }
      });
    });
    listField(found, SCROLLING_TABS).forEach(function (tab) {
      if (named.indexOf(tab) < ZERO) {
        note(null, SCROLLING_TABS, UNKNOWN_NAME_FAULT, tab);
      }
    });
  }

  function checkSpecs(found) {
    var seen = {};
    listField(found, CONTROL_SPECS).forEach(function (one, index) {
      if (!isPlainObject(one)) {
        note(AT + String(index), CONTROL_SPECS, NOT_A_BAG_FAULT, kindOf(one));
        return;
      }
      var name = String(one[NAME]);
      if (owns(seen, name)) {
        note(AT + String(index), CONTROL_SPECS, DUPLICATE_NAME_FAULT, name);
      }
      seen[name] = true;
      PER_CONTROL_BAGS.forEach(function (field) {
        if (!owns(objectField(found, field), name)) {
          note(AT + String(index), field, MISSING_FAULT, name);
        }
      });
      if (listField(found, TABS).indexOf(one[TAB]) < ZERO) {
        note(AT + String(index), CONTROL_SPECS, UNKNOWN_NAME_FAULT, one[TAB]);
      }
    });
    var wired = {};
    listField(found, BUTTON_NAMES).forEach(function (pair) {
      wired[String(at(pair, STEP))] = true;
    });
    Object.keys(objectField(found, ENABLED)).forEach(function (key) {
      if (!owns(seen, key) && !owns(wired, key)) {
        note(null, ENABLED, UNKNOWN_NAME_FAULT, key);
      }
    });
    Object.keys(objectField(found, VISIBLE)).forEach(function (key) {
      if (!owns(seen, key)) {
        note(null, VISIBLE, UNKNOWN_NAME_FAULT, key);
      }
    });
  }

  // checkRanges reads one seeded value against the smallest and largest held.
  function checkRanges(found) {
    listField(found, CONTROL_SPECS).forEach(function (one) {
      if (!isPlainObject(one) || !Array.isArray(one[RANGE])) {
        return;
      }
      var name = String(one[NAME]);
      var seeded = objectField(found, VALUES)[name];
      var low = at(one[RANGE], ZERO);
      var high = at(one[RANGE], STEP);
      if (!isFiniteNumber(seeded) || !isFiniteNumber(low) || !isFiniteNumber(high)) {
        return;
      }
      if (seeded < low || seeded > high) {
        note(null, VALUES, OUT_OF_RANGE_FAULT, name);
      }
    });
  }

  function checkRows(found) {
    var named = {};
    listField(found, CONTROL_SPECS).forEach(function (one) {
      if (isPlainObject(one)) {
        named[String(one[NAME])] = true;
      }
    });
    listField(found, TEXT_ROWS).forEach(function (one) {
      named[String(at(one, THIRD))] = true;
    });
    var drawn = [];
    listField(found, ROWS).forEach(function (row, index) {
      if (!Array.isArray(row) || row.length !== THIRD + STEP) {
        note(AT + String(index), ROWS, SHORT_LIST_FAULT, kindOf(row));
        return;
      }
      var name = String(at(row, THIRD));
      if (!owns(named, name)) {
        note(AT + String(index), ROWS, UNKNOWN_NAME_FAULT, name);
      }
      if (drawn.indexOf(name) >= ZERO) {
        note(AT + String(index), ROWS, DUPLICATE_NAME_FAULT, name);
      }
      drawn.push(name);
    });
    listField(found, TEXT_ROWS).forEach(function (one, index) {
      if (drawn.indexOf(String(at(one, THIRD))) < ZERO) {
        note(AT + String(index), TEXT_ROWS, MISSING_FAULT, at(one, THIRD));
      }
    });
  }

  function checkConnections(found) {
    var order = listField(found, CONNECT_ORDER);
    var wired = objectField(found, ACTIONS);
    var seen = {};
    order.forEach(function (pair, index) {
      if (!Array.isArray(pair) || pair.length !== SECOND) {
        note(AT + String(index), CONNECT_ORDER, NOT_A_LIST_FAULT, kindOf(pair));
        return;
      }
      var signal = String(at(pair, ZERO));
      if (owns(seen, signal)) {
        note(AT + String(index), CONNECT_ORDER, DUPLICATE_NAME_FAULT, signal);
      }
      seen[signal] = true;
      if (!owns(wired, signal)) {
        note(AT + String(index), ACTIONS, MISSING_FAULT, signal);
        return;
      }
      if (wired[signal] !== at(pair, STEP)) {
        note(AT + String(index), ACTIONS, DISAGREES_FAULT, signal);
      }
    });
    Object.keys(wired).forEach(function (signal) {
      if (!owns(seen, signal)) {
        note(null, ACTIONS, UNKNOWN_NAME_FAULT, signal);
      }
    });
    var counted = objectField(found, CONNECTIONS)[RUN_TIME];
    if (counted !== order.length) {
      note(null, CONNECTIONS, DISAGREES_FAULT, counted);
    }
    if (order.length && counted === ZERO) {
      note(null, CONNECTIONS, NEVER_FILLED_FAULT, RUN_TIME);
    }
  }

  function checkSteps(found) {
    var named = listField(found, CALL_NAMES);
    listField(found, CALLS).forEach(function (one, index) {
      if (named.indexOf(at(one, ZERO)) < ZERO) {
        note(AT + String(index), CALLS, UNKNOWN_STEP_FAULT, at(one, ZERO));
      }
    });
  }

  function checkBanner(found) {
    var one = objectField(found, BANNER_FIELD);
    var marks = objectField(one, MARKS);
    [LEAD, TAIL, SHOWN, TEXT_KEY, STYLE_SHEET, TINT].forEach(function (name) {
      if (!owns(one, name)) {
        note(null, BANNER_FIELD, MISSING_FAULT, name);
      }
    });
    var pieces = listField(one, PIECES);
    if (pieces.length !== SECOND) {
      note(null, PIECES, SHORT_LIST_FAULT, pieces.length);
    } else if (at(pieces, ZERO) !== one[LEAD] || at(pieces, STEP) !== one[TAIL]) {
      note(null, PIECES, DISAGREES_FAULT, LEAD);
    }
    var rebuilt =
      String(marks[STRONG_OPEN]) +
      String(one[LEAD]) +
      String(marks[STRONG_CLOSE]) +
      String(one[TAIL]);
    if (owns(one, TEXT_KEY) && rebuilt !== one[TEXT_KEY]) {
      note(null, BANNER_FIELD, DISAGREES_FAULT, TEXT_KEY);
    }
    pieces.forEach(function (piece, index) {
      if (typeof piece === STRING_KIND && carries(piece, MARKUP_OPEN)) {
        note(AT + String(index), PIECES, MARKUP_FAULT, MARKUP_OPEN);
      }
    });
    var alpha = objectField(one, ALPHA);
    if (isFiniteNumber(alpha[SCALE]) && isFiniteNumber(alpha[RECIPROCAL])) {
      if (alpha[SCALE] * alpha[RECIPROCAL] !== STEP) {
        note(null, ALPHA, DISAGREES_FAULT, RECIPROCAL);
      }
    }
    if (listField(one, RGB).length !== THIRD) {
      note(null, RGB, SHORT_LIST_FAULT, listField(one, RGB).length);
    }
  }

  function checkPaired(found) {
    listField(found, TA_ROWS_FIELD).forEach(function (row, index) {
      if (!Array.isArray(row) || row.length !== TA_ROW_WIDTH) {
        note(AT + String(index), TA_ROWS_FIELD, SHORT_LIST_FAULT, kindOf(row));
      }
    });
    listField(found, SOUND_TEST_BUTTONS).forEach(function (row, index) {
      if (!Array.isArray(row) || row.length !== THIRD) {
        note(AT + String(index), SOUND_TEST_BUTTONS, SHORT_LIST_FAULT, kindOf(row));
      }
    });
    listField(found, EXCHANGE_ITEMS).forEach(function (row, index) {
      if (!Array.isArray(row) || row.length !== SECOND) {
        note(AT + String(index), EXCHANGE_ITEMS, SHORT_LIST_FAULT, kindOf(row));
      }
    });
    listField(found, BUTTON_NAMES).forEach(function (row, index) {
      if (!Array.isArray(row) || row.length !== SECOND) {
        note(AT + String(index), BUTTON_NAMES, SHORT_LIST_FAULT, kindOf(row));
      }
    });
    var size = listField(found, MINIMUM_SIZE);
    if (size.length !== SECOND) {
      note(null, MINIMUM_SIZE, SHORT_LIST_FAULT, size.length);
    }
  }

  function sheetsOf(found) {
    var sheets = [];
    Object.keys(objectField(found, STYLES)).forEach(function (name) {
      sheets.push({ field: STYLES, where: name, sheet: objectField(found, STYLES)[name] });
    });
    [SAVE_STYLE, AI_TEST_STYLE].forEach(function (name) {
      sheets.push({ field: BUTTONS, where: name, sheet: objectField(found, BUTTONS)[name] });
    });
    Object.keys(objectField(found, HEADINGS)).forEach(function (name) {
      sheets.push({
        field: HEADINGS,
        where: name,
        sheet: objectField(found, HEADINGS)[name]
      });
    });
    sheets.push({
      field: BANNER_FIELD,
      where: STYLE_SHEET,
      sheet: objectField(found, BANNER_FIELD)[STYLE_SHEET]
    });
    sheets.push({
      field: BANNER_FIELD,
      where: TINT,
      sheet: objectField(found, BANNER_FIELD)[TINT]
    });
    return sheets;
  }

  function checkColours(found) {
    sheetsOf(found).forEach(function (one) {
      coloursIn(one.sheet).forEach(function (written) {
        if (isSwappedAlpha(written)) {
          note(one.where, one.field, SWAPPED_ALPHA_FAULT, written);
        }
      });
      wholeSheet(one.sheet).forEach(function (written) {
        if (carries(written.value, QT_ONLY)) {
          note(one.where, one.field, NOT_CSS_FAULT, written.property);
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

  // checkDrawnMarkup sweeps every drawn word for markup a Qt label reads.
  function checkDrawnMarkup(found) {
    Object.keys(objectField(found, TEXTS)).forEach(function (name) {
      if (name !== BANNER_ROLE) {
        checkMarkup(name, TEXTS, objectField(found, TEXTS)[name]);
      }
    });
    Object.keys(objectField(found, VALUES)).forEach(function (name) {
      checkMarkup(name, VALUES, objectField(found, VALUES)[name]);
    });
    listField(found, LISTED_EXCHANGES).forEach(function (one, index) {
      checkMarkup(AT + String(index), LISTED_EXCHANGES, one);
    });
    listField(found, TA_ROWS_FIELD).forEach(function (row, index) {
      checkMarkup(AT + String(index), TA_ROWS_FIELD, at(row, ZERO));
    });
    listField(found, EXCHANGE_ITEMS).forEach(function (row, index) {
      checkMarkup(AT + String(index), EXCHANGE_ITEMS, at(row, ZERO));
    });
    Object.keys(objectField(found, BUTTONS)).forEach(function (name) {
      if (name !== SAVE_STYLE && name !== AI_TEST_STYLE) {
        checkMarkup(name, BUTTONS, objectField(found, BUTTONS)[name]);
      }
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
    if (!declarations(value).length) {
      return { color: colour(value) };
    }
    return styleOf(value);
  }

  function partProps(part, style) {
    var props = { className: DIALOG_CLASS };
    props[PART_ATTR] = part;
    if (style !== undefined) {
      props.style = style;
    }
    return props;
  }

  function Stretch() {
    return element(DIV_TAG, partProps(STRETCH_PART, { flexGrow: STEP }), null);
  }

  // The banner draws its emphasis as an element and its words as characters.
  function Banner() {
    var one = banner();
    var props = partProps(BANNER_PART, bannerStyle());
    props[SHOWN_ATTR] = text(one[SHOWN]);
    props[WRAP_ATTR] = text(one[WORD_WRAP]);
    props.hidden = one[SHOWN] !== true;
    var leadProps = partProps(BANNER_LEAD_PART, {
      fontWeight: text(bannerMarks()[STRONG_WEIGHT])
    });
    var tailProps = partProps(BANNER_TAIL_PART);
    return element(
      DIV_TAG,
      props,
      element(STRONG_TAG, leadProps, text(one[LEAD])),
      element(SPAN_TAG, tailProps, text(one[TAIL]))
    );
  }

  function PlainLabel(props) {
    var one = partProps(LABEL_PART, paintedStyle(props.sheet));
    one[KEY_ATTR] = text(props.words);
    one[STYLED_ATTR] = String(Boolean(declarations(props.sheet).length));
    return element(SPAN_TAG, one, text(props.words));
  }

  function NamedText(props) {
    var sheet = styleNamed(props.name);
    var one = partProps(TEXT_PART, paintedStyle(sheet));
    one[NAME_ATTR] = text(props.name);
    one[PAINTED_ATTR] = String(sheet !== undefined && sheet !== EMPTY);
    one[STYLED_ATTR] = String(Boolean(declarations(sheet).length));
    return element(SPAN_TAG, one, text(textNamed(props.name)));
  }

  function sheetForButton(words) {
    if (words === buttonNamed(SAVE)) {
      return buttonNamed(SAVE_STYLE);
    }
    if (words === buttonNamed(AI_TEST)) {
      return buttonNamed(AI_TEST_STYLE);
    }
    return undefined;
  }

  // buttonEnabled answers false for a button the enabled bag greys out.
  function buttonEnabled(name) {
    var found = enabledOf(name);
    return found === undefined ? true : found === true;
  }

  function DialogButton(props) {
    var sheet = sheetForButton(props.words);
    var one = partProps(BUTTON_PART, paintedStyle(sheet));
    one[KEY_ATTR] = text(props.words);
    one[NAME_ATTR] = text(props.name);
    one[ENABLED_ATTR] = String(buttonEnabled(props.name));
    one.disabled = !buttonEnabled(props.name);
    if (tooltipOf(props.name) !== undefined) {
      one[TITLE_ATTR] = text(tooltipOf(props.name));
    }
    return element(BUTTON_TAG, one, text(props.words));
  }

  function controlTag(kind) {
    if (kind === TEXT_AREA_KIND) {
      return TEXTAREA_TAG;
    }
    if (kind === COMBO_TEXT_KIND || kind === COMBO_DATA_KIND) {
      return SELECT_TAG;
    }
    if (kind === LIST_KIND) {
      return LIST_TAG;
    }
    return INPUT_TAG;
  }

  function inputType(spec) {
    var kind = spec[KIND];
    if (kind === CHECK_KIND) {
      return CHECKBOX_TYPE;
    }
    if (kind === RADIO_KIND) {
      return RADIO_TYPE;
    }
    if (kind === SLIDER_KIND) {
      return RANGE_TYPE;
    }
    if (kind === SPIN_KIND || kind === DOUBLE_SPIN_KIND) {
      return NUMBER_TYPE;
    }
    return spec[ECHO] === PASSWORD_ECHO ? PASSWORD_TYPE : TEXT_TYPE;
  }

  function ComboItem(props) {
    var one = partProps(COMBO_ITEM_PART);
    one[KEY_ATTR] = comboItemKey(props.item);
    one[INDEX_ATTR] = text(props.at);
    one.value = text(props.at);
    return element(OPTION_TAG, one, comboItemText(props.item));
  }

  function ListItem(props) {
    var one = partProps(LIST_ITEM_PART);
    one[KEY_ATTR] = text(props.words);
    one[INDEX_ATTR] = text(props.at);
    return element(LIST_ITEM_TAG, one, text(props.words));
  }

  function controlStyle(spec) {
    var style = {};
    if (spec[MIN_HEIGHT] !== undefined) {
      style.minHeight = length(spec[MIN_HEIGHT]);
    }
    if (spec[MAX_HEIGHT] !== undefined) {
      style.maxHeight = length(spec[MAX_HEIGHT]);
    }
    return style;
  }

  function controlProps(spec, name) {
    var one = partProps(CONTROL_PART, controlStyle(spec));
    one[NAME_ATTR] = text(name);
    one[KIND_ATTR] = text(spec[KIND]);
    one[ENABLED_ATTR] = String(enabledOf(name) === true);
    one[SHOWN_ATTR] = String(visibleOf(name) === true);
    one.disabled = enabledOf(name) !== true;
    one.hidden = visibleOf(name) !== true;
    if (tooltipOf(name) !== undefined) {
      one[TITLE_ATTR] = text(tooltipOf(name));
    }
    if (spec[PLACEHOLDER] !== undefined) {
      one.placeholder = text(spec[PLACEHOLDER]);
    }
    if (Array.isArray(spec[RANGE])) {
      one[RANGE_LOW_ATTR] = text(at(spec[RANGE], ZERO));
      one[RANGE_HIGH_ATTR] = text(at(spec[RANGE], STEP));
      one.min = text(at(spec[RANGE], ZERO));
      one.max = text(at(spec[RANGE], STEP));
    }
    if (spec[DECIMALS] !== undefined) {
      one[STEP_ATTR] = text(spec[DECIMALS]);
    }
    if (spec[SUFFIX] !== undefined || spec[PREFIX] !== undefined) {
      one[KEY_ATTR] = text(spec[PREFIX]) || text(spec[SUFFIX]);
    }
    if (spec[ECHO] !== undefined) {
      one[ECHO_ATTR] = text(spec[ECHO]);
    }
    if (spec[MIN_HEIGHT] !== undefined || spec[MAX_HEIGHT] !== undefined) {
      one[HEIGHT_ATTR] = text(
        spec[MIN_HEIGHT] === undefined ? spec[MAX_HEIGHT] : spec[MIN_HEIGHT]
      );
    }
    if (spec[EDITABLE] !== undefined) {
      one[CURRENT_ATTR] = text(spec[CURRENT_TEXT]);
    }
    return one;
  }

  function Control(props) {
    var spec = specFor(props.name);
    if (!isPlainObject(spec)) {
      var missing = partProps(CONTROL_PART);
      missing[NAME_ATTR] = text(props.name);
      return element(DIV_TAG, missing, null);
    }
    var kind = spec[KIND];
    var seeded = valueOf(props.name);
    var one = controlProps(spec, props.name);
    var tag = controlTag(kind);
    if (tag === LIST_TAG) {
      var lines = Array.isArray(seeded) ? seeded : [];
      var listProps = partProps(LIST_BOX_PART, controlStyle(spec));
      listProps[NAME_ATTR] = text(props.name);
      listProps[KIND_ATTR] = text(kind);
      listProps[COUNT_ATTR] = text(lines.length);
      listProps[ENABLED_ATTR] = String(enabledOf(props.name) === true);
      listProps[SHOWN_ATTR] = String(visibleOf(props.name) === true);
      listProps.hidden = visibleOf(props.name) !== true;
      return element(
        LIST_TAG,
        listProps,
        lines.map(function (words, index) {
          return element(ListItem, { key: String(index), words: words, at: index });
        })
      );
    }
    if (tag === SELECT_TAG) {
      var items = comboItems(props.name);
      one[COUNT_ATTR] = text(items.length);
      one[INDEX_ATTR] = text(seeded);
      one.defaultValue = text(seeded);
      return element(
        SELECT_TAG,
        one,
        items.map(function (item, index) {
          return element(ComboItem, { key: String(index), item: item, at: index });
        })
      );
    }
    if (tag === TEXTAREA_TAG) {
      one.defaultValue = text(seeded);
      return element(TEXTAREA_TAG, one);
    }
    one.type = inputType(spec);
    if (kind === CHECK_KIND || kind === RADIO_KIND) {
      one.defaultChecked = seeded === true;
      one[TICKED_ATTR] = text(seeded);
      // A shared name is what makes one group box hold one ticked radio.
      if (kind === RADIO_KIND) {
        one.name = text(spec[GROUP_KEY]);
      }
      return element(INPUT_TAG, one);
    }
    one.defaultValue = text(seeded);
    return element(INPUT_TAG, one);
  }

  // Beside `label`, a spec carries `text` for a tick box and `prefix` or
  // `suffix` for a number, and Qt draws all three.
  function sideWords(part, name, words) {
    var one = partProps(part);
    one.key = part;
    one[NAME_ATTR] = text(name);
    one[KEY_ATTR] = text(words);
    return element(SPAN_TAG, one, text(words));
  }

  function ControlRow(props) {
    var spec = specFor(props.name);
    var held = isPlainObject(spec) ? spec : {};
    var words = held[LABEL_KEY];
    var drawn = [];
    if (label(held[PREFIX]) !== undefined) {
      drawn.push(sideWords(VALUE_PREFIX_PART, props.name, held[PREFIX]));
    }
    drawn.push(element(Control, { key: CONTROL_PART, name: props.name }));
    if (label(held[SUFFIX]) !== undefined) {
      drawn.push(sideWords(VALUE_SUFFIX_PART, props.name, held[SUFFIX]));
    }
    if (label(held[TEXT_KEY]) !== undefined) {
      drawn.push(sideWords(CHECK_TEXT_PART, props.name, held[TEXT_KEY]));
    }
    if (label(words) !== undefined) {
      var labelProps = partProps(ROW_LABEL_PART);
      labelProps[NAME_ATTR] = text(props.name);
      labelProps[KEY_ATTR] = text(words);
      labelProps[ARIA_LABEL] = label(words);
      drawn.unshift(element(SPAN_TAG, labelProps, text(words)));
    }
    var rowProps = partProps(FORM_ROW_PART, {
      display: FLEX,
      flexDirection: ROW_DIRECTION
    });
    rowProps[NAME_ATTR] = text(props.name);
    return element(DIV_TAG, rowProps, drawn);
  }

  function TextRow(props) {
    var words = rowLabel(props.name);
    var drawn = [element(NamedText, { key: TEXT_PART, name: props.name })];
    if (words !== undefined) {
      var labelProps = partProps(ROW_LABEL_PART);
      labelProps[NAME_ATTR] = text(props.name);
      labelProps[KEY_ATTR] = words;
      drawn.unshift(element(SPAN_TAG, labelProps, words));
    }
    var rowProps = partProps(FORM_ROW_PART, {
      display: FLEX,
      flexDirection: ROW_DIRECTION
    });
    rowProps[NAME_ATTR] = text(props.name);
    return element(DIV_TAG, rowProps, drawn);
  }

  function TaRows() {
    var outer = partProps(TA_ROWS_PART, {
      display: FLEX,
      flexDirection: COLUMN_DIRECTION
    });
    outer[COUNT_ATTR] = text(taRows().length);
    return element(
      DIV_TAG,
      outer,
      taRows().map(function (row, index) {
        var rowProps = partProps(TA_ROW_PART, {
          display: FLEX,
          flexDirection: ROW_DIRECTION
        });
        var sliderName = at(row, THIRD);
        rowProps.key = String(index);
        // ControlRow and FormRow name a row by its control, and taRowNamed
        // matches this attribute, not the printed label at index ZERO.
        rowProps[NAME_ATTR] = text(sliderName);
        rowProps[INDEX_ATTR] = text(at(row, STEP));
        var labelProps = partProps(TA_LABEL_PART);
        labelProps[KEY_ATTR] = text(at(row, ZERO));
        var sliderProps = partProps(TA_SLIDER_PART);
        sliderProps.type = RANGE_TYPE;
        sliderProps.defaultValue = text(at(row, STEP));
        sliderProps[INDEX_ATTR] = text(at(row, STEP));
        // The host's change listener reports a node only once it carries both,
        // so these two are what carry a dragged weight back to the dialog.
        var sliderSpec = specFor(sliderName);
        var sliderRange = isPlainObject(sliderSpec) ? sliderSpec[RANGE] : undefined;
        sliderProps[NAME_ATTR] = text(sliderName);
        sliderProps[KIND_ATTR] = SLIDER_KIND;
        if (Array.isArray(sliderRange)) {
          sliderProps.min = text(at(sliderRange, ZERO));
          sliderProps.max = text(at(sliderRange, STEP));
        }
        var valueProps = partProps(TA_VALUE_PART);
        valueProps[KEY_ATTR] = text(at(row, ZERO));
        return element(
          DIV_TAG,
          rowProps,
          element(SPAN_TAG, labelProps, text(at(row, ZERO))),
          element(INPUT_TAG, sliderProps),
          element(SPAN_TAG, valueProps, text(at(row, SECOND)))
        );
      })
    );
  }

  function SoundRow() {
    var rowProps = partProps(SOUND_ROW_PART, {
      display: FLEX,
      flexDirection: ROW_DIRECTION
    });
    rowProps[COUNT_ATTR] = text(soundButtons().length);
    return element(
      DIV_TAG,
      rowProps,
      soundButtons().map(function (row, index) {
        var one = partProps(SOUND_BUTTON_PART);
        one.key = String(index);
        one[NAME_ATTR] = text(at(row, STEP));
        one[KEY_ATTR] = text(at(row, ZERO));
        if (label(at(row, SECOND)) !== undefined) {
          one[TITLE_ATTR] = text(at(row, SECOND));
        }
        return element(BUTTON_TAG, one, text(at(row, ZERO)));
      })
    );
  }

  function Group(props) {
    var title = props.title === ADD_GROUP_ROLE ? textNamed(ADD_GROUP_ROLE) : props.title;
    var margins = groupMargins(title);
    var groupProps = partProps(GROUP_PART, {
      display: FLEX,
      flexDirection: COLUMN_DIRECTION,
      paddingLeft: length(at(margins, ZERO)),
      paddingTop: length(at(margins, STEP)),
      paddingRight: length(at(margins, SECOND)),
      paddingBottom: length(at(margins, THIRD)),
      gap: length(groupSpacing(title))
    });
    groupProps[KEY_ATTR] = text(title);
    groupProps[SPACING_ATTR] = text(groupSpacing(title));
    groupProps[MARGINS_ATTR] = margins.length ? margins.join(PATH_SPLIT) : undefined;
    var titleProps = partProps(GROUP_TITLE_PART);
    titleProps[KEY_ATTR] = text(title);
    return element(
      DIV_TAG,
      groupProps,
      element(SPAN_TAG, titleProps, text(title)),
      element(Block, { node: props.node, tab: props.tab, part: GROUP_BODY_PART })
    );
  }

  function Item(props) {
    var node = props.node;
    var role = at(node, ZERO);
    if (role === STRETCH_ROLE) {
      return element(Stretch, null);
    }
    if (role === BANNER_ROLE) {
      return element(Banner, null);
    }
    if (role === LABEL_ROLE) {
      return element(PlainLabel, {
        words: at(node, STEP),
        sheet: sheetForHeading(at(node, STEP))
      });
    }
    if (role === BUTTON_ROLE) {
      return element(DialogButton, {
        words: at(node, STEP),
        name: nameForButton(at(node, STEP))
      });
    }
    if (role === TEXT_ROLE) {
      return element(TextRow, { name: at(node, STEP) });
    }
    if (role === ROW_ROLE) {
      return element(Block, { node: node, tab: props.tab, part: BLOCK_PART });
    }
    if (role === GROUP_ROLE) {
      return element(Group, {
        title: at(node, STEP),
        node: at(node, SECOND),
        tab: props.tab
      });
    }
    if (role === TA_ROWS_ROLE) {
      return element(TaRows, null);
    }
    if (role === SOUND_ROW_ROLE) {
      return element(SoundRow, null);
    }
    return element(ControlRow, { name: at(node, STEP) });
  }

  // A heading the surface styles carries its rule beside its words.
  function sheetForHeading(words) {
    if (words === headingNamed(SMS_GATEWAY)) {
      return headingNamed(SMS_GATEWAY_STYLE);
    }
    if (words === headingNamed(AI_INFO)) {
      return headingNamed(AI_INFO_STYLE);
    }
    return undefined;
  }

  function Block(props) {
    var node = props.node;
    var role = at(node, ZERO);
    if (role === SCROLL_ROLE) {
      var scrollProps = partProps(props.part, {
        overflowY: AUTO,
        overflowX: horizontalBarOff(props.tab) ? HIDDEN : AUTO
      });
      scrollProps[ROLE_ATTR] = text(role);
      scrollProps[TAB_ATTR] = text(props.tab);
      scrollProps[SCROLLS_ATTR] = String(true);
      scrollProps[BAR_ATTR] = String(!horizontalBarOff(props.tab));
      return element(
        DIV_TAG,
        scrollProps,
        element(Block, { node: at(node, STEP), tab: props.tab, part: BLOCK_PART })
      );
    }
    var blockProps = partProps(props.part, {
      display: FLEX,
      flexDirection: role === ROW_ROLE ? ROW_DIRECTION : COLUMN_DIRECTION,
      gap: length(contentSpacing(props.tab))
    });
    blockProps[ROLE_ATTR] = text(role);
    blockProps[SPACING_ATTR] = text(contentSpacing(props.tab));
    var items = Array.isArray(at(node, STEP)) ? at(node, STEP) : [];
    return element(
      DIV_TAG,
      blockProps,
      items.map(function (one, index) {
        return element(Item, { key: String(index), node: one, tab: props.tab });
      })
    );
  }

  function TabButton(props) {
    var one = partProps(TAB_BUTTON_PART);
    one[KEY_ATTR] = text(props.tab);
    one[INDEX_ATTR] = text(props.at);
    one[CURRENT_ATTR] = String(props.current);
    one[ARIA_LABEL] = label(props.tab);
    return element(BUTTON_TAG, one, text(props.tab));
  }

  // An inline `display` beats the browser's own rule for `hidden`, so the
  // page not on show takes `none` rather than relying on that attribute.
  function TabPage(props) {
    var node = layoutOf(props.tab);
    var one = partProps(TAB_PAGE_PART, {
      display: props.current === true ? FLEX : DISPLAY_NONE,
      flexDirection: COLUMN_DIRECTION
    });
    one[TAB_ATTR] = text(props.tab);
    one[KEY_ATTR] = text(props.tab);
    one[CURRENT_ATTR] = String(props.current);
    one[COUNT_ATTR] = text(groupTitlesOn(props.tab).length);
    one.hidden = !props.current;
    if (!Array.isArray(node)) {
      return element(DIV_TAG, one, null);
    }
    return element(
      DIV_TAG,
      one,
      element(Block, { node: node, tab: props.tab, part: BLOCK_PART })
    );
  }

  function Footer() {
    var one = partProps(FOOTER_PART, {
      display: FLEX,
      flexDirection: ROW_DIRECTION
    });
    return element(
      DIV_TAG,
      one,
      element(Stretch, { key: STRETCH_PART }),
      element(DialogButton, {
        key: CANCEL,
        words: buttonNamed(CANCEL),
        name: nameForButton(buttonNamed(CANCEL))
      }),
      element(DialogButton, {
        key: SAVE,
        words: buttonNamed(SAVE),
        name: nameForButton(buttonNamed(SAVE))
      })
    );
  }

  function DialogStep(props) {
    var one = partProps(STEP_PART);
    one[NAME_ATTR] = text(props.name);
    one[INDEX_ATTR] = text(props.at);
    return element(DIV_TAG, one, null);
  }

  // Dialog draws nothing for a payload that is not an object.
  function Dialog(props) {
    if (!isPlainObject(props.model)) {
      return null;
    }
    var found = props.model;
    var size = listField(found, MINIMUM_SIZE);
    var one = partProps(DIALOG_PART, {
      display: FLEX,
      flexDirection: COLUMN_DIRECTION,
      minWidth: length(at(size, ZERO)),
      minHeight: length(at(size, STEP))
    });
    one[KEY_ATTR] = text(found[WING]);
    one[COUNT_ATTR] = text(tabNames().length);
    one[ARIA_LABEL] = label(found[WINDOW_TITLE]);
    var titleProps = partProps(TITLE_PART);
    var barProps = partProps(TAB_BAR_PART, {
      display: FLEX,
      flexDirection: ROW_DIRECTION
    });
    barProps[COUNT_ATTR] = text(tabNames().length);
    var pagesProps = partProps(TAB_PAGES_PART, {
      display: FLEX,
      flexDirection: COLUMN_DIRECTION
    });
    pagesProps[CURRENT_ATTR] = text(props.tab);
    var drawn = [
      element(SPAN_TAG, titleProps, text(found[WINDOW_TITLE])),
      element(
        DIV_TAG,
        barProps,
        tabNames().map(function (tab, index) {
          return element(TabButton, {
            key: String(index),
            tab: tab,
            at: index,
            current: tab === props.tab
          });
        })
      ),
      element(
        DIV_TAG,
        pagesProps,
        tabNames().map(function (tab, index) {
          return element(TabPage, {
            key: String(index),
            tab: tab,
            current: tab === props.tab
          });
        })
      ),
      element(Footer, { key: FOOTER_PART })
    ];
    listField(found, CALLS).forEach(function (step, index) {
      drawn.push(
        element(DialogStep, {
          key: STEP_PART + String(index),
          name: at(step, ZERO),
          at: index
        })
      );
    });
    return element(DIV_TAG, one, drawn);
  }

  function heldFieldCount(found) {
    return DECLARED_FIELDS.filter(function (name) {
      return owns(found, name);
    }).length;
  }

  // Counts tabs, controls, rows and connections declared against those held.
  function report() {
    var found = held.model;
    return {
      declared: {
        fields: DECLARED_FIELDS.length,
        tabs: listField(found, TABS).length,
        controls: listField(found, CONTROL_SPECS).length,
        text_rows: listField(found, TEXT_ROWS).length,
        connections: objectField(found, CONNECTIONS)[RUN_TIME],
        steps: listField(found, CALL_NAMES).length
      },
      held: {
        fields: heldFieldCount(found),
        tabs: Object.keys(objectField(found, LAYOUT)).length,
        controls: Object.keys(objectField(found, VALUES)).length,
        text_rows: listField(found, ROWS).length,
        connections: listField(found, CONNECT_ORDER).length,
        steps: listField(found, CALLS).length
      },
      faults: dialogFaults.slice()
    };
  }

  function setDialog(found) {
    if (!isPlainObject(found)) {
      held = null;
      dialogFaults = [fault(null, null, NOT_AN_OBJECT_FAULT, kindOf(found))];
      return { declared: null, held: null, faults: dialogFaults.slice() };
    }
    held = { model: found };
    dialogFaults = [];
    checkFields(found);
    checkTabs(found);
    checkSpecs(found);
    checkRanges(found);
    checkRows(found);
    checkConnections(found);
    checkSteps(found);
    checkBanner(found);
    checkPaired(found);
    checkColours(found);
    checkBagOrder(found);
    checkDrawnMarkup(found);
    return report();
  }

  // Asks METHOD once, clearing asked so a refused first ask is retried.
  function loadDialog(params) {
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
        setDialog(found);
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
        value.forEach(function (one, index) {
          var inner = path + PATH_SPLIT + String(index);
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
        kind === NULL_KIND ||
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
    return dialogFaults.slice();
  }

  function loadError() {
    return loadFault;
  }

  function isLoaded() {
    return held !== null;
  }

  function busTopics() {
    var one = objectField(model(), BUS);
    return {
      subscribes: Array.isArray(one[SUBSCRIBES]) ? one[SUBSCRIBES].slice() : [],
      emits: Array.isArray(one[EMITS]) ? one[EMITS].slice() : []
    };
  }

  function runners(field_name) {
    var one = objectField(model(), field_name);
    return {
      built: Array.isArray(one[BUILT]) ? one[BUILT].slice() : [],
      started: Array.isArray(one[STARTED]) ? one[STARTED].slice() : []
    };
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

  function writeSeeded(node, kind, seeded) {
    if (kind === CHECK_KIND || kind === RADIO_KIND) {
      var ticked = seeded === true;
      if (node.checked !== ticked) {
        node.checked = ticked;
      }
      return;
    }
    if (kind === COMBO_TEXT_KIND || kind === COMBO_DATA_KIND) {
      var chosen = Number(seeded);
      if (isFiniteNumber(chosen) && node.selectedIndex !== chosen) {
        node.selectedIndex = chosen;
      }
      return;
    }
    var printed = seeded === undefined || seeded === null ? EMPTY : String(seeded);
    if (node.value !== printed) {
      node.value = printed;
    }
  }

  // A drawn control takes a seeded value once, so each draw writes the model
  // into every control but the focused one, which holds a half-typed value.
  function syncDrawn(target) {
    if (held === null || typeof target.querySelectorAll !== FUNCTION_KIND) {
      return;
    }
    var owner = target.ownerDocument;
    var typing = owner ? owner.activeElement : null;
    Array.prototype.slice
      .call(target.querySelectorAll(DRAWN_SELECT))
      .forEach(function (node) {
        var kind = node.getAttribute(KIND_ATTR);
        if (node === typing || kind === LIST_KIND) {
          return;
        }
        writeSeeded(node, kind, valueOf(node.getAttribute(NAME_ATTR)));
      });
  }

  // flushSync makes the document current before draw returns.
  function draw(target, node) {
    var root = rootFor(target);
    global.ReactDOM.flushSync(function () {
      root.render(node);
    });
    syncDrawn(target);
    return target;
  }

  // A payload given here is set first, so every drawn piece reads one model.
  function renderDialog(target, found, tab) {
    if (isPlainObject(found)) {
      setDialog(found);
    }
    var showing = tab === undefined || tab === null ? at(tabNames(), ZERO) : tab;
    return draw(
      target,
      element(Dialog, { model: held === null ? null : held.model, tab: showing })
    );
  }

  // The named empty space the renderer left for this window, or root itself.
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

  function fill(root, found, tab) {
    var space = spaceIn(root);
    return space === null ? null : renderDialog(space, found, tab);
  }

  function forget() {
    held = null;
    dialogFaults = [];
    loadFault = null;
    asked = null;
  }

  global.acervatorSetSettingsDialog = setDialog;
  global.acervatorLoadSettingsDialog = loadDialog;
  global.acervatorSettingsDialog = {
    method: METHOD,
    spacePart: PAGE_PART,
    Dialog: Dialog,
    TabPage: TabPage,
    Banner: Banner,
    Control: Control,
    Footer: Footer,
    payload: payload,
    declaredNames: declaredNames,
    field: field,
    bag: bag,
    list: list,
    bagKeys: bagKeys,
    tabNames: tabNames,
    scrollingTabs: scrollingTabs,
    layoutOf: layoutOf,
    groupTitlesOn: groupTitlesOn,
    paintedOn: paintedOn,
    specNames: specNames,
    specFor: specFor,
    valueOf: valueOf,
    enabledOf: enabledOf,
    visibleOf: visibleOf,
    tooltipOf: tooltipOf,
    textNamed: textNamed,
    styleNamed: styleNamed,
    buttonNamed: buttonNamed,
    buttonNames: buttonNames,
    nameForButton: nameForButton,
    headingNamed: headingNamed,
    rowNames: rowNames,
    rowFor: rowFor,
    rowLabel: rowLabel,
    textRowNames: textRowNames,
    taRows: taRows,
    taRowNamed: taRowNamed,
    soundButtons: soundButtons,
    soundButtonNamed: soundButtonNamed,
    exchangeItems: exchangeItems,
    exchangeItemNamed: exchangeItemNamed,
    comboItems: comboItems,
    connectOrder: connectOrder,
    connectSignals: connectSignals,
    handlerFor: handlerFor,
    handlersOn: handlersOn,
    calls: calls,
    callNames: callNames,
    banner: banner,
    bannerMarks: bannerMarks,
    bannerPieces: bannerPieces,
    rebuiltBanner: rebuiltBanner,
    bannerColour: bannerColour,
    bannerStyle: bannerStyle,
    contentSpacing: contentSpacing,
    groupSpacing: groupSpacing,
    groupMargins: groupMargins,
    horizontalBarOff: horizontalBarOff,
    busTopics: busTopics,
    runners: runners,
    coloursIn: coloursIn,
    wholeSheet: wholeSheet,
    paintedStyle: paintedStyle,
    isSwappedAlpha: isSwappedAlpha,
    isReorderedKey: isReorderedKey,
    kinds: kinds,
    notPlainData: notPlainData,
    faults: faults,
    loadError: loadError,
    isLoaded: isLoaded,
    renderDialog: renderDialog,
    spaceIn: spaceIn,
    fill: fill,
    forget: forget
  };
})(window);
