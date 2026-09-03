// Draws the Stack Tranches tab from the stack_tranches_tab.state payload.
(function (global) {
  "use strict";

  var METHOD = "stack_tranches_tab.state";

  var ACCESSIBLE_NAME = "accessible_name";
  var ACTIONS = "actions";
  var ANSWERS = "answers";
  var ATTRIBUTES = "attributes";
  var BOXES = "boxes";
  var BUS_EMITS = "bus_emits";
  var BUS_TOPICS = "bus_topics";
  var CALL_NAMES = "call_names";
  var CALLS = "calls";
  var CLEAR_BUTTON = "clear_button";
  var COLOURS = "colours";
  var CONTAINER = "container";
  var COUNTERS_BUTTON = "counters_button";
  var COUNTS = "counts";
  var DETAIL = "detail";
  var EMPTY_LABEL = "empty_label";
  var FORMATS = "formats";
  var ICONS = "icons";
  var KEYS = "keys";
  var LABELS = "labels";
  var METHOD_FIELD = "method";
  var OUTCOME = "outcome";
  var OUTCOMES = "outcomes";
  var PENDING_SIZE_TOTAL = "pending_size_total";
  var REFRESH_STATUS = "refresh_status";
  var RESET_TS = "reset_ts";
  var SETTLED_LINES = "settled_lines";
  var SIGNALS = "signals";
  var STATUSES = "statuses";
  var STYLES = "styles";
  var SUMMARY_GROUP = "summary_group";
  var SUMMARY_ROWS = "summary_rows";
  var SUMMARY_STYLES = "summary_styles";
  var TAB_LABEL = "tab_label";
  var TEXTS = "texts";
  var THREADS = "threads";
  var THRESHOLDS = "thresholds";
  var TIMER_DELAYS_MS = "timer_delays_ms";
  var TIMERS = "timers";
  var TITLES = "titles";

  // Every top-level name the stack_tranches_tab.state payload carries.
  var DECLARED_FIELDS = [
    ACCESSIBLE_NAME,
    ACTIONS,
    ANSWERS,
    ATTRIBUTES,
    BOXES,
    BUS_EMITS,
    BUS_TOPICS,
    CALL_NAMES,
    CALLS,
    CLEAR_BUTTON,
    COLOURS,
    CONTAINER,
    COUNTERS_BUTTON,
    COUNTS,
    DETAIL,
    EMPTY_LABEL,
    FORMATS,
    ICONS,
    KEYS,
    LABELS,
    METHOD_FIELD,
    OUTCOME,
    OUTCOMES,
    PENDING_SIZE_TOTAL,
    REFRESH_STATUS,
    RESET_TS,
    SETTLED_LINES,
    SIGNALS,
    STATUSES,
    STYLES,
    SUMMARY_GROUP,
    SUMMARY_ROWS,
    SUMMARY_STYLES,
    TAB_LABEL,
    TEXTS,
    THREADS,
    THRESHOLDS,
    TIMER_DELAYS_MS,
    TIMERS,
    TITLES
  ];

  var DECLARED_BAGS = [
    ACTIONS,
    ANSWERS,
    ATTRIBUTES,
    CLEAR_BUTTON,
    COLOURS,
    CONTAINER,
    COUNTERS_BUTTON,
    COUNTS,
    DETAIL,
    EMPTY_LABEL,
    FORMATS,
    ICONS,
    KEYS,
    LABELS,
    STATUSES,
    STYLES,
    SUMMARY_GROUP,
    TEXTS,
    THRESHOLDS,
    TIMERS,
    TITLES
  ];

  var DECLARED_LISTS = [
    BOXES,
    BUS_EMITS,
    BUS_TOPICS,
    CALL_NAMES,
    CALLS,
    OUTCOMES,
    SETTLED_LINES,
    SIGNALS,
    SUMMARY_ROWS,
    SUMMARY_STYLES,
    THREADS,
    TIMER_DELAYS_MS
  ];

  // The two wired names as a list, because a bag key order is the only other order.
  var CLEAR_CLICKED = "clear_button.clicked";
  var COUNTERS_CLICKED = "counters_button.clicked";
  var ACTION_NAMES = [CLEAR_CLICKED, COUNTERS_CLICKED];
  var BUTTON_PLAN = [
    [CLEAR_BUTTON, CLEAR_CLICKED],
    [COUNTERS_BUTTON, COUNTERS_CLICKED]
  ];

  // The answer names, as a list, so one box offers them in one order.
  var YES_NAME = "yes";
  var NO_NAME = "no";
  var DEFAULT_NAME = "default";
  var ANSWER_NAMES = [YES_NAME, NO_NAME];

  var QUESTION_NAME = "question";

  var TEXT_FIELD = "text";
  var ENABLED = "enabled";
  var TOOLTIP = "tooltip";
  var STYLE_SHEET = "style_sheet";
  var SHOWN = "shown";
  var WORD_WRAP = "word_wrap";
  var TITLE_FIELD = "title";
  var HEADER_TEXT = "header_text";
  var HEADER_STYLE = "header_style";
  var ROWS = "rows";
  var ROW_STYLES = "row_styles";
  var ROW_COUNT = "row_count";
  var SPACING_PX = "spacing_px";
  var MARGINS_SET = "margins_set";
  var CONFIGURED_BY_HOST = "configured_by_host";
  var FORMS_CONFIGURED = "forms_configured";
  var BOX_ICON = "icon";
  var BOX_TITLE = "title";
  var BOX_TEXT = "text";
  var BOX_FIELDS = [BOX_ICON, BOX_TITLE, BOX_TEXT];

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
  var DUPLICATE_NAME_FAULT = "duplicate-name";
  var NOT_CSS_FAULT = "not-css";

  var ROW_AT = "row:";
  var BOX_AT = "box:";
  var SUMMARY_AT = "summary:";
  var PATH_SPLIT = ".";
  var EMPTY = "";
  var SPACE = " ";

  var NO_BRIDGE = "the preload bridge is not present";

  // Qt paints qlineargradient by name and no browser stylesheet runs it.
  var QT_ONLY = "qlineargradient";

  var TAB_CLASS = "acervator-stack-tranches";

  var DIV_TAG = "div";
  var SPAN_TAG = "span";
  var BUTTON_TAG = "button";
  var BUTTON_TYPE = "button";

  var TAB_PART = "stack-tranches-tab";
  var SUMMARY_GROUP_PART = "summary-group";
  var SUMMARY_TITLE_PART = "summary-group-title";
  var SUMMARY_ROW_PART = "summary-row";
  var SUMMARY_LABEL_PART = "summary-label";
  var SUMMARY_VALUE_PART = "summary-value";
  var CLEAR_BUTTONS_PART = "clear-buttons";
  var CLEAR_BUTTON_PART = "clear-button";
  var EMPTY_NOTE_PART = "empty-note";
  var DETAIL_PANEL_PART = "detail-panel";
  var DETAIL_TITLE_PART = "detail-title";
  var DETAIL_HEADER_PART = "detail-header";
  var DETAIL_ROW_PART = "detail-row";
  var MESSAGE_BOX_PART = "message-box";
  var BOX_TITLE_PART = "box-title";
  var BOX_TEXT_PART = "box-text";
  var BOX_BUTTON_PART = "box-button";
  var OUTCOME_PART = "outcome";
  var REFRESH_PART = "refresh-status";
  var SETTLED_PART = "settled-line";

  // PAGE_PART is the space the Live Bot Settings window leaves for this tab.
  var PAGE_PART = "stack-tranches-page";

  var PART_ATTR = "data-part";
  var KEY_ATTR = "data-key";
  var NAME_ATTR = "data-name";
  var INDEX_ATTR = "data-index";
  var COUNT_ATTR = "data-count";
  var ENABLED_ATTR = "data-enabled";
  var ACTION_ATTR = "data-action";
  var ICON_ATTR = "data-icon";
  var VALUE_ATTR = "data-value";
  var DEFAULT_ATTR = "data-default";
  var SHOWN_ATTR = "data-shown";
  var WRAP_ATTR = "data-word-wrap";
  var HOST_ATTR = "data-configured-by-host";
  var MARGINS_ATTR = "data-margins-set";
  var STYLED_ATTR = "data-styled";
  var MATCHED_ATTR = "data-matched";
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
  var AUTO = "auto";
  var PRE = "pre";
  var PRE_WRAP = "pre-wrap";

  var ZERO = Number(EMPTY);
  var STEP = Number(true);

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

  function summaryRows() {
    return listField(model(), SUMMARY_ROWS);
  }

  function summaryStyles() {
    return listField(model(), SUMMARY_STYLES);
  }

  function summaryStyle(at) {
    return summaryStyles()[at];
  }

  // Every drawn row named by its own label, in the order the rows arrived.
  function drawnLabels() {
    return summaryRows().map(function (row) {
      return Array.isArray(row) && row.length ? row[ZERO] : undefined;
    });
  }

  function publishedLabels() {
    var bag = objectField(model(), LABELS);
    return Object.keys(bag).map(function (name) {
      return bag[name];
    });
  }

  // One summary row found by its own label, never by where it sits.
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

  function summaryStyleNamed(name) {
    var at = drawnLabels().indexOf(name);
    return at < ZERO ? undefined : summaryStyle(at);
  }

  function detailBag() {
    return objectField(model(), DETAIL);
  }

  function detailRows() {
    return listField(detailBag(), ROWS);
  }

  function detailStyle(at) {
    return listField(detailBag(), ROW_STYLES)[at];
  }

  // The first word of one printed row, which is the number that tranche prints.
  function firstWord(line) {
    var printed = String(line).trim();
    var at = printed.indexOf(SPACE);
    return at < ZERO ? printed : printed.slice(ZERO, at);
  }

  // Every tranche row named by the number it prints, never by its place.
  function rowIdentities() {
    return detailRows().map(function (line, at) {
      return { at: at, name: firstWord(line) };
    });
  }

  function detailRowNamed(name) {
    var found;
    rowIdentities().forEach(function (one) {
      if (one.name === name) {
        found = detailRows()[one.at];
      }
    });
    return found;
  }

  function buttonBag(field) {
    return objectField(model(), field);
  }

  function buttonNames() {
    return BUTTON_PLAN.map(function (pair) {
      return pair[STEP];
    });
  }

  function buttonFields() {
    return BUTTON_PLAN.map(function (pair) {
      return pair[ZERO];
    });
  }

  function action(name) {
    var found = objectField(model(), ACTIONS);
    return owns(found, name) ? found[name] : undefined;
  }

  function answerValue(name) {
    var found = objectField(model(), ANSWERS);
    return owns(found, name) ? found[name] : undefined;
  }

  function defaultAnswer() {
    return answerValue(DEFAULT_NAME);
  }

  function boxes() {
    return listField(model(), BOXES);
  }

  function questionIcon() {
    var found = objectField(model(), ICONS);
    return owns(found, QUESTION_NAME) ? found[QUESTION_NAME] : undefined;
  }

  // A box carrying the question icon asks, so it offers both answers.
  function isQuestionBox(box) {
    return isPlainObject(box) && box[BOX_ICON] === questionIcon();
  }

  function boxAnswers(box) {
    return isQuestionBox(box) ? ANSWER_NAMES.slice() : [NO_NAME];
  }

  function colourNamed(name) {
    var found = objectField(model(), COLOURS);
    return owns(found, name) ? found[name] : undefined;
  }

  function calls() {
    return listField(model(), CALLS).slice();
  }

  // Every style sheet the tab applies, each beside the field carrying it.
  function sheets() {
    var found = model();
    var detail = detailBag();
    var written = [
      { field: EMPTY_LABEL, sheet: objectField(found, EMPTY_LABEL)[STYLE_SHEET] },
      { field: DETAIL, sheet: detail[HEADER_STYLE] }
    ];
    buttonFields().forEach(function (field) {
      written.push({ field: field, sheet: buttonBag(field)[STYLE_SHEET] });
    });
    summaryStyles().forEach(function (sheet, at) {
      written.push({
        field: SUMMARY_STYLES,
        sheet: sheet,
        where: SUMMARY_AT + String(at)
      });
    });
    listField(detail, ROW_STYLES).forEach(function (sheet, at) {
      written.push({ field: ROW_STYLES, sheet: sheet, where: ROW_AT + String(at) });
    });
    Object.keys(objectField(found, STYLES)).forEach(function (name) {
      written.push({ field: STYLES, sheet: objectField(found, STYLES)[name] });
    });
    return written;
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
    buttonFields().forEach(function (field) {
      if (!isPlainObject(found[field])) {
        tabFaults.push(fault(null, field, NOT_A_BAG_FAULT, kindOf(found[field])));
      }
    });
  }

  function checkAnswers(found) {
    var bag = objectField(found, ANSWERS);
    ANSWER_NAMES.concat([DEFAULT_NAME]).forEach(function (name) {
      if (!owns(bag, name)) {
        tabFaults.push(fault(null, ANSWERS, MISSING_FAULT, name));
      }
    });
    var offered = ANSWER_NAMES.map(function (name) {
      return bag[name];
    });
    if (owns(bag, DEFAULT_NAME) && offered.indexOf(bag[DEFAULT_NAME]) < ZERO) {
      tabFaults.push(fault(null, ANSWERS, DISAGREES_FAULT, bag[DEFAULT_NAME]));
    }
  }

  function checkCounts(found) {
    var rows = listField(found, SUMMARY_ROWS);
    var styles = listField(found, SUMMARY_STYLES);
    if (rows.length !== styles.length) {
      tabFaults.push(fault(null, SUMMARY_STYLES, SHORT_LIST_FAULT, styles.length));
    }
    rows.forEach(function (row, at) {
      if (!Array.isArray(row)) {
        tabFaults.push(
          fault(SUMMARY_AT + String(at), SUMMARY_ROWS, NOT_A_LIST_FAULT, kindOf(row))
        );
        return;
      }
      if (row.length <= STEP) {
        tabFaults.push(
          fault(SUMMARY_AT + String(at), SUMMARY_ROWS, SHORT_LIST_FAULT, row.length)
        );
      }
    });
    var detail = objectField(found, DETAIL);
    var drawn = listField(detail, ROWS);
    if (drawn.length !== detail[ROW_COUNT]) {
      tabFaults.push(fault(null, ROW_COUNT, DISAGREES_FAULT, detail[ROW_COUNT]));
    }
    if (listField(detail, ROW_STYLES).length !== drawn.length) {
      tabFaults.push(
        fault(null, ROW_STYLES, SHORT_LIST_FAULT, listField(detail, ROW_STYLES).length)
      );
    }
  }

  // Each drawn row must carry a label the payload publishes for a row.
  function checkLabels(found) {
    var published = Object.keys(objectField(found, LABELS)).map(function (name) {
      return objectField(found, LABELS)[name];
    });
    listField(found, SUMMARY_ROWS).forEach(function (row, at) {
      var name = Array.isArray(row) && row.length ? row[ZERO] : undefined;
      if (published.indexOf(name) < ZERO) {
        tabFaults.push(fault(SUMMARY_AT + String(at), LABELS, UNNAMED_ROW_FAULT, name));
      }
    });
  }

  // Two tranches printing one number cannot be told apart by name.
  function checkRowNames() {
    var seen = [];
    rowIdentities().forEach(function (one) {
      if (seen.indexOf(one.name) >= ZERO) {
        tabFaults.push(
          fault(ROW_AT + String(one.at), ROWS, DUPLICATE_NAME_FAULT, one.name)
        );
      }
      seen.push(one.name);
    });
  }

  function checkColour(where, field, value) {
    if (isSwappedAlpha(value)) {
      tabFaults.push(fault(where, field, SWAPPED_ALPHA_FAULT, value));
    }
  }

  function checkColours(found) {
    var bag = objectField(found, COLOURS);
    Object.keys(bag).forEach(function (name) {
      checkColour(null, COLOURS, bag[name]);
    });
    sheets().forEach(function (one) {
      var where = one.where === undefined ? null : one.where;
      hexRuns(one.sheet).forEach(function (value) {
        checkColour(where, one.field, value);
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
      if (!isPlainObject(box)) {
        tabFaults.push(
          fault(BOX_AT + String(at), BOXES, NOT_AN_OBJECT_FAULT, kindOf(box))
        );
        return;
      }
      BOX_FIELDS.forEach(function (name) {
        if (!owns(box, name)) {
          tabFaults.push(fault(BOX_AT + String(at), BOXES, MISSING_FAULT, name));
        }
      });
      if (named.indexOf(box[BOX_TITLE]) < ZERO) {
        tabFaults.push(
          fault(BOX_AT + String(at), TITLES, UNNAMED_ROW_FAULT, box[BOX_TITLE])
        );
      }
      if (!boxAnswers(box).length) {
        tabFaults.push(
          fault(BOX_AT + String(at), BOXES, SHORT_LIST_FAULT, box[BOX_ICON])
        );
      }
    });
  }

  function element() {
    return global.React.createElement.apply(null, arguments);
  }

  // Every summary style is written CSS, so an empty sheet paints nothing.
  function paintedStyle(sheet) {
    return declarations(sheet).length ? styleOf(sheet) : {};
  }

  function SummaryRow(props) {
    var row = Array.isArray(props.row) ? props.row : [];
    var name = row.length ? row[ZERO] : undefined;
    var sheet = summaryStyle(props.at);
    var rowProps = {
      className: TAB_CLASS,
      style: { display: FLEX }
    };
    rowProps[PART_ATTR] = SUMMARY_ROW_PART;
    rowProps[KEY_ATTR] = text(name);
    rowProps[INDEX_ATTR] = text(props.at);
    var labelProps = { className: TAB_CLASS };
    labelProps[PART_ATTR] = SUMMARY_LABEL_PART;
    labelProps[KEY_ATTR] = text(name);
    var style = paintedStyle(sheet);
    style.whiteSpace = PRE;
    var valueProps = { className: TAB_CLASS, style: style };
    valueProps[PART_ATTR] = SUMMARY_VALUE_PART;
    valueProps[KEY_ATTR] = text(name);
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
      style: { display: FLEX, flexDirection: COLUMN_DIRECTION }
    };
    groupProps[PART_ATTR] = SUMMARY_GROUP_PART;
    groupProps[COUNT_ATTR] = text(summaryRows().length);
    groupProps[HOST_ATTR] = text(group[CONFIGURED_BY_HOST]);
    groupProps[MATCHED_ATTR] = text(group[FORMS_CONFIGURED]);
    var titleProps = { className: TAB_CLASS };
    titleProps[PART_ATTR] = SUMMARY_TITLE_PART;
    var drawn = [element(SPAN_TAG, titleProps, text(group[TITLE_FIELD]))];
    summaryRows().forEach(function (row, at) {
      drawn.push(
        element(SummaryRow, { key: SUMMARY_ROW_PART + String(at), row: row, at: at })
      );
    });
    return element(DIV_TAG, groupProps, drawn);
  }

  function ClearButton(props) {
    var one = buttonBag(props.field);
    var enabled = one[ENABLED] === true;
    var buttonProps = {
      className: TAB_CLASS,
      style: styleOf(one[STYLE_SHEET]),
      type: BUTTON_TYPE,
      title: label(one[TOOLTIP]),
      disabled: !enabled,
      onClick: function () {
        press(props.name, props.name);
        if (typeof props.onClear === "function") {
          props.onClear(props.name);
        }
      }
    };
    buttonProps[PART_ATTR] = CLEAR_BUTTON_PART;
    buttonProps[INDEX_ATTR] = text(props.at);
    buttonProps[NAME_ATTR] = props.name;
    buttonProps[KEY_ATTR] = props.field;
    buttonProps[ACTION_ATTR] = label(action(props.name));
    buttonProps[ENABLED_ATTR] = String(enabled);
    buttonProps[ARIA_LABEL] = label(one[TEXT_FIELD]);
    return element(BUTTON_TAG, buttonProps, text(one[TEXT_FIELD]));
  }

  function ClearButtons(props) {
    var boxProps = {
      className: TAB_CLASS,
      style: { display: FLEX }
    };
    boxProps[PART_ATTR] = CLEAR_BUTTONS_PART;
    boxProps[COUNT_ATTR] = text(BUTTON_PLAN.length);
    var drawn = BUTTON_PLAN.map(function (pair, at) {
      return element(ClearButton, {
        key: pair[STEP],
        field: pair[ZERO],
        name: pair[STEP],
        at: at,
        onClear: props.onClear
      });
    });
    return element(DIV_TAG, boxProps, drawn);
  }

  function EmptyNote(props) {
    var note = objectField(props.model, EMPTY_LABEL);
    var style = styleOf(note[STYLE_SHEET]);
    style.whiteSpace = note[WORD_WRAP] === true ? PRE_WRAP : PRE;
    var hidden = note[SHOWN] !== true;
    var noteProps = { className: TAB_CLASS, style: style, hidden: hidden };
    noteProps[PART_ATTR] = EMPTY_NOTE_PART;
    noteProps[SHOWN_ATTR] = text(note[SHOWN]);
    noteProps[WRAP_ATTR] = text(note[WORD_WRAP]);
    return element(DIV_TAG, noteProps, text(note[TEXT_FIELD]));
  }

  function DetailRow(props) {
    var style = styleOf(props.sheet);
    style.whiteSpace = PRE;
    var rowProps = { className: TAB_CLASS, style: style };
    rowProps[PART_ATTR] = DETAIL_ROW_PART;
    rowProps[INDEX_ATTR] = text(props.at);
    rowProps[NAME_ATTR] = text(props.name);
    rowProps[STYLED_ATTR] = String(Boolean(declarations(props.sheet).length));
    return element(DIV_TAG, rowProps, text(props.line));
  }

  function DetailPanel(props) {
    var detail = objectField(props.model, DETAIL);
    var panelProps = {
      className: TAB_CLASS,
      style: { display: FLEX, flexDirection: COLUMN_DIRECTION, overflow: AUTO },
      hidden: detail[SHOWN] !== true
    };
    panelProps[PART_ATTR] = DETAIL_PANEL_PART;
    panelProps[SHOWN_ATTR] = text(detail[SHOWN]);
    panelProps[COUNT_ATTR] = text(detail[ROW_COUNT]);
    var titleProps = { className: TAB_CLASS };
    titleProps[PART_ATTR] = DETAIL_TITLE_PART;
    var headerStyle = styleOf(detail[HEADER_STYLE]);
    headerStyle.whiteSpace = PRE;
    var headerProps = { className: TAB_CLASS, style: headerStyle };
    headerProps[PART_ATTR] = DETAIL_HEADER_PART;
    var drawn = [
      element(SPAN_TAG, titleProps, text(detail[TITLE_FIELD])),
      element(DIV_TAG, headerProps, text(detail[HEADER_TEXT]))
    ];
    rowIdentities().forEach(function (one) {
      drawn.push(
        element(DetailRow, {
          key: DETAIL_ROW_PART + String(one.at),
          line: detailRows()[one.at],
          sheet: detailStyle(one.at),
          name: one.name,
          at: one.at
        })
      );
    });
    return element(DIV_TAG, panelProps, drawn);
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
    buttonProps[DEFAULT_ATTR] = String(value === defaultAnswer());
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
    boxProps[DEFAULT_ATTR] = text(defaultAnswer());
    boxProps[COUNT_ATTR] = text(boxAnswers(box).length);
    var titleProps = { className: TAB_CLASS };
    titleProps[PART_ATTR] = BOX_TITLE_PART;
    var textProps = { className: TAB_CLASS, style: { whiteSpace: PRE_WRAP } };
    textProps[PART_ATTR] = BOX_TEXT_PART;
    var drawn = boxAnswers(box).map(function (name) {
      return element(BoxButton, { key: name, name: name, onAnswer: props.onAnswer });
    });
    return element(
      DIV_TAG,
      boxProps,
      element(SPAN_TAG, titleProps, text(box[BOX_TITLE])),
      element(DIV_TAG, textProps, text(box[BOX_TEXT])),
      drawn
    );
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
    var refreshProps = { className: TAB_CLASS };
    refreshProps[PART_ATTR] = REFRESH_PART;
    refreshProps[VALUE_ATTR] = text(found[REFRESH_STATUS]);
    var drawn = [
      element(SummaryGroup, { key: SUMMARY_GROUP_PART, model: found }),
      element(ClearButtons, {
        key: CLEAR_BUTTONS_PART,
        model: found,
        onClear: props.onClear
      }),
      element(EmptyNote, { key: EMPTY_NOTE_PART, model: found }),
      element(DetailPanel, { key: DETAIL_PANEL_PART, model: found }),
      element(SPAN_TAG, outcomeProps, text(found[OUTCOME])),
      element(SPAN_TAG, refreshProps, text(found[REFRESH_STATUS]))
    ];
    listField(found, SETTLED_LINES).forEach(function (line, at) {
      var lineProps = {
        key: SETTLED_PART + String(at),
        className: TAB_CLASS,
        style: { whiteSpace: PRE_WRAP }
      };
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

  // Counts fields, rows, labels, buttons and answers declared against those held.
  function report() {
    var found = held.model;
    var detail = objectField(found, DETAIL);
    var drawn = drawnLabels();
    var published = publishedLabels();
    return {
      declared: {
        fields: DECLARED_FIELDS.length,
        rows: detail[ROW_COUNT],
        summary: listField(found, SUMMARY_STYLES).length,
        labels: published.length,
        buttons: BUTTON_PLAN.length,
        actions: ACTION_NAMES.length,
        answers: ANSWER_NAMES.length
      },
      held: {
        fields: heldFieldCount(found),
        rows: listField(detail, ROWS).length,
        summary: listField(found, SUMMARY_ROWS).length,
        labels: drawn.filter(function (name) {
          return published.indexOf(name) >= ZERO;
        }).length,
        buttons: buttonFields().filter(function (field) {
          return isPlainObject(found[field]);
        }).length,
        actions: Object.keys(objectField(found, ACTIONS)).length,
        answers: ANSWER_NAMES.filter(function (name) {
          return owns(objectField(found, ANSWERS), name);
        }).length
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
    checkAnswers(found);
    checkCounts(found);
    checkLabels(found);
    checkRowNames();
    checkColours(found);
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
        onClear: wired.onClear,
        onAnswer: wired.onAnswer
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

  global.acervatorSetStackTranchesTab = setTab;
  global.acervatorLoadStackTranchesTab = loadTab;
  global.acervatorStackTranchesTab = {
    method: METHOD,
    spacePart: PAGE_PART,
    Tab: Tab,
    SummaryGroup: SummaryGroup,
    ClearButtons: ClearButtons,
    DetailPanel: DetailPanel,
    MessageBox: MessageBox,
    payload: payload,
    declaredNames: declaredNames,
    field: field,
    bag: bag,
    list: list,
    bagKeys: bagKeys,
    actionNames: actionNames,
    answerNames: answerNames,
    buttonNames: buttonNames,
    buttonFields: buttonFields,
    summaryRows: summaryRows,
    summaryStyles: summaryStyles,
    summaryStyle: summaryStyle,
    summaryStyleNamed: summaryStyleNamed,
    summaryRowNamed: summaryRowNamed,
    summaryValue: summaryValue,
    drawnLabels: drawnLabels,
    publishedLabels: publishedLabels,
    detailRows: detailRows,
    detailStyle: detailStyle,
    detailRowNamed: detailRowNamed,
    rowIdentities: rowIdentities,
    firstWord: firstWord,
    action: action,
    answerValue: answerValue,
    defaultAnswer: defaultAnswer,
    boxes: boxes,
    boxAnswers: boxAnswers,
    isQuestionBox: isQuestionBox,
    questionIcon: questionIcon,
    colourNamed: colourNamed,
    calls: calls,
    sheets: sheets,
    press: press,
    pressed: pressed,
    paintedStyle: paintedStyle,
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
