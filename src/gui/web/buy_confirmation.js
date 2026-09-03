// The buy confirmation dialog, as buy_confirmation_surface.py serves it.
(function (global) {
  "use strict";

  var METHOD = "buy_confirmation.state";

  var WIDGET = "widget";
  var LAYOUT = "layout";
  var BUTTON_ROW = "button_row";
  var REASON_LABEL = "reason_label";
  var SEPARATOR = "separator";
  var DETAILS_LABEL = "details_label";
  var BUTTONS = "buttons";
  var ACTIONS = "actions";
  var ANSWERS = "answers";
  var BUTTON_ANSWERS = "button_answers";
  var DEFAULT_ANSWER = "default_answer";
  var CLOSED_ANSWER = "closed_answer";
  var HEADLESS_ANSWER = "headless_answer";
  var TIMEOUT_SEC = "timeout_sec";
  var TIMEOUT_MS = "timeout_ms";
  var REQUEST_FIELDS = "request_fields";
  var PAYLOAD_FIELDS = "payload_fields";
  var DIALOG_FIELDS = "dialog_fields";
  var REASON_TEXT = "reason_text";
  var DETAILS_TEXT = "details_text";
  var DETAIL_ROW_ORDER = "detail_row_order";
  var DETAIL_ROW_LABELS = "detail_row_labels";
  var DETAIL_ROW_VALUES = "detail_row_values";
  var RESULT_VALUE = "result_value";
  var ACCEPTED = "accepted";
  var CALLS = "calls";
  var REASON_COLOR = "reason_color";
  var YES_SURFACE = "yes_surface";
  var NO_SURFACE = "no_surface";
  var BUTTON_TEXT_COLOR = "button_text_color";

  // Every top-level name the buy_confirmation.state payload carries.
  var DECLARED_FIELDS = [
    WIDGET,
    LAYOUT,
    BUTTON_ROW,
    REASON_LABEL,
    SEPARATOR,
    DETAILS_LABEL,
    BUTTONS,
    ACTIONS,
    ANSWERS,
    BUTTON_ANSWERS,
    DEFAULT_ANSWER,
    CLOSED_ANSWER,
    HEADLESS_ANSWER,
    TIMEOUT_SEC,
    TIMEOUT_MS,
    REQUEST_FIELDS,
    PAYLOAD_FIELDS,
    DIALOG_FIELDS,
    REASON_TEXT,
    DETAILS_TEXT,
    DETAIL_ROW_ORDER,
    DETAIL_ROW_LABELS,
    DETAIL_ROW_VALUES,
    RESULT_VALUE,
    ACCEPTED,
    CALLS,
    REASON_COLOR,
    YES_SURFACE,
    NO_SURFACE,
    BUTTON_TEXT_COLOR
  ];

  var DECLARED_BAGS = [
    WIDGET,
    LAYOUT,
    BUTTON_ROW,
    REASON_LABEL,
    SEPARATOR,
    DETAILS_LABEL,
    BUTTONS,
    ACTIONS,
    BUTTON_ANSWERS,
    DETAIL_ROW_LABELS,
    DETAIL_ROW_VALUES
  ];

  var DECLARED_LISTS = [
    ANSWERS,
    REQUEST_FIELDS,
    PAYLOAD_FIELDS,
    DIALOG_FIELDS,
    DETAIL_ROW_ORDER,
    CALLS,
    REASON_COLOR,
    YES_SURFACE,
    NO_SURFACE,
    BUTTON_TEXT_COLOR
  ];

  var ORDER = "order";
  var MARGINS_PX = "margins_px";
  var SPACING_PX = "spacing_px";
  var CHILD_STRETCH = "child_stretch";

  var ACCESSIBLE_NAME = "accessible_name";
  var WINDOW_TITLE = "window_title";
  var MODAL = "modal";
  var MINIMUM_WIDTH_PX = "minimum_width_px";
  var SIZE_PX = "size_px";
  var STYLE_SHEET = "style_sheet";
  var STAYS_ON_TOP = "stays_on_top";

  var POINT_SIZE = "point_size";
  var BOLD = "bold";
  var WORD_WRAP = "word_wrap";

  var TEXT_KEY = "text";
  var ENABLED_KEY = "enabled";

  var REASON_CHILD = "reason";
  var SEPARATOR_CHILD = "separator";
  var DETAILS_CHILD = "details";
  var BUTTON_ROW_CHILD = "button_row";

  var YES = "yes";
  var NO = "no";
  var SKIP = "skip";

  var MISSING_FAULT = "missing";
  var NOT_AN_OBJECT_FAULT = "not-an-object";
  var NOT_A_BAG_FAULT = "not-a-bag";
  var NOT_A_LIST_FAULT = "not-a-list";
  var SHORT_LIST_FAULT = "short-list";
  var UNKNOWN_NAME_FAULT = "unknown-name";
  var SWAPPED_ALPHA_FAULT = "swapped-alpha";
  var NOT_CSS_FAULT = "not-css";
  var MARKUP_FAULT = "markup";
  var NON_FINITE_FAULT = "non-finite";
  var REORDERED_KEY_FAULT = "reordered-key";

  var ROW_AT = "row:";
  var EMPTY = "";
  var PATH_SPLIT = ".";

  var ZERO = Number(EMPTY);
  var ONE = Number(true);
  var TWO = ONE + ONE;
  var THREE = TWO + ONE;
  var FOUR = THREE + ONE;

  var NO_BRIDGE = "the preload bridge is not present";

  var MARKUP_OPEN = "<";

  var SCREEN_CLASS = "acervator-buy-confirmation";
  var DIV_TAG = "div";
  var SPAN_TAG = "span";
  var STRONG_TAG = "b";
  var BUTTON_TAG = "button";
  var BUTTON_TYPE = "button";
  var HR_TAG = "hr";

  var SCREEN_PART = "buy-confirmation";
  var REASON_PART = "reason-banner";
  var SEPARATOR_PART = "separator";
  var DETAILS_PART = "details";
  var ROW_PART = "detail-row";
  var LABEL_PART = "detail-label";
  var VALUE_PART = "detail-value";
  var BUTTON_ROW_PART = "button-row";
  var BUTTON_PART = "confirm-button";

  //: The named empty space a host page leaves for this screen.
  var PAGE_PART = "buy-confirmation-page";

  var PART_ATTR = "data-part";
  var KEY_ATTR = "data-key";
  var INDEX_ATTR = "data-index";
  var ANSWER_ATTR = "data-answer";
  var MODAL_ATTR = "data-modal";
  var TOP_ATTR = "data-stays-on-top";
  var ACCEPTED_ATTR = "data-accepted";
  var RESULT_ATTR = "data-result-value";
  var READY_ATTR = "data-ready";
  var ARIA_LABEL = "aria-label";
  var ARIA_DISABLED = "aria-disabled";

  var SELECT_OPEN = "[";
  var SELECT_IS = "=\"";
  var SELECT_CLOSE = "\"]";

  var PT = "pt";
  var SPACE = " ";
  var FLEX = "flex";
  var COLUMN_DIRECTION = "column";
  var ROW_DIRECTION = "row";
  var PRE_WRAP = "pre-wrap";
  var BOLD_WEIGHT = "bold";
  var NORMAL_WEIGHT = "normal";
  var FLEX_END = "flex-end";

  var STRING_KIND = "string";
  var NUMBER_KIND = "number";
  var BOOLEAN_KIND = "boolean";
  var FUNCTION_KIND = "function";
  var NULL_KIND = "null";

  var held = null;
  var screenFaults = [];
  var loadFault = null;
  var asked = null;
  var pressed = [];
  var lastRequest = null;
  var lastTarget = null;
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

  function carries(value, mark) {
    return String(value).indexOf(mark) >= ZERO;
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

  // shared_widgets.js owns the one-carrier rule that names a spacing token.
  function variableFor(value) {
    var api = global.acervatorWidgets;
    if (!api || typeof api.variableFor !== FUNCTION_KIND) {
      return undefined;
    }
    return api.variableFor(value);
  }

  // A whole-number token published bare would render `0px` through CSS, so
  // every length is scaled by `calc()` the same way every merged module does.
  function length(value) {
    if (value === null || value === undefined) {
      return undefined;
    }
    var name = variableFor(value);
    if (name === undefined) {
      return String(value) + "px";
    }
    return "calc(var(--" + name + ", " + String(value) + ") * 1px)";
  }

  // Qt reads a label's point size in points, which CSS also carries natively.
  function pointsOf(value) {
    return value === null || value === undefined ? undefined : String(value) + PT;
  }

  var HEX_MARK = "#";
  var DIGITS = "0123456789";
  //: The width of a colour written with eight hex digits, Qt's own alpha shape.
  var SWAPPED_LENGTH = HEX_MARK.length + "aabbccdd".length;

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

  var QT_ONLY = "qlineargradient";

  function checkColour(where, field, value) {
    if (isSwappedAlpha(value)) {
      note(where, field, SWAPPED_ALPHA_FAULT, value);
    }
  }

  function sheetsOf(found) {
    return [
      { where: REASON_LABEL, field: STYLE_SHEET, sheet: objectField(found, REASON_LABEL)[STYLE_SHEET] },
      { where: DETAILS_LABEL, field: STYLE_SHEET, sheet: objectField(found, DETAILS_LABEL)[STYLE_SHEET] },
      { where: YES, field: STYLE_SHEET, sheet: objectField(objectField(found, BUTTONS), YES)[STYLE_SHEET] },
      { where: NO, field: STYLE_SHEET, sheet: objectField(objectField(found, BUTTONS), NO)[STYLE_SHEET] },
      { where: SKIP, field: STYLE_SHEET, sheet: objectField(objectField(found, BUTTONS), SKIP)[STYLE_SHEET] }
    ];
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

  // `default_answer`, `closed_answer`, `headless_answer` and `result_value`
  // must each be one of the four answers the surface declares.
  function checkAnswers(found) {
    var named = listField(found, ANSWERS);
    [DEFAULT_ANSWER, CLOSED_ANSWER, HEADLESS_ANSWER, RESULT_VALUE].forEach(function (field) {
      if (owns(found, field) && named.indexOf(found[field]) < ZERO) {
        note(null, field, UNKNOWN_NAME_FAULT, found[field]);
      }
    });
    var reached = objectField(found, BUTTON_ANSWERS);
    Object.keys(reached).forEach(function (name) {
      if (named.indexOf(reached[name]) < ZERO) {
        note(name, BUTTON_ANSWERS, UNKNOWN_NAME_FAULT, reached[name]);
      }
    });
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
  }

  function checkButtonRow(found) {
    var order = listField(objectField(found, BUTTON_ROW), ORDER);
    var stretch = listField(objectField(found, BUTTON_ROW), CHILD_STRETCH);
    if (order.length !== stretch.length) {
      note(null, BUTTON_ROW, SHORT_LIST_FAULT, CHILD_STRETCH + PATH_SPLIT + stretch.length);
    }
    var bag = objectField(found, BUTTONS);
    order.forEach(function (name, at) {
      if (!owns(bag, name)) {
        note(ROW_AT + String(at), BUTTONS, MISSING_FAULT, name);
      }
    });
  }

  function checkLayout(found) {
    var order = listField(objectField(found, LAYOUT), ORDER);
    var stretch = listField(objectField(found, LAYOUT), CHILD_STRETCH);
    if (order.length !== stretch.length) {
      note(null, LAYOUT, SHORT_LIST_FAULT, CHILD_STRETCH + PATH_SPLIT + stretch.length);
    }
  }

  function checkDetailRows(found) {
    var order = listField(found, DETAIL_ROW_ORDER);
    var labels = objectField(found, DETAIL_ROW_LABELS);
    var values = objectField(found, DETAIL_ROW_VALUES);
    if (Object.keys(labels).length !== order.length) {
      note(null, DETAIL_ROW_LABELS, SHORT_LIST_FAULT, DETAIL_ROW_ORDER + PATH_SPLIT + Object.keys(labels).length);
    }
    if (Object.keys(values).length !== order.length) {
      note(null, DETAIL_ROW_VALUES, SHORT_LIST_FAULT, DETAIL_ROW_ORDER + PATH_SPLIT + Object.keys(values).length);
    }
    order.forEach(function (row, at) {
      if (!owns(labels, row)) {
        note(ROW_AT + String(at), DETAIL_ROW_LABELS, MISSING_FAULT, row);
      }
      if (!owns(values, row)) {
        note(ROW_AT + String(at), DETAIL_ROW_VALUES, MISSING_FAULT, row);
      }
    });
  }

  function checkMarkup(where, field, carried) {
    if (typeof carried === STRING_KIND && carries(carried, MARKUP_OPEN)) {
      note(where, field, MARKUP_FAULT, MARKUP_OPEN);
    }
  }

  // Only the words this screen draws as characters are swept: `details_text`
  // is Qt rich text the browser never renders, so a tag there is expected.
  function checkDrawnMarkup(found) {
    checkMarkup(null, REASON_TEXT, found[REASON_TEXT]);
    var values = objectField(found, DETAIL_ROW_VALUES);
    Object.keys(values).forEach(function (row) {
      checkMarkup(row, DETAIL_ROW_VALUES, values[row]);
    });
    var buttons = objectField(found, BUTTONS);
    Object.keys(buttons).forEach(function (name) {
      checkMarkup(name, BUTTONS, objectField(buttons, name)[TEXT_KEY]);
    });
  }

  function checkFinite(where, field, value) {
    if (typeof value === NUMBER_KIND && !isFinite(value)) {
      note(where, field, NON_FINITE_FAULT, value);
    }
  }

  // The bridge sanitises a non-finite number to `null` before this module
  // ever sees it; a bare NaN or Infinity reaching here is reported rather
  // than painted, so a caller cannot silently show a bogus figure.
  function checkNumbers(found) {
    [TIMEOUT_SEC, TIMEOUT_MS].forEach(function (field) {
      checkFinite(null, field, found[field]);
    });
    [REASON_COLOR, YES_SURFACE, NO_SURFACE, BUTTON_TEXT_COLOR].forEach(function (colourField) {
      listField(found, colourField).forEach(function (one, at) {
        checkFinite(ROW_AT + String(at), colourField, one);
      });
    });
  }

  function checkClaims(found) {
    // A row published with no label or no value is a figure this screen
    // would show without the surface ever having measured it.
    var order = listField(found, DETAIL_ROW_ORDER);
    var labels = objectField(found, DETAIL_ROW_LABELS);
    var values = objectField(found, DETAIL_ROW_VALUES);
    order.forEach(function (row) {
      if (owns(labels, row) && !label(labels[row])) {
        note(row, DETAIL_ROW_LABELS, MISSING_FAULT, row);
      }
      if (owns(values, row) && values[row] === undefined) {
        note(row, DETAIL_ROW_VALUES, MISSING_FAULT, row);
      }
    });
  }

  function setScreen(found) {
    if (!isPlainObject(found)) {
      held = null;
      screenFaults = [fault(null, null, NOT_AN_OBJECT_FAULT, kindOf(found))];
      return { faults: screenFaults.slice() };
    }
    held = { model: found };
    screenFaults = [];
    checkFields(found);
    checkButtonRow(found);
    checkLayout(found);
    checkDetailRows(found);
    checkColours(found);
    checkBagOrder(found);
    checkAnswers(found);
    checkDrawnMarkup(found);
    checkNumbers(found);
    checkClaims(found);
    return report();
  }

  function model() {
    return held === null ? null : held.model;
  }

  function report() {
    var found = held.model;
    return {
      declared: {
        fields: DECLARED_FIELDS.length,
        rows: listField(found, DETAIL_ROW_ORDER).length,
        buttons: listField(objectField(found, BUTTON_ROW), ORDER).length,
        calls: listField(found, CALLS).length
      },
      held: {
        fields: DECLARED_FIELDS.filter(function (name) {
          return owns(found, name);
        }).length,
        rows: Object.keys(objectField(found, DETAIL_ROW_VALUES)).length,
        buttons: Object.keys(objectField(found, BUTTONS)).length,
        calls: listField(found, CALLS).length
      },
      faults: screenFaults.slice()
    };
  }

  // -- what the module answers for ---------------------------------------

  function payload() {
    return held === null ? {} : copyOf(held.model);
  }

  function declaredNames() {
    return DECLARED_FIELDS.slice();
  }

  function field(name) {
    var found = model();
    return isPlainObject(found) && owns(found, name) ? found[name] : undefined;
  }

  function bag(name) {
    return copyOf(objectField(model(), name));
  }

  function list(name) {
    return listField(model(), name).slice();
  }

  function reasonText() {
    return field(REASON_TEXT);
  }

  function detailsText() {
    return field(DETAILS_TEXT);
  }

  function detailRowOrder() {
    return list(DETAIL_ROW_ORDER);
  }

  function detailRowLabel(row) {
    var found = bag(DETAIL_ROW_LABELS);
    return owns(found, row) ? found[row] : undefined;
  }

  function detailRowValue(row) {
    var found = bag(DETAIL_ROW_VALUES);
    return owns(found, row) ? found[row] : undefined;
  }

  function buttonNames() {
    return listField(objectField(model(), BUTTON_ROW), ORDER).slice();
  }

  function buttonNamed(name) {
    var found = bag(BUTTONS);
    return owns(found, name) ? found[name] : undefined;
  }

  function resultValue() {
    return field(RESULT_VALUE);
  }

  function accepted() {
    return field(ACCEPTED);
  }

  function calls() {
    return list(CALLS);
  }

  function ready() {
    return isPlainObject(model());
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

  function presses() {
    return pressed.slice();
  }

  function requestOf() {
    return lastRequest === null ? null : copyOf(lastRequest);
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

  // -- drawing --------------------------------------------------------

  function element() {
    return global.React.createElement.apply(null, arguments);
  }

  function marginStyle(box) {
    var written = listField(box, MARGINS_PX);
    if (written.length !== FOUR) {
      return {};
    }
    return {
      paddingLeft: length(written[ZERO]),
      paddingTop: length(written[ONE]),
      paddingRight: length(written[TWO]),
      paddingBottom: length(written[THREE])
    };
  }

  function ReasonBanner(props) {
    var widget = props.widget;
    var bannerStyle = styleOf(widget[STYLE_SHEET]);
    bannerStyle.fontWeight = widget[BOLD] === true ? BOLD_WEIGHT : NORMAL_WEIGHT;
    bannerStyle.fontSize = pointsOf(widget[POINT_SIZE]);
    bannerStyle.whiteSpace = widget[WORD_WRAP] === true ? PRE_WRAP : bannerStyle.whiteSpace;
    var bannerProps = { className: SCREEN_CLASS, style: bannerStyle };
    bannerProps[PART_ATTR] = REASON_PART;
    return element(DIV_TAG, bannerProps, text(props.words));
  }

  function Separator() {
    var lineProps = { className: SCREEN_CLASS };
    lineProps[PART_ATTR] = SEPARATOR_PART;
    return element(HR_TAG, lineProps, null);
  }

  function DetailRow(props) {
    var rowProps = { className: SCREEN_CLASS, style: { whiteSpace: PRE_WRAP } };
    rowProps[PART_ATTR] = ROW_PART;
    rowProps[KEY_ATTR] = text(props.row);
    rowProps[INDEX_ATTR] = text(props.at);
    var labelProps = {};
    labelProps[PART_ATTR] = LABEL_PART;
    var valueProps = {};
    valueProps[PART_ATTR] = VALUE_PART;
    return element(
      DIV_TAG,
      rowProps,
      element(STRONG_TAG, labelProps, text(props.label)),
      SPACE,
      element(SPAN_TAG, valueProps, text(props.value))
    );
  }

  function DetailsBlock(props) {
    var widget = props.widget;
    var blockStyle = styleOf(widget[STYLE_SHEET]);
    blockStyle.display = FLEX;
    blockStyle.flexDirection = COLUMN_DIRECTION;
    var blockProps = { className: SCREEN_CLASS, style: blockStyle };
    blockProps[PART_ATTR] = DETAILS_PART;
    return element(
      DIV_TAG,
      blockProps,
      props.order.map(function (row, at) {
        return element(DetailRow, {
          key: row,
          row: row,
          at: at,
          label: props.labels[row],
          value: props.values[row]
        });
      })
    );
  }

  function ConfirmButton(props) {
    var one = isPlainObject(props.button) ? props.button : {};
    var buttonProps = {
      className: SCREEN_CLASS,
      type: BUTTON_TYPE,
      disabled: one[ENABLED_KEY] === false,
      style: styleOf(one[STYLE_SHEET]),
      onClick: function () {
        press(props.name);
      }
    };
    buttonProps[PART_ATTR] = BUTTON_PART;
    buttonProps[KEY_ATTR] = text(props.name);
    buttonProps[INDEX_ATTR] = text(props.at);
    buttonProps[ANSWER_ATTR] = text(props.answer);
    buttonProps[ARIA_LABEL] = label(text(one[TEXT_KEY]));
    buttonProps[ARIA_DISABLED] = text(one[ENABLED_KEY] === false);
    return element(BUTTON_TAG, buttonProps, text(one[TEXT_KEY]));
  }

  function ButtonRow(props) {
    var rowStyle = { display: FLEX, flexDirection: ROW_DIRECTION, justifyContent: FLEX_END };
    var rowMargins = marginStyle(props.layout);
    Object.keys(rowMargins).forEach(function (name) {
      rowStyle[name] = rowMargins[name];
    });
    if (owns(props.layout, SPACING_PX)) {
      rowStyle.gap = length(props.layout[SPACING_PX]);
    }
    var rowProps = { className: SCREEN_CLASS, style: rowStyle };
    rowProps[PART_ATTR] = BUTTON_ROW_PART;
    var answers = props.answers;
    return element(
      DIV_TAG,
      rowProps,
      props.order.map(function (name, at) {
        return element(ConfirmButton, {
          key: name,
          name: name,
          at: at,
          answer: owns(answers, name) ? answers[name] : undefined,
          button: props.buttons[name]
        });
      })
    );
  }

  var CHILD_PARTS = {};

  function childFor(name, widget, props) {
    var made = CHILD_PARTS[name];
    return made === undefined ? null : made(widget, props);
  }

  // `Screen` draws nothing for a payload that has not arrived yet, so no
  // button — confirm, refuse or skip — exists to be pressed before then.
  function Screen(props) {
    if (!isPlainObject(props.model)) {
      return null;
    }
    var found = props.model;
    var widget = objectField(found, WIDGET);
    var layout = objectField(found, LAYOUT);
    var order = listField(layout, ORDER);
    var screenStyle = marginStyle(layout);
    screenStyle.display = FLEX;
    screenStyle.flexDirection = COLUMN_DIRECTION;
    if (owns(layout, SPACING_PX)) {
      screenStyle.gap = length(layout[SPACING_PX]);
    }
    if (listField(widget, SIZE_PX).length === TWO) {
      screenStyle.minWidth = length(widget[MINIMUM_WIDTH_PX]);
    }
    var screenProps = { className: SCREEN_CLASS, id: props.id, style: screenStyle };
    screenProps[PART_ATTR] = SCREEN_PART;
    screenProps[MODAL_ATTR] = text(widget[MODAL]);
    screenProps[TOP_ATTR] = text(widget[STAYS_ON_TOP]);
    screenProps[ACCEPTED_ATTR] = text(found[ACCEPTED]);
    screenProps[RESULT_ATTR] = text(found[RESULT_VALUE]);
    screenProps[READY_ATTR] = String(ready());
    screenProps[ARIA_LABEL] = label(text(widget[ACCESSIBLE_NAME]));
    var drawn = order
      .map(function (name) {
        return childFor(name, widget, found);
      })
      .filter(function (one) {
        return one !== null;
      });
    return element(DIV_TAG, screenProps, drawn);
  }

  CHILD_PARTS[REASON_CHILD] = function (widget, found) {
    return element(ReasonBanner, {
      key: REASON_CHILD,
      widget: objectField(found, REASON_LABEL),
      words: found[REASON_TEXT]
    });
  };
  CHILD_PARTS[SEPARATOR_CHILD] = function () {
    return element(Separator, { key: SEPARATOR_CHILD });
  };
  CHILD_PARTS[DETAILS_CHILD] = function (widget, found) {
    return element(DetailsBlock, {
      key: DETAILS_CHILD,
      widget: objectField(found, DETAILS_LABEL),
      order: listField(found, DETAIL_ROW_ORDER),
      labels: objectField(found, DETAIL_ROW_LABELS),
      values: objectField(found, DETAIL_ROW_VALUES)
    });
  };
  CHILD_PARTS[BUTTON_ROW_CHILD] = function (widget, found) {
    return element(ButtonRow, {
      key: BUTTON_ROW_CHILD,
      layout: objectField(found, BUTTON_ROW),
      order: listField(objectField(found, BUTTON_ROW), ORDER),
      buttons: objectField(found, BUTTONS),
      answers: objectField(found, BUTTON_ANSWERS)
    });
  };

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

  // Validates and stores `found` unconditionally; draws only where a real
  // `ReactDOM` is present, so a bridge round-trip run under `QJSEngine` (no
  // document, no React) still exercises the structural checks and never
  // throws for want of a renderer.
  function renderScreen(target, found) {
    if (isPlainObject(found)) {
      setScreen(found);
    }
    if (typeof global.ReactDOM === "undefined" || !target) {
      return target;
    }
    return draw(target, element(Screen, { model: held === null ? null : held.model }));
  }

  function bridgeCall(params) {
    if (!global.acervator || typeof global.acervator.call !== FUNCTION_KIND) {
      loadFault = NO_BRIDGE;
      return Promise.resolve(null);
    }
    return global.acervator
      .call(METHOD, isPlainObject(params) ? params : {})
      .then(function (found) {
        loadFault = null;
        return found;
      })
      .catch(function (err) {
        loadFault = err.message;
        return null;
      });
  }

  // Opens one confirmation. `requestFields` carries the seven fields the
  // surface reads on every call; `reset` starts a fresh answer so a stale
  // one from a previous request cannot be read as this one's.
  function load(target, requestFields) {
    lastRequest = isPlainObject(requestFields) ? copyOf(requestFields) : {};
    lastTarget = target;
    var params = copyOf(lastRequest);
    params.reset = true;
    asked = bridgeCall(params).then(function (found) {
      if (found !== null) {
        renderScreen(target, found);
      }
      return found;
    });
    return asked;
  }

  // Presses one button: re-submits the same seven fields the dialog opened
  // with, so the surface answers about the request actually on screen.
  function press(name) {
    pressed.push(name);
    if (lastRequest === null) {
      return Promise.resolve(null);
    }
    var params = copyOf(lastRequest);
    params.button = name;
    return bridgeCall(params).then(function (found) {
      if (found !== null && lastTarget !== null) {
        renderScreen(lastTarget, found);
      }
      return found;
    });
  }

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
    return root.querySelector(SELECT_OPEN + PART_ATTR + SELECT_IS + PAGE_PART + SELECT_CLOSE);
  }

  function fill(root, requestFields) {
    var space = spaceIn(root);
    return space === null ? null : load(space, requestFields);
  }

  function forget() {
    held = null;
    screenFaults = [];
    loadFault = null;
    asked = null;
    pressed = [];
    lastRequest = null;
    lastTarget = null;
  }

  global.acervatorSetBuyConfirmation = setScreen;
  global.acervatorLoadBuyConfirmation = load;
  global.acervatorBuyConfirmation = {
    method: METHOD,
    spacePart: PAGE_PART,
    Screen: Screen,
    ReasonBanner: ReasonBanner,
    DetailsBlock: DetailsBlock,
    ButtonRow: ButtonRow,
    payload: payload,
    declaredNames: declaredNames,
    field: field,
    bag: bag,
    list: list,
    reasonText: reasonText,
    detailsText: detailsText,
    detailRowOrder: detailRowOrder,
    detailRowLabel: detailRowLabel,
    detailRowValue: detailRowValue,
    buttonNames: buttonNames,
    buttonNamed: buttonNamed,
    resultValue: resultValue,
    accepted: accepted,
    calls: calls,
    ready: ready,
    isSwappedAlpha: isSwappedAlpha,
    isReorderedKey: isReorderedKey,
    wholeSheet: wholeSheet,
    kinds: kinds,
    notPlainData: notPlainData,
    faults: faults,
    loadError: loadError,
    isLoaded: isLoaded,
    press: press,
    presses: presses,
    requestOf: requestOf,
    renderScreen: renderScreen,
    load: load,
    spaceIn: spaceIn,
    fill: fill,
    forget: forget
  };
})(window);
