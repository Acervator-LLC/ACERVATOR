// Draws the pre-flight symbol check box from the preflight_check.state payload.
(function (global) {
  "use strict";

  var METHOD = "preflight_check.state";

  var METHOD_FIELD = "method";
  var BOXES = "boxes";
  var BOX_WIDGETS = "box_widgets";
  var FAILURE_WIDGET = "failure_widget";
  var WARNING_WIDGET = "warning_widget";
  var LAYOUT = "layout";
  var BUTTONS = "buttons";
  var BUTTON_NAMES = "button_names";
  var FAILURE_BUTTONS = "failure_buttons";
  var WARNING_BUTTONS = "warning_buttons";
  var ACTIONS = "actions";
  var OUTCOMES = "outcomes";
  var CREATES_BOT = "creates_bot";
  var OUTCOME_LEVELS = "outcome_levels";
  var DEFAULT_OUTCOME = "default_outcome";
  var CLOSED_OUTCOME = "closed_outcome";
  var BOX_CLOSED_OUTCOMES = "box_closed_outcomes";
  var BUTTON_OUTCOMES = "button_outcomes";
  var ANSWERS = "answers";
  var BUTTON_ANSWERS = "button_answers";
  var DEFAULT_ANSWER = "default_answer";
  var CLOSED_ANSWER = "closed_answer";
  var TIMERS = "timers";
  var TIMER_DELAYS_MS = "timer_delays_ms";
  var REQUEST_TIMEOUT_MS = "request_timeout_ms";
  var SKIN = "skin";
  var RESULT = "result";
  var RESULT_FIELDS = "result_fields";
  var WARNING_COUNT = "warning_count";
  var REPORT = "report";
  var REPORT_LINES = "report_lines";
  var BOX = "box";
  var BOX_TITLE = "box_title";
  var BOX_BODY = "box_body";
  var BOX_BODY_LINES = "box_body_lines";
  var BOX_BUTTONS = "box_buttons";
  var STATUS_LINE = "status_line";
  var STATUS_LEVEL = "status_level";
  var ANSWERED = "answered";
  var OUTCOME = "outcome";
  var CHECKED = "checked";
  var CALL_NAMES = "call_names";
  var CALLS = "calls";

  // Every top-level name the preflight_check.state payload carries.
  var DECLARED_FIELDS = [
    METHOD_FIELD,
    BOXES,
    BOX_WIDGETS,
    FAILURE_WIDGET,
    WARNING_WIDGET,
    LAYOUT,
    BUTTONS,
    BUTTON_NAMES,
    FAILURE_BUTTONS,
    WARNING_BUTTONS,
    ACTIONS,
    OUTCOMES,
    CREATES_BOT,
    OUTCOME_LEVELS,
    DEFAULT_OUTCOME,
    CLOSED_OUTCOME,
    BOX_CLOSED_OUTCOMES,
    BUTTON_OUTCOMES,
    ANSWERS,
    BUTTON_ANSWERS,
    DEFAULT_ANSWER,
    CLOSED_ANSWER,
    TIMERS,
    TIMER_DELAYS_MS,
    REQUEST_TIMEOUT_MS,
    SKIN,
    RESULT,
    RESULT_FIELDS,
    WARNING_COUNT,
    REPORT,
    REPORT_LINES,
    BOX,
    BOX_TITLE,
    BOX_BODY,
    BOX_BODY_LINES,
    BOX_BUTTONS,
    STATUS_LINE,
    STATUS_LEVEL,
    ANSWERED,
    OUTCOME,
    CHECKED,
    CALL_NAMES,
    CALLS
  ];

  var DECLARED_BAGS = [
    BOX_WIDGETS,
    FAILURE_WIDGET,
    WARNING_WIDGET,
    LAYOUT,
    BUTTONS,
    ACTIONS,
    CREATES_BOT,
    OUTCOME_LEVELS,
    BOX_CLOSED_OUTCOMES,
    BUTTON_OUTCOMES,
    BUTTON_ANSWERS,
    TIMERS,
    SKIN,
    RESULT
  ];

  var DECLARED_LISTS = [
    BOXES,
    BUTTON_NAMES,
    FAILURE_BUTTONS,
    WARNING_BUTTONS,
    OUTCOMES,
    ANSWERS,
    TIMER_DELAYS_MS,
    RESULT_FIELDS,
    REPORT_LINES,
    BOX_BODY_LINES,
    BOX_BUTTONS,
    CALL_NAMES,
    CALLS
  ];

  // Every bag whose written order the payload also publishes as a list.
  var ORDERED_BAGS = [
    { bag: BUTTONS, order: BUTTON_NAMES },
    { bag: BUTTON_OUTCOMES, order: BUTTON_NAMES },
    { bag: BUTTON_ANSWERS, order: BUTTON_NAMES },
    { bag: CREATES_BOT, order: OUTCOMES },
    { bag: OUTCOME_LEVELS, order: OUTCOMES },
    { bag: BOX_CLOSED_OUTCOMES, order: BOXES },
    { bag: BOX_WIDGETS, order: BOXES }
  ];

  var ACCESSIBLE_NAME = "accessible_name";
  var WINDOW_TITLE = "window_title";
  var MODAL = "modal";
  var SIZE_PX = "size_px";
  var STYLE_SHEET = "style_sheet";
  var STAYS_ON_TOP = "stays_on_top";
  var ICON = "icon";
  var ICON_VALUE = "icon_value";
  var TEXT_FORMAT = "text_format";
  var TEXT_FORMAT_VALUE = "text_format_value";
  var BUTTONS_VALUE = "buttons_value";
  var DEFAULT_BUTTON_VALUE = "default_button_value";

  // Every key one box widget carries, in the order the payload writes them.
  var WIDGET_KEYS = [
    ACCESSIBLE_NAME,
    WINDOW_TITLE,
    MODAL,
    SIZE_PX,
    STYLE_SHEET,
    STAYS_ON_TOP,
    ICON,
    ICON_VALUE,
    TEXT_FORMAT,
    TEXT_FORMAT_VALUE,
    BUTTONS_VALUE,
    DEFAULT_BUTTON_VALUE
  ];

  var MARGINS_PX = "margins_px";
  var SPACING_PX = "spacing_px";
  var ORDER = "order";
  var CHILD_STRETCH = "child_stretch";
  var CHILD_OBJECT_NAMES = "child_object_names";

  var ICON_CHILD = "icon";
  var SPACER_CHILD = "spacer";
  var TEXT_CHILD = "text";
  var BUTTON_BOX_CHILD = "button_box";

  var TEXT_KEY = "text";
  var ENABLED_KEY = "enabled";
  var VALUE_KEY = "value";
  var ANSWER_KEY = "answer";
  var OUTCOME_KEY = "outcome";

  // Every key one button carries, so a button lost one is reported.
  var BUTTON_KEYS = [TEXT_KEY, ENABLED_KEY, VALUE_KEY, ANSWER_KEY, OUTCOME_KEY];

  var SUCCESS = "success";
  var MESSAGE = "message";
  var MARKET_ACTIVE = "market_active";
  var ACTIVE_REPORTED = "active_reported";
  var LAST_PRICE = "last_price";
  var PRICE_READ = "price_read";
  var WARNINGS = "warnings";

  var MISSING_FAULT = "missing";
  var NOT_AN_OBJECT_FAULT = "not-an-object";
  var NOT_A_BAG_FAULT = "not-a-bag";
  var NOT_A_LIST_FAULT = "not-a-list";
  var SHORT_LIST_FAULT = "short-list";
  var DISAGREES_FAULT = "disagrees";
  var DUPLICATE_NAME_FAULT = "duplicate-name";
  var UNKNOWN_NAME_FAULT = "unknown-name";
  var UNKNOWN_STEP_FAULT = "unknown-step";
  var REORDERED_KEY_FAULT = "reordered-key";
  var SWAPPED_ALPHA_FAULT = "swapped-alpha";
  var NOT_CSS_FAULT = "not-css";
  var MARKUP_FAULT = "markup";
  var UNCHECKED_CLAIM_FAULT = "unchecked-claim";

  var ROW_AT = "row:";
  var PATH_SPLIT = ".";
  var EMPTY = "";

  var NO_BRIDGE = "the preload bridge is not present";

  // Qt paints this gradient by name and no browser stylesheet runs it.
  var QT_ONLY = "qlineargradient";

  // MARKUP_OPEN starts a tag a Qt rich-text box reads as formatting.
  var MARKUP_OPEN = "<";

  var SCREEN_CLASS = "acervator-preflight-check";

  var DIV_TAG = "div";
  var SPAN_TAG = "span";
  var BUTTON_TAG = "button";
  var BUTTON_TYPE = "button";

  var SCREEN_PART = "preflight-check";
  var BOX_PART = "preflight-box";
  var TITLE_PART = "box-title";
  var ICON_PART = "box-icon";
  var SPACER_PART = "box-spacer";
  var BODY_PART = "box-body";
  var BODY_LINE_PART = "body-line";
  var BUTTON_BOX_PART = "box-button-box";
  var BUTTON_PART = "box-button";
  var STATUS_PART = "status-line";
  var OUTCOME_PART = "outcome-mark";
  var RESULT_PART = "result-field";
  var WARNING_PART = "warning-line";
  var STEP_PART = "check-step";

  // PAGE_PART is the space the bot wizard leaves for this screen.
  var PAGE_PART = "preflight-check-page";

  var PART_ATTR = "data-part";
  var KEY_ATTR = "data-key";
  var NAME_ATTR = "data-name";
  var INDEX_ATTR = "data-index";
  var COUNT_ATTR = "data-count";
  var SHOWN_ATTR = "data-shown";
  var VALUE_ATTR = "data-value";
  var LEVEL_ATTR = "data-level";
  var ANSWER_ATTR = "data-answer";
  var OUTCOME_ATTR = "data-outcome";
  var CHECKED_ATTR = "data-checked";
  var CREATES_ATTR = "data-creates-bot";
  var DEFAULT_ATTR = "data-default";
  var MODAL_ATTR = "data-modal";
  var TOP_ATTR = "data-stays-on-top";
  var ICON_ATTR = "data-icon";
  var FORMAT_ATTR = "data-text-format";
  var STRETCH_ATTR = "data-stretch";
  var OBJECT_ATTR = "data-object-name";
  var ARIA_LABEL = "aria-label";
  var ARIA_DISABLED = "aria-disabled";

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
  var SPACE = " ";
  var FLEX = "flex";
  var ROW_DIRECTION = "row";
  var COLUMN_DIRECTION = "column";
  var PRE_WRAP = "pre-wrap";
  var NOWRAP = "nowrap";
  var WRAP = "wrap";
  var AUTO = "auto";
  var FLEX_END = "flex-end";
  var CENTER = "center";
  var STRING_KIND = "string";
  var NUMBER_KIND = "number";
  var BOOLEAN_KIND = "boolean";
  var FUNCTION_KIND = "function";
  var NULL_KIND = "null";

  var ZERO = Number(EMPTY);
  var STEP = Number(true);

  var LEFT = ZERO;
  var TOP = LEFT + STEP;
  var RIGHT = TOP + STEP;
  var BOTTOM = RIGHT + STEP;
  var MARGIN_COUNT = BOTTOM + STEP;

  var held = null;
  var screenFaults = [];
  var loadFault = null;
  var asked = null;
  var pressed = [];
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
    screenFaults.push(fault(where, field, kind, detail));
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

  function boxName() {
    var found = model();
    return isPlainObject(found) ? text(found[BOX]) : undefined;
  }

  // The widget the open box reads, found by that box's own name.
  function widgetOf(name) {
    var found = model();
    var field = objectField(found, BOX_WIDGETS)[name];
    return typeof field === STRING_KIND ? objectField(found, field) : {};
  }

  function openWidget() {
    return widgetOf(boxName());
  }

  function boxNames() {
    return listField(model(), BOXES).slice();
  }

  function layout() {
    return objectField(model(), LAYOUT);
  }

  function layoutOrder() {
    return listField(layout(), ORDER).slice();
  }

  function layoutStretch(at) {
    return listField(layout(), CHILD_STRETCH)[at];
  }

  // The Qt object name one layout child carries, undefined for the spacer.
  function layoutObjectName(name) {
    var named = objectField(layout(), CHILD_OBJECT_NAMES);
    return owns(named, name) ? named[name] : undefined;
  }

  function buttonNames() {
    return listField(model(), BUTTON_NAMES).slice();
  }

  function buttonNamed(name) {
    var bag = objectField(model(), BUTTONS);
    return owns(bag, name) ? bag[name] : undefined;
  }

  function boxButtons() {
    return listField(model(), BOX_BUTTONS).slice();
  }

  function bodyLines() {
    return listField(model(), BOX_BODY_LINES).slice();
  }

  function reportLines() {
    return listField(model(), REPORT_LINES).slice();
  }

  function result() {
    return objectField(model(), RESULT);
  }

  function resultNames() {
    return listField(model(), RESULT_FIELDS).slice();
  }

  function resultField(name) {
    var found = result();
    return owns(found, name) ? found[name] : undefined;
  }

  function warnings() {
    var found = result();
    return Array.isArray(found[WARNINGS]) ? found[WARNINGS].slice() : [];
  }

  function outcomeNames() {
    return listField(model(), OUTCOMES).slice();
  }

  function outcome() {
    var found = model();
    return isPlainObject(found) ? text(found[OUTCOME]) : undefined;
  }

  function outcomeLevel(name) {
    var bag = objectField(model(), OUTCOME_LEVELS);
    return owns(bag, name) ? bag[name] : undefined;
  }

  function createsBot(name) {
    var bag = objectField(model(), CREATES_BOT);
    return owns(bag, name) ? bag[name] : undefined;
  }

  function actionFor(name) {
    var bag = objectField(model(), ACTIONS);
    return owns(bag, name) ? bag[name] : undefined;
  }

  function checkRan() {
    var found = model();
    return isPlainObject(found) && found[CHECKED] === true;
  }

  function calls() {
    return listField(model(), CALLS).slice();
  }

  function callNames() {
    return listField(model(), CALL_NAMES).slice();
  }

  // The names of the steps the run took, each step's own first word.
  function stepNames() {
    return calls().map(function (one) {
      return text(Array.isArray(one) && one.length ? one[ZERO] : undefined);
    });
  }

  function stepNamed(name) {
    var found;
    calls().forEach(function (one) {
      if (Array.isArray(one) && one.length && String(one[ZERO]) === String(name)) {
        found = one;
      }
    });
    return found;
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
      var step = Array.isArray(one) && one.length ? one[ZERO] : one;
      if (named.indexOf(step) < ZERO) {
        note(ROW_AT + String(at), CALLS, UNKNOWN_STEP_FAULT, step);
      }
    });
  }

  // Counts both lists before pairing them, so neither is read past its end.
  function checkPairedList(where, field, drawn, paired, name) {
    if (paired.length !== drawn.length) {
      note(where, field, SHORT_LIST_FAULT, name + PATH_SPLIT + String(paired.length));
    }
  }

  function checkNamedList(field, drawn, allowed) {
    var seen = {};
    drawn.forEach(function (name, at) {
      if (allowed.indexOf(name) < ZERO) {
        note(ROW_AT + String(at), field, UNKNOWN_NAME_FAULT, name);
      }
      if (owns(seen, String(name))) {
        note(ROW_AT + String(at), field, DUPLICATE_NAME_FAULT, name);
      }
      seen[String(name)] = true;
    });
  }

  // Every bag is paired against its published order, by name and never by place.
  function checkOrderedBags(found) {
    ORDERED_BAGS.forEach(function (one) {
      var bag = objectField(found, one.bag);
      var order = listField(found, one.order);
      var keys = Object.keys(bag);
      if (keys.length !== order.length) {
        note(null, one.bag, SHORT_LIST_FAULT, one.order + PATH_SPLIT + keys.length);
        return;
      }
      order.forEach(function (name, at) {
        if (!owns(bag, name)) {
          note(ROW_AT + String(at), one.bag, MISSING_FAULT, name);
        }
      });
    });
  }

  function checkButtons(found) {
    var bag = objectField(found, BUTTONS);
    listField(found, BUTTON_NAMES).forEach(function (name) {
      if (!isPlainObject(bag[name])) {
        note(null, BUTTONS, NOT_A_BAG_FAULT, name);
        return;
      }
      BUTTON_KEYS.forEach(function (key) {
        if (!owns(bag[name], key)) {
          note(name, BUTTONS, MISSING_FAULT, key);
        }
      });
    });
    checkNamedList(BOX_BUTTONS, listField(found, BOX_BUTTONS), listField(found, BUTTON_NAMES));
    checkNamedList(
      FAILURE_BUTTONS,
      listField(found, FAILURE_BUTTONS),
      listField(found, BUTTON_NAMES)
    );
    checkNamedList(
      WARNING_BUTTONS,
      listField(found, WARNING_BUTTONS),
      listField(found, BUTTON_NAMES)
    );
  }

  function checkOutcomes(found) {
    var named = listField(found, OUTCOMES);
    [DEFAULT_OUTCOME, CLOSED_OUTCOME, OUTCOME].forEach(function (field) {
      if (owns(found, field) && named.indexOf(found[field]) < ZERO) {
        note(null, field, UNKNOWN_NAME_FAULT, found[field]);
      }
    });
    var closed = objectField(found, BOX_CLOSED_OUTCOMES);
    Object.keys(closed).forEach(function (name) {
      if (named.indexOf(closed[name]) < ZERO) {
        note(name, BOX_CLOSED_OUTCOMES, UNKNOWN_NAME_FAULT, closed[name]);
      }
    });
    var reached = objectField(found, BUTTON_OUTCOMES);
    Object.keys(reached).forEach(function (name) {
      if (named.indexOf(reached[name]) < ZERO) {
        note(name, BUTTON_OUTCOMES, UNKNOWN_NAME_FAULT, reached[name]);
      }
    });
    checkNamedList(BOXES, listField(found, BOXES), listField(found, BOXES));
    checkOpenBox(found);
  }

  // An open box the payload never listed would draw from an empty widget.
  function checkOpenBox(found) {
    var open = found[BOX];
    var opened = open === undefined || open === null ? EMPTY : String(open);
    if (opened.length && listField(found, BOXES).indexOf(opened) < ZERO) {
      note(null, BOX, UNKNOWN_NAME_FAULT, opened);
    }
  }

  function checkResult(found) {
    var carried = objectField(found, RESULT);
    var named = listField(found, RESULT_FIELDS);
    var keys = Object.keys(carried);
    if (keys.length && keys.length !== named.length) {
      note(null, RESULT, SHORT_LIST_FAULT, RESULT_FIELDS + PATH_SPLIT + keys.length);
    }
    if (keys.length) {
      named.forEach(function (name) {
        if (!owns(carried, name)) {
          note(null, RESULT, MISSING_FAULT, name);
        }
      });
    }
    var listed = Array.isArray(carried[WARNINGS]) ? carried[WARNINGS] : [];
    if (owns(found, WARNING_COUNT) && found[WARNING_COUNT] !== listed.length) {
      note(null, WARNING_COUNT, DISAGREES_FAULT, found[WARNING_COUNT]);
    }
  }

  // The lines and the block they build must be the same words.
  function checkReport(found) {
    [
      { lines: REPORT_LINES, whole: REPORT },
      { lines: BOX_BODY_LINES, whole: BOX_BODY }
    ].forEach(function (one) {
      var drawn = listField(found, one.lines);
      var block = found[one.whole];
      if (typeof block !== STRING_KIND) {
        return;
      }
      var rebuilt = drawn.join(lineBreak());
      if (block.length && rebuilt !== block) {
        note(null, one.lines, DISAGREES_FAULT, one.whole);
      }
      if (!block.length && drawn.length) {
        note(null, one.lines, SHORT_LIST_FAULT, one.whole);
      }
    });
  }

  // A pass drawn where no check ran is the claim this screen must never make.
  function checkClaims(found) {
    var ran = found[CHECKED] === true;
    var carried = objectField(found, RESULT);
    if (ran) {
      return;
    }
    if (Object.keys(carried).length) {
      note(null, RESULT, UNCHECKED_CLAIM_FAULT, CHECKED);
    }
    if (typeof found[REPORT] === STRING_KIND && found[REPORT].length) {
      note(null, REPORT, UNCHECKED_CLAIM_FAULT, CHECKED);
    }
    if (typeof found[BOX] === STRING_KIND && found[BOX].length) {
      note(null, BOX, UNCHECKED_CLAIM_FAULT, CHECKED);
    }
  }

  function checkColour(where, field, value) {
    if (isSwappedAlpha(value)) {
      note(where, field, SWAPPED_ALPHA_FAULT, value);
    }
  }

  // Every sheet the payload carries, the skin bag's own entries among them.
  function sheetsOf(found) {
    var sheets = [];
    listField(found, BOXES).forEach(function (name) {
      var field = objectField(found, BOX_WIDGETS)[name];
      if (typeof field === STRING_KIND) {
        sheets.push({ where: name, field: field, sheet: objectField(found, field)[STYLE_SHEET] });
      }
    });
    Object.keys(objectField(found, SKIN)).forEach(function (name) {
      sheets.push({ where: name, field: SKIN, sheet: objectField(found, SKIN)[name] });
    });
    return sheets;
  }

  function checkColours(found) {
    sheetsOf(found).forEach(function (one) {
      checkColour(one.where, one.field, one.sheet);
      wholeSheet(one.sheet).forEach(function (written) {
        checkColour(one.where, one.field, written.value);
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

  // Every word drawn as characters swept for the tags a Qt box would read.
  function checkDrawnMarkup(found) {
    [BOX_BODY_LINES, REPORT_LINES].forEach(function (field) {
      listField(found, field).forEach(function (line, at) {
        checkMarkup(ROW_AT + String(at), field, line);
      });
    });
    [BOX_TITLE, STATUS_LINE].forEach(function (field) {
      checkMarkup(null, field, found[field]);
    });
    var bag = objectField(found, BUTTONS);
    Object.keys(bag).forEach(function (name) {
      checkMarkup(name, BUTTONS, objectField(bag, name)[TEXT_KEY]);
    });
  }

  function checkLayout(found) {
    var box = objectField(found, LAYOUT);
    var order = listField(box, ORDER);
    checkPairedList(null, LAYOUT, order, listField(box, CHILD_STRETCH), CHILD_STRETCH);
    var seen = {};
    order.forEach(function (name, at) {
      if (owns(seen, String(name))) {
        note(ROW_AT + String(at), ORDER, DUPLICATE_NAME_FAULT, name);
      }
      seen[String(name)] = true;
    });
    Object.keys(objectField(box, CHILD_OBJECT_NAMES)).forEach(function (name) {
      if (order.indexOf(name) < ZERO) {
        note(name, CHILD_OBJECT_NAMES, UNKNOWN_NAME_FAULT, name);
      }
    });
  }

  function checkWidgets(found) {
    listField(found, BOXES).forEach(function (name) {
      var field = objectField(found, BOX_WIDGETS)[name];
      if (typeof field !== STRING_KIND) {
        note(name, BOX_WIDGETS, MISSING_FAULT, name);
        return;
      }
      var widget = objectField(found, field);
      WIDGET_KEYS.forEach(function (key) {
        if (!owns(widget, key)) {
          note(name, field, MISSING_FAULT, key);
        }
      });
    });
  }

  function element() {
    return global.React.createElement.apply(null, arguments);
  }

  // The line break the report block is split on, written as a percent escape.
  function lineBreak() {
    return decodeURIComponent("%0A");
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

  // Qt writes its margins left first and CSS padding writes them top first.
  function marginOf(box) {
    var written = listField(box, MARGINS_PX);
    if (written.length !== MARGIN_COUNT) {
      return undefined;
    }
    return [written[TOP], written[RIGHT], written[BOTTOM], written[LEFT]]
      .map(function (one) {
        return String(length(one));
      })
      .join(SPACE);
  }

  function BodyLine(props) {
    var lineProps = { className: SCREEN_CLASS, style: { whiteSpace: PRE_WRAP } };
    lineProps[PART_ATTR] = BODY_LINE_PART;
    lineProps[INDEX_ATTR] = text(props.at);
    return element(DIV_TAG, lineProps, text(props.words));
  }

  function BoxIcon(props) {
    var iconProps = { className: SCREEN_CLASS };
    iconProps[PART_ATTR] = ICON_PART;
    iconProps[NAME_ATTR] = text(props.widget[ICON]);
    iconProps[VALUE_ATTR] = text(props.widget[ICON_VALUE]);
    iconProps[OBJECT_ATTR] = text(layoutObjectName(props.child));
    iconProps[STRETCH_ATTR] = text(props.stretch);
    return element(SPAN_TAG, iconProps, null);
  }

  function BoxSpacer(props) {
    var spacerProps = { className: SCREEN_CLASS, style: { flex: AUTO } };
    spacerProps[PART_ATTR] = SPACER_PART;
    spacerProps[OBJECT_ATTR] = text(layoutObjectName(props.child));
    spacerProps[STRETCH_ATTR] = text(props.stretch);
    return element(SPAN_TAG, spacerProps, null);
  }

  // The body draws one element per published line, so no line loses its place.
  function BoxBody(props) {
    var bodyProps = {
      className: SCREEN_CLASS,
      style: { display: FLEX, flexDirection: COLUMN_DIRECTION, whiteSpace: PRE_WRAP }
    };
    bodyProps[PART_ATTR] = BODY_PART;
    bodyProps[COUNT_ATTR] = text(bodyLines().length);
    bodyProps[OBJECT_ATTR] = text(layoutObjectName(props.child));
    bodyProps[STRETCH_ATTR] = text(props.stretch);
    bodyProps[FORMAT_ATTR] = text(props.widget[TEXT_FORMAT]);
    bodyProps[VALUE_ATTR] = text(props.widget[TEXT_FORMAT_VALUE]);
    return element(
      DIV_TAG,
      bodyProps,
      bodyLines().map(function (line, at) {
        return element(BodyLine, { key: String(at), words: line, at: at });
      })
    );
  }

  function BoxButton(props) {
    var one = isPlainObject(props.button) ? props.button : {};
    var buttonProps = {
      className: SCREEN_CLASS,
      type: BUTTON_TYPE,
      disabled: one[ENABLED_KEY] === false,
      style: { whiteSpace: NOWRAP },
      onClick: function () {
        press(props.name);
      }
    };
    buttonProps[PART_ATTR] = BUTTON_PART;
    buttonProps[KEY_ATTR] = text(props.name);
    buttonProps[INDEX_ATTR] = text(props.at);
    buttonProps[VALUE_ATTR] = text(one[VALUE_KEY]);
    buttonProps[ANSWER_ATTR] = text(one[ANSWER_KEY]);
    buttonProps[OUTCOME_ATTR] = text(one[OUTCOME_KEY]);
    buttonProps[NAME_ATTR] = text(actionFor(props.action));
    buttonProps[DEFAULT_ATTR] = String(one[VALUE_KEY] === props.fallback);
    buttonProps[ARIA_LABEL] = label(text(one[TEXT_KEY]));
    buttonProps[ARIA_DISABLED] = text(one[ENABLED_KEY] === false);
    return element(BUTTON_TAG, buttonProps, text(one[TEXT_KEY]));
  }

  // The button row draws the buttons the open box carries, in its own order.
  function ButtonBox(props) {
    var rowProps = {
      className: SCREEN_CLASS,
      style: { display: FLEX, flexDirection: ROW_DIRECTION, justifyContent: FLEX_END }
    };
    rowProps[PART_ATTR] = BUTTON_BOX_PART;
    rowProps[COUNT_ATTR] = text(boxButtons().length);
    rowProps[OBJECT_ATTR] = text(layoutObjectName(props.child));
    rowProps[STRETCH_ATTR] = text(props.stretch);
    rowProps[VALUE_ATTR] = text(props.widget[BUTTONS_VALUE]);
    rowProps[DEFAULT_ATTR] = text(props.widget[DEFAULT_BUTTON_VALUE]);
    return element(
      DIV_TAG,
      rowProps,
      boxButtons().map(function (name, at) {
        return element(BoxButton, {
          key: String(name),
          name: name,
          at: at,
          action: actionNameFor(name),
          button: buttonNamed(name),
          fallback: props.widget[DEFAULT_BUTTON_VALUE]
        });
      })
    );
  }

  // The action a button press runs, named the way the payload writes it.
  function actionNameFor(name) {
    var found;
    Object.keys(objectField(model(), ACTIONS)).forEach(function (key) {
      if (key.split(PATH_SPLIT).shift() === String(name)) {
        found = key;
      }
    });
    return found;
  }

  var CHILD_PARTS = {};

  function childFor(name, at, widget) {
    var made = CHILD_PARTS[name];
    var props = { key: name, child: name, stretch: layoutStretch(at), widget: widget };
    return made === undefined ? null : element(made, props);
  }

  function PreflightBox(props) {
    var widget = props.widget;
    var boxProps = {
      className: SCREEN_CLASS,
      style: {
        display: FLEX,
        flexDirection: ROW_DIRECTION,
        alignItems: CENTER,
        flexWrap: WRAP,
        gap: length(layout()[SPACING_PX]),
        padding: marginOf(layout()),
        width: length(listField(widget, SIZE_PX)[ZERO]),
        minHeight: length(listField(widget, SIZE_PX)[STEP])
      }
    };
    boxProps[PART_ATTR] = BOX_PART;
    boxProps[KEY_ATTR] = text(props.name);
    boxProps[MODAL_ATTR] = text(widget[MODAL]);
    boxProps[TOP_ATTR] = text(widget[STAYS_ON_TOP]);
    boxProps[ICON_ATTR] = text(widget[ICON]);
    boxProps[ARIA_LABEL] = label(text(widget[ACCESSIBLE_NAME]));
    var titleProps = { className: SCREEN_CLASS, style: { whiteSpace: NOWRAP } };
    titleProps[PART_ATTR] = TITLE_PART;
    titleProps[KEY_ATTR] = text(props.name);
    var drawn = [element(SPAN_TAG, titleProps, text(props.title))];
    layoutOrder().forEach(function (name, at) {
      var made = childFor(name, at, widget);
      if (made !== null) {
        drawn.push(made);
      }
    });
    return element(DIV_TAG, boxProps, drawn);
  }

  function StatusLine(props) {
    var lineProps = {
      className: SCREEN_CLASS,
      style: { whiteSpace: PRE_WRAP },
      hidden: props.words === EMPTY
    };
    lineProps[PART_ATTR] = STATUS_PART;
    lineProps[LEVEL_ATTR] = text(props.level);
    lineProps[SHOWN_ATTR] = String(props.words !== EMPTY);
    return element(DIV_TAG, lineProps, text(props.words));
  }

  function OutcomeMark(props) {
    var markProps = { className: SCREEN_CLASS };
    markProps[PART_ATTR] = OUTCOME_PART;
    markProps[OUTCOME_ATTR] = text(props.outcome);
    markProps[LEVEL_ATTR] = text(outcomeLevel(props.outcome));
    markProps[CREATES_ATTR] = text(createsBot(props.outcome));
    markProps[ANSWER_ATTR] = text(props.answered);
    markProps[CHECKED_ATTR] = text(props.checked);
    return element(DIV_TAG, markProps, null);
  }

  function ResultField(props) {
    var fieldProps = { className: SCREEN_CLASS };
    fieldProps[PART_ATTR] = RESULT_PART;
    fieldProps[KEY_ATTR] = text(props.name);
    fieldProps[INDEX_ATTR] = text(props.at);
    fieldProps[VALUE_ATTR] = text(props.value);
    fieldProps[SHOWN_ATTR] = String(props.value !== undefined);
    return element(DIV_TAG, fieldProps, null);
  }

  function WarningLine(props) {
    var warningProps = { className: SCREEN_CLASS, style: { whiteSpace: PRE_WRAP } };
    warningProps[PART_ATTR] = WARNING_PART;
    warningProps[INDEX_ATTR] = text(props.at);
    return element(DIV_TAG, warningProps, text(props.words));
  }

  function CheckStep(props) {
    var stepProps = { className: SCREEN_CLASS };
    stepProps[PART_ATTR] = STEP_PART;
    stepProps[NAME_ATTR] = text(props.name);
    stepProps[INDEX_ATTR] = text(props.at);
    return element(DIV_TAG, stepProps, null);
  }

  // Screen draws nothing for a payload that is not an object.
  function Screen(props) {
    if (!isPlainObject(props.model)) {
      return null;
    }
    var found = props.model;
    var open = text(found[BOX]);
    var screenProps = {
      className: SCREEN_CLASS,
      id: props.id,
      style: { display: FLEX, flexDirection: COLUMN_DIRECTION, minWidth: ZERO }
    };
    screenProps[PART_ATTR] = SCREEN_PART;
    screenProps[KEY_ATTR] = text(found[METHOD_FIELD]);
    screenProps[NAME_ATTR] = open;
    screenProps[CHECKED_ATTR] = text(found[CHECKED]);
    screenProps[COUNT_ATTR] = text(found[WARNING_COUNT]);
    var drawn = [];
    if (open !== undefined && open !== EMPTY) {
      drawn.push(
        element(PreflightBox, {
          key: open,
          name: open,
          title: found[BOX_TITLE],
          widget: widgetOf(open)
        })
      );
    }
    drawn.push(
      element(StatusLine, {
        key: STATUS_PART,
        words: found[STATUS_LINE],
        level: found[STATUS_LEVEL]
      })
    );
    drawn.push(
      element(OutcomeMark, {
        key: OUTCOME_PART,
        outcome: found[OUTCOME],
        answered: found[ANSWERED],
        checked: found[CHECKED]
      })
    );
    resultNames().forEach(function (name, at) {
      drawn.push(
        element(ResultField, {
          key: name,
          name: name,
          at: at,
          value: resultField(name)
        })
      );
    });
    warnings().forEach(function (line, at) {
      drawn.push(element(WarningLine, { key: String(at), words: line, at: at }));
    });
    stepNames().forEach(function (name, at) {
      drawn.push(
        element(CheckStep, { key: STEP_PART + String(at), name: name, at: at })
      );
    });
    return element(DIV_TAG, screenProps, drawn);
  }

  CHILD_PARTS[ICON_CHILD] = BoxIcon;
  CHILD_PARTS[SPACER_CHILD] = BoxSpacer;
  CHILD_PARTS[TEXT_CHILD] = BoxBody;
  CHILD_PARTS[BUTTON_BOX_CHILD] = ButtonBox;

  function heldFieldCount(found) {
    return DECLARED_FIELDS.filter(function (name) {
      return owns(found, name);
    }).length;
  }

  // Counts every list the payload declares against the entries it holds.
  function report() {
    var found = held.model;
    return {
      declared: {
        fields: DECLARED_FIELDS.length,
        steps: listField(found, CALL_NAMES).length,
        result: listField(found, RESULT_FIELDS).length,
        buttons: listField(found, BUTTON_NAMES).length,
        boxes: listField(found, BOXES).length,
        outcomes: listField(found, OUTCOMES).length,
        children: listField(objectField(found, LAYOUT), ORDER).length,
        warnings: found[WARNING_COUNT]
      },
      held: {
        fields: heldFieldCount(found),
        steps: listField(found, CALLS).length,
        result: Object.keys(objectField(found, RESULT)).length,
        buttons: Object.keys(objectField(found, BUTTONS)).length,
        boxes: Object.keys(objectField(found, BOX_WIDGETS)).length,
        outcomes: Object.keys(objectField(found, CREATES_BOT)).length,
        children: Object.keys(objectField(objectField(found, LAYOUT), CHILD_OBJECT_NAMES))
          .length,
        warnings: warnings().length,
        lines: listField(found, BOX_BODY_LINES).length
      },
      faults: screenFaults.slice()
    };
  }

  function setScreen(found) {
    if (!isPlainObject(found)) {
      held = null;
      screenFaults = [fault(null, null, NOT_AN_OBJECT_FAULT, kindOf(found))];
      return { declared: null, held: null, faults: screenFaults.slice() };
    }
    held = { model: found };
    screenFaults = [];
    checkFields(found);
    checkSteps(found);
    checkOrderedBags(found);
    checkButtons(found);
    checkOutcomes(found);
    checkResult(found);
    checkReport(found);
    checkClaims(found);
    checkLayout(found);
    checkWidgets(found);
    checkColours(found);
    checkBagOrder(found);
    checkDrawnMarkup(found);
    return report();
  }

  // Asks METHOD once, clearing asked so a refused first ask is retried.
  function loadScreen(params) {
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
        setScreen(found);
        return found;
      })
      .catch(function (err) {
        loadFault = err.message;
        asked = null;
        return null;
      });
    return asked;
  }

  // Records one press, which the wizard sends back as the button parameter.
  function press(name) {
    pressed.push(name);
    return name;
  }

  function presses() {
    return pressed.slice();
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
    return screenFaults.slice();
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
  function renderScreen(target, found) {
    if (isPlainObject(found)) {
      setScreen(found);
    }
    return draw(target, element(Screen, { model: held === null ? null : held.model }));
  }

  // The named empty space the bot wizard left, or the root element itself.
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
    return space === null ? null : renderScreen(space, found);
  }

  function forget() {
    held = null;
    screenFaults = [];
    loadFault = null;
    asked = null;
    pressed = [];
  }

  global.acervatorSetPreflightCheck = setScreen;
  global.acervatorLoadPreflightCheck = loadScreen;
  global.acervatorPreflightCheck = {
    method: METHOD,
    spacePart: PAGE_PART,
    Screen: Screen,
    PreflightBox: PreflightBox,
    BoxBody: BoxBody,
    ButtonBox: ButtonBox,
    StatusLine: StatusLine,
    payload: payload,
    declaredNames: declaredNames,
    field: field,
    bag: bag,
    list: list,
    bagKeys: bagKeys,
    boxName: boxName,
    boxNames: boxNames,
    widgetOf: widgetOf,
    openWidget: openWidget,
    layout: layout,
    layoutOrder: layoutOrder,
    layoutStretch: layoutStretch,
    layoutObjectName: layoutObjectName,
    buttonNames: buttonNames,
    buttonNamed: buttonNamed,
    boxButtons: boxButtons,
    actionNameFor: actionNameFor,
    actionFor: actionFor,
    bodyLines: bodyLines,
    reportLines: reportLines,
    result: result,
    resultNames: resultNames,
    resultField: resultField,
    warnings: warnings,
    outcome: outcome,
    outcomeNames: outcomeNames,
    outcomeLevel: outcomeLevel,
    createsBot: createsBot,
    checkRan: checkRan,
    calls: calls,
    callNames: callNames,
    stepNames: stepNames,
    stepNamed: stepNamed,
    press: press,
    presses: presses,
    wholeSheet: wholeSheet,
    paintedStyle: paintedStyle,
    isSwappedAlpha: isSwappedAlpha,
    isReorderedKey: isReorderedKey,
    lineBreak: lineBreak,
    kinds: kinds,
    notPlainData: notPlainData,
    faults: faults,
    loadError: loadError,
    isLoaded: isLoaded,
    renderScreen: renderScreen,
    spaceIn: spaceIn,
    fill: fill,
    forget: forget
  };
})(window);
