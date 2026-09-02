// Draws the Fold Tranches despawn rows, the order picker and the filter box.
(function (global) {
  "use strict";

  var METHOD = "fold_chrome.state";

  var ACTIONS = "actions";
  var ATTRIBUTES = "attributes";
  var BORDER = "border";
  var BUS_EMITS = "bus_emits";
  var BUS_TOPICS = "bus_topics";
  var CALL_NAMES = "call_names";
  var CALLS = "calls";
  var COLORS = "colors";
  var CONTRACT_PINS = "contract_pins";
  var CONTROL_COUNT = "control_count";
  var CONTROLS = "controls";
  var CONTROLS_SHAPE = "controls_shape";
  var DEFERRED = "deferred";
  var ELEMENT_NAMES = "element_names";
  var FORMATS = "formats";
  var HIDDEN = "hidden";
  var KEYS = "keys";
  var LABELS = "labels";
  var ORDERS = "orders";
  var PIN_SHAPE = "pin_shape";
  var PINS = "pins";
  var REBUILD_CALLS = "rebuild_calls";
  var REBUILD_TIMER = "rebuild_timer";
  var ROW_COUNT = "row_count";
  var ROWS = "rows";
  var SCREEN_ELEMENTS = "screen_elements";
  var SIGNALS = "signals";
  var SORT_ORDER = "sort_order";
  var TEXTS = "texts";
  var THREADS = "threads";
  var THRESHOLDS = "thresholds";
  var TIMER_DELAYS_MS = "timer_delays_ms";
  var TIMERS = "timers";
  var TIMERS_BUILT = "timers_built";
  var WARNINGS = "warnings";

  // Every top-level name the fold_chrome.state payload carries.
  var DECLARED_FIELDS = [
    ACTIONS,
    ATTRIBUTES,
    BORDER,
    BUS_EMITS,
    BUS_TOPICS,
    CALL_NAMES,
    CALLS,
    COLORS,
    CONTRACT_PINS,
    CONTROL_COUNT,
    CONTROLS,
    CONTROLS_SHAPE,
    DEFERRED,
    ELEMENT_NAMES,
    FORMATS,
    HIDDEN,
    KEYS,
    LABELS,
    ORDERS,
    PIN_SHAPE,
    PINS,
    REBUILD_CALLS,
    REBUILD_TIMER,
    ROW_COUNT,
    ROWS,
    SCREEN_ELEMENTS,
    SIGNALS,
    SORT_ORDER,
    TEXTS,
    THREADS,
    THRESHOLDS,
    TIMER_DELAYS_MS,
    TIMERS,
    TIMERS_BUILT,
    WARNINGS
  ];

  var DECLARED_BAGS = [
    ACTIONS,
    ATTRIBUTES,
    BORDER,
    COLORS,
    CONTROLS_SHAPE,
    ELEMENT_NAMES,
    FORMATS,
    KEYS,
    LABELS,
    ORDERS,
    PIN_SHAPE,
    TEXTS,
    THRESHOLDS,
    TIMERS
  ];

  var DECLARED_LISTS = [
    BUS_EMITS,
    BUS_TOPICS,
    CALL_NAMES,
    CALLS,
    CONTRACT_PINS,
    CONTROLS,
    DEFERRED,
    HIDDEN,
    PINS,
    ROWS,
    SCREEN_ELEMENTS,
    SIGNALS,
    THREADS,
    TIMER_DELAYS_MS,
    TIMERS_BUILT,
    WARNINGS
  ];

  // Names inside the ELEMENT_NAMES bag, each one the identity of one element.
  var ORDER_LABEL_NAME = "order_label";
  var SORT_COMBO_NAME = "sort_combo";
  var FILTER_EDIT_NAME = "filter_edit";
  var TIMER_ROW_NAME = "timer_row_value";
  var PREVIEW_ROW_NAME = "preview_row_value";

  var TIMER_ROW_LABEL = "timer_row";
  var PREVIEW_ROW_LABEL = "preview_row";
  var ORDER_LABEL_TEXT = "order";

  var BY_FILL = "by_fill";
  var BORDER_WIDTH = "width_px";
  var OFFERED = "offered";
  var CLEAR_BUTTON = "clear_button";
  var FILTER_STRETCH = "filter_stretch";
  var NO_STRETCH = "no_stretch";
  var SPACING_SET = "spacing_set";
  var MARGINS_SET = "margins_set";

  var SORT_ACTION = "sort_combo.activated";
  var FILTER_ACTION = "filter_edit.textChanged";

  var MISSING_FAULT = "missing";
  var NULL_FAULT = "null";
  var NOT_AN_OBJECT_FAULT = "not-an-object";
  var NOT_A_BAG_FAULT = "not-a-bag";
  var NOT_A_LIST_FAULT = "not-a-list";
  var SWAPPED_ALPHA_FAULT = "swapped-alpha";
  var REORDERED_KEY_FAULT = "reordered-key";
  var DISAGREES_FAULT = "disagrees";
  var UNKNOWN_ELEMENT_FAULT = "unknown-element";
  var UNKNOWN_ORDER_FAULT = "unknown-order";
  var SHORT_LIST_FAULT = "short-list";

  var ROW_AT = "row:";
  var CONTROL_AT = "control:";
  var PATH_SPLIT = ".";
  var EMPTY = "";

  var NO_BRIDGE = "the preload bridge is not present";

  var CHROME_CLASS = "acervator-fold-chrome";

  var DIV_TAG = "div";
  var SPAN_TAG = "span";
  var LABEL_TAG = "label";
  var SELECT_TAG = "select";
  var OPTION_TAG = "option";
  var INPUT_TAG = "input";
  var TEXT_TYPE = "text";
  var SEARCH_TYPE = "search";

  var CHROME_PART = "fold-chrome";
  var DESPAWN_ROWS_PART = "despawn-rows";
  var DESPAWN_ROW_PART = "despawn-row";
  var DESPAWN_LABEL_PART = "despawn-row-label";
  var DESPAWN_VALUE_PART = "despawn-row-value";
  var ROW_CONTROLS_PART = "row-controls";
  var ORDER_LABEL_PART = "order-label";
  var SORT_COMBO_PART = "sort-combo";
  var SORT_OPTION_PART = "sort-option";
  var FILTER_EDIT_PART = "filter-edit";
  var BORDER_PLAN_PART = "border-plan";
  var HIDDEN_ROW_PART = "hidden-row";
  var PIN_PART = "chrome-pin";
  var WARNING_PART = "chrome-warning";

  var PART_ATTR = "data-part";
  var KEY_ATTR = "data-key";
  var NAME_ATTR = "data-name";
  var INDEX_ATTR = "data-index";
  var ORDER_ATTR = "data-order";
  var CURRENT_ATTR = "data-current";
  var FILL_ATTR = "data-fill";
  var BORDER_ATTR = "data-border";
  var HIDDEN_ATTR = "data-hidden";
  var STRETCH_ATTR = "data-stretch";
  var CLEAR_ATTR = "data-clear-button";
  var ACTION_ATTR = "data-action";
  var STYLED_ATTR = "data-styled";
  var COUNT_ATTR = "data-count";
  var REBUILDS_ATTR = "data-rebuilds";
  var SPACING_ATTR = "data-spacing-set";
  var MARGINS_ATTR = "data-margins-set";
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

  var PX = "px";
  var FLEX = "flex";
  var ROW_DIRECTION = "row";
  var COLUMN_DIRECTION = "column";
  var CENTER = "center";

  var ZERO = Number(EMPTY);
  var STEP = Number(true);
  var SECOND = STEP + STEP;
  var THIRD = SECOND + STEP;
  var FOURTH = THIRD + STEP;

  var held = null;
  var chromeFaults = [];
  var loadFault = null;
  var asked = null;
  var roots = [];
  var lastPick = null;
  var lastType = null;

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

  function model() {
    return held === null ? null : held.model;
  }

  function elementName(name) {
    var found = objectField(model(), ELEMENT_NAMES);
    return owns(found, name) ? found[name] : undefined;
  }

  function rowLabel(name) {
    var found = objectField(model(), LABELS);
    return owns(found, name) ? found[name] : undefined;
  }

  function rows() {
    return listField(model(), ROWS);
  }

  // One despawn row found by its own label, never by where it sits.
  function rowNamed(name) {
    var wanted = rowLabel(name);
    var found;
    rows().forEach(function (row) {
      if (Array.isArray(row) && row.length && row[ZERO] === wanted) {
        found = row;
      }
    });
    return found;
  }

  function rowValue(name) {
    var row = rowNamed(name);
    return Array.isArray(row) && row.length > STEP ? row[STEP] : undefined;
  }

  function rowStyle(name) {
    var row = rowNamed(name);
    return Array.isArray(row) && row.length > SECOND ? row[SECOND] : undefined;
  }

  function rowTooltip(name) {
    var row = rowNamed(name);
    return Array.isArray(row) && row.length > THIRD ? row[THIRD] : undefined;
  }

  function controls() {
    return listField(model(), CONTROLS);
  }

  // One drawn element found by the name it carries in its own first place.
  function controlNamed(name) {
    var found;
    controls().forEach(function (one) {
      if (Array.isArray(one) && one.length && one[ZERO] === name) {
        found = one;
      }
    });
    return found;
  }

  function controlNames() {
    return controls().map(function (one) {
      return Array.isArray(one) && one.length ? one[ZERO] : undefined;
    });
  }

  function offeredOrders() {
    var found = objectField(model(), ORDERS);
    return Array.isArray(found[OFFERED]) ? found[OFFERED].slice() : [];
  }

  function sortOrder() {
    var found = model();
    return found === null ? undefined : found[SORT_ORDER];
  }

  function borderMap() {
    return objectField(objectField(model(), BORDER), BY_FILL);
  }

  function fillNames() {
    return Object.keys(borderMap());
  }

  function borderFor(fill) {
    var found = borderMap();
    return owns(found, fill) ? found[fill] : undefined;
  }

  function borderWidth() {
    var found = objectField(model(), BORDER);
    return found[BORDER_WIDTH];
  }

  function colourNamed(name) {
    var found = objectField(model(), COLORS);
    return owns(found, name) ? found[name] : undefined;
  }

  function shape(name) {
    var found = objectField(model(), CONTROLS_SHAPE);
    return owns(found, name) ? found[name] : undefined;
  }

  function textNamed(name) {
    var found = objectField(model(), TEXTS);
    return owns(found, name) ? found[name] : undefined;
  }

  function hiddenRows() {
    return listField(model(), HIDDEN).slice();
  }

  function pins() {
    return listField(model(), PINS).slice();
  }

  function warnings() {
    return listField(model(), WARNINGS).slice();
  }

  function deferred() {
    return listField(model(), DEFERRED).slice();
  }

  function calls() {
    return listField(model(), CALLS).slice();
  }

  function action(name) {
    var found = objectField(model(), ACTIONS);
    return owns(found, name) ? found[name] : undefined;
  }

  function checkFields(found) {
    DECLARED_FIELDS.forEach(function (name) {
      if (!owns(found, name)) {
        chromeFaults.push(fault(null, name, MISSING_FAULT, null));
      }
    });
    DECLARED_BAGS.forEach(function (name) {
      if (owns(found, name) && !isPlainObject(found[name])) {
        chromeFaults.push(fault(null, name, NOT_A_BAG_FAULT, kindOf(found[name])));
      }
    });
    DECLARED_LISTS.forEach(function (name) {
      if (owns(found, name) && !Array.isArray(found[name])) {
        chromeFaults.push(fault(null, name, NOT_A_LIST_FAULT, kindOf(found[name])));
      }
    });
  }

  function checkCounts(found) {
    if (listField(found, ROWS).length !== found[ROW_COUNT]) {
      chromeFaults.push(fault(null, ROW_COUNT, DISAGREES_FAULT, found[ROW_COUNT]));
    }
    if (listField(found, CONTROLS).length !== found[CONTROL_COUNT]) {
      chromeFaults.push(
        fault(null, CONTROL_COUNT, DISAGREES_FAULT, found[CONTROL_COUNT])
      );
    }
  }

  // Each drawn element must name itself with a name the payload declares.
  function checkElements(found) {
    var declared = listField(found, SCREEN_ELEMENTS);
    listField(found, CONTROLS).forEach(function (one, at) {
      var name = Array.isArray(one) && one.length ? one[ZERO] : undefined;
      if (declared.indexOf(name) < ZERO) {
        chromeFaults.push(
          fault(CONTROL_AT + String(at), CONTROLS, UNKNOWN_ELEMENT_FAULT, name)
        );
      }
    });
    var labels = objectField(found, LABELS);
    listField(found, ROWS).forEach(function (row, at) {
      var name = Array.isArray(row) && row.length ? row[ZERO] : undefined;
      if (name !== labels[TIMER_ROW_LABEL] && name !== labels[PREVIEW_ROW_LABEL]) {
        chromeFaults.push(fault(ROW_AT + String(at), ROWS, UNKNOWN_ELEMENT_FAULT, name));
      }
      if (Array.isArray(row) && row.length <= THIRD) {
        chromeFaults.push(fault(ROW_AT + String(at), ROWS, SHORT_LIST_FAULT, row.length));
      }
    });
  }

  function checkOrder(found) {
    var offered = objectField(found, ORDERS)[OFFERED];
    if (!Array.isArray(offered)) {
      chromeFaults.push(fault(null, ORDERS, NOT_A_LIST_FAULT, kindOf(offered)));
      return;
    }
    if (offered.indexOf(found[SORT_ORDER]) < ZERO) {
      chromeFaults.push(fault(null, SORT_ORDER, UNKNOWN_ORDER_FAULT, found[SORT_ORDER]));
    }
  }

  function checkColours(found) {
    var bag = objectField(found, COLORS);
    Object.keys(bag).forEach(function (name) {
      if (isSwappedAlpha(bag[name])) {
        chromeFaults.push(fault(null, COLORS, SWAPPED_ALPHA_FAULT, bag[name]));
      }
    });
    var borders = objectField(objectField(found, BORDER), BY_FILL);
    Object.keys(borders).forEach(function (fill) {
      if (isSwappedAlpha(fill) || isSwappedAlpha(borders[fill])) {
        chromeFaults.push(fault(null, BORDER, SWAPPED_ALPHA_FAULT, fill));
      }
    });
    listField(found, ROWS).forEach(function (row, at) {
      var sheet = Array.isArray(row) && row.length > SECOND ? row[SECOND] : undefined;
      declarations(sheet).forEach(function (one) {
        if (isSwappedAlpha(one.value)) {
          chromeFaults.push(
            fault(ROW_AT + String(at), ROWS, SWAPPED_ALPHA_FAULT, one.value)
          );
        }
      });
    });
  }

  function checkBagOrder(found) {
    DECLARED_BAGS.forEach(function (name) {
      Object.keys(objectField(found, name)).forEach(function (key) {
        if (isReorderedKey(key)) {
          chromeFaults.push(fault(null, name, REORDERED_KEY_FAULT, key));
        }
      });
    });
    Object.keys(objectField(objectField(found, BORDER), BY_FILL)).forEach(function (key) {
      if (isReorderedKey(key)) {
        chromeFaults.push(fault(null, BORDER, REORDERED_KEY_FAULT, key));
      }
    });
  }

  function element() {
    return global.React.createElement.apply(null, arguments);
  }

  // A bare colour carries no declaration, so it paints the text and nothing else.
  function valueStyle(sheet) {
    var written = declarations(sheet);
    if (!written.length) {
      return sheet ? { color: colour(sheet) } : {};
    }
    return styleOf(sheet);
  }

  function DespawnRow(props) {
    var name = props.name;
    var row = rowNamed(name);
    var rowProps = {
      className: CHROME_CLASS,
      style: { display: FLEX, flexDirection: ROW_DIRECTION, alignItems: CENTER }
    };
    rowProps[PART_ATTR] = DESPAWN_ROW_PART;
    rowProps[KEY_ATTR] = text(rowLabel(name));
    rowProps[NAME_ATTR] = text(elementName(props.element));
    rowProps[MATCHED_ATTR] = String(row !== undefined);
    var labelProps = { className: CHROME_CLASS, title: label(rowTooltip(name)) };
    labelProps[PART_ATTR] = DESPAWN_LABEL_PART;
    labelProps[KEY_ATTR] = text(rowLabel(name));
    var sheet = rowStyle(name);
    var valueProps = {
      className: CHROME_CLASS,
      style: valueStyle(sheet),
      title: label(rowTooltip(name))
    };
    valueProps[PART_ATTR] = DESPAWN_VALUE_PART;
    valueProps[NAME_ATTR] = text(elementName(props.element));
    valueProps[STYLED_ATTR] = String(Boolean(declarations(sheet).length));
    return element(
      DIV_TAG,
      rowProps,
      element(SPAN_TAG, labelProps, text(rowLabel(name))),
      element(SPAN_TAG, valueProps, text(rowValue(name)))
    );
  }

  function DespawnRows(props) {
    var rowsProps = {
      className: CHROME_CLASS,
      style: { display: FLEX, flexDirection: COLUMN_DIRECTION }
    };
    rowsProps[PART_ATTR] = DESPAWN_ROWS_PART;
    rowsProps[COUNT_ATTR] = text(props.model[ROW_COUNT]);
    return element(
      DIV_TAG,
      rowsProps,
      element(DespawnRow, {
        key: TIMER_ROW_LABEL,
        name: TIMER_ROW_LABEL,
        element: TIMER_ROW_NAME
      }),
      element(DespawnRow, {
        key: PREVIEW_ROW_LABEL,
        name: PREVIEW_ROW_LABEL,
        element: PREVIEW_ROW_NAME
      })
    );
  }

  function OrderLabel(props) {
    var one = controlNamed(elementName(ORDER_LABEL_NAME));
    var words = Array.isArray(one) && one.length > STEP ? one[STEP] : rowLabel(ORDER_LABEL_TEXT);
    var tip = Array.isArray(one) && one.length > SECOND ? one[SECOND] : undefined;
    var stretch = Array.isArray(one) && one.length > THIRD ? one[THIRD] : undefined;
    var labelProps = {
      className: CHROME_CLASS,
      style: { flexGrow: stretch, flexShrink: shape(NO_STRETCH) },
      title: label(tip),
      htmlFor: props.forId
    };
    labelProps[PART_ATTR] = ORDER_LABEL_PART;
    labelProps[NAME_ATTR] = text(elementName(ORDER_LABEL_NAME));
    labelProps[STRETCH_ATTR] = text(stretch);
    return element(LABEL_TAG, labelProps, text(words));
  }

  function SortCombo(props) {
    var one = controlNamed(elementName(SORT_COMBO_NAME));
    var offered = Array.isArray(one) && Array.isArray(one[STEP]) ? one[STEP] : offeredOrders();
    var current = Array.isArray(one) && one.length > SECOND ? one[SECOND] : sortOrder();
    var tip = Array.isArray(one) && one.length > THIRD ? one[THIRD] : undefined;
    var stretch = Array.isArray(one) && one.length > FOURTH ? one[FOURTH] : undefined;
    var comboProps = {
      id: props.id,
      className: CHROME_CLASS,
      style: { flexGrow: stretch, flexShrink: shape(NO_STRETCH) },
      title: label(tip),
      value: current === undefined ? EMPTY : current,
      onChange: function (event) {
        pickOrder(event.target.value);
        if (typeof props.onPick === "function") {
          props.onPick(event.target.value);
        }
      }
    };
    comboProps[PART_ATTR] = SORT_COMBO_PART;
    comboProps[NAME_ATTR] = text(elementName(SORT_COMBO_NAME));
    comboProps[CURRENT_ATTR] = text(current);
    comboProps[ACTION_ATTR] = label(action(SORT_ACTION));
    comboProps[COUNT_ATTR] = text(offered.length);
    comboProps[ARIA_LABEL] = label(rowLabel(ORDER_LABEL_TEXT));
    var drawn = offered.map(function (order, at) {
      var optionProps = { key: String(at), className: CHROME_CLASS, value: order };
      optionProps[PART_ATTR] = SORT_OPTION_PART;
      optionProps[ORDER_ATTR] = text(order);
      optionProps[INDEX_ATTR] = text(at);
      return element(OPTION_TAG, optionProps, text(order));
    });
    return element(SELECT_TAG, comboProps, drawn);
  }

  function FilterEdit(props) {
    var one = controlNamed(elementName(FILTER_EDIT_NAME));
    var hint = Array.isArray(one) && one.length > STEP ? one[STEP] : undefined;
    var tip = Array.isArray(one) && one.length > SECOND ? one[SECOND] : undefined;
    var clears = Array.isArray(one) && one.length > THIRD ? one[THIRD] : shape(CLEAR_BUTTON);
    var stretch = Array.isArray(one) && one.length > FOURTH ? one[FOURTH] : shape(FILTER_STRETCH);
    var editProps = {
      className: CHROME_CLASS,
      style: { flexGrow: stretch, minWidth: ZERO },
      title: label(tip),
      placeholder: label(hint),
      type: clears === true ? SEARCH_TYPE : TEXT_TYPE,
      value: props.typed === undefined ? EMPTY : props.typed,
      onChange: function (event) {
        typeFilter(event.target.value);
        if (typeof props.onType === "function") {
          props.onType(event.target.value);
        }
      }
    };
    editProps[PART_ATTR] = FILTER_EDIT_PART;
    editProps[NAME_ATTR] = text(elementName(FILTER_EDIT_NAME));
    editProps[CLEAR_ATTR] = text(clears);
    editProps[STRETCH_ATTR] = text(stretch);
    editProps[ACTION_ATTR] = label(action(FILTER_ACTION));
    editProps[ARIA_LABEL] = label(hint);
    return element(INPUT_TAG, editProps);
  }

  // RowControls is what the Fold Tranches tab draws above its table.
  function RowControls(props) {
    if (!isPlainObject(model())) {
      return null;
    }
    var boxProps = {
      className: CHROME_CLASS,
      style: {
        display: FLEX,
        flexDirection: ROW_DIRECTION,
        alignItems: CENTER,
        flexGrow: shape(NO_STRETCH)
      }
    };
    boxProps[PART_ATTR] = ROW_CONTROLS_PART;
    boxProps[COUNT_ATTR] = text(controls().length);
    boxProps[SPACING_ATTR] = text(shape(SPACING_SET));
    boxProps[MARGINS_ATTR] = text(shape(MARGINS_SET));
    return element(
      DIV_TAG,
      boxProps,
      element(OrderLabel, { key: ORDER_LABEL_PART, forId: SORT_COMBO_PART }),
      element(SortCombo, { key: SORT_COMBO_PART, id: SORT_COMBO_PART, onPick: props.onPick }),
      element(FilterEdit, { key: FILTER_EDIT_PART, typed: props.typed, onType: props.onType })
    );
  }

  function BorderPlan(props) {
    var fill = props.fill;
    var planProps = {
      className: CHROME_CLASS,
      style: {
        background: colour(fill),
        borderColor: colour(borderFor(fill)),
        borderWidth: length(borderWidth())
      }
    };
    planProps[PART_ATTR] = BORDER_PLAN_PART;
    planProps[FILL_ATTR] = text(fill);
    planProps[BORDER_ATTR] = text(borderFor(fill));
    return element(DIV_TAG, planProps, null);
  }

  function HiddenRow(props) {
    var markProps = { className: CHROME_CLASS };
    markProps[PART_ATTR] = HIDDEN_ROW_PART;
    markProps[INDEX_ATTR] = text(props.at);
    markProps[HIDDEN_ATTR] = text(props.hidden);
    return element(SPAN_TAG, markProps, null);
  }

  function ChromePin(props) {
    var one = Array.isArray(props.pin) ? props.pin : [];
    var pinProps = { className: CHROME_CLASS };
    pinProps[PART_ATTR] = PIN_PART;
    pinProps[NAME_ATTR] = text(one.length ? one[ZERO] : undefined);
    pinProps[INDEX_ATTR] = text(props.at);
    pinProps[MATCHED_ATTR] = String(
      one.length > SECOND &&
        JSON.stringify(one[STEP]) === JSON.stringify(one[SECOND])
    );
    return element(DIV_TAG, pinProps, null);
  }

  function ChromeWarning(props) {
    var one = Array.isArray(props.warning) ? props.warning : [];
    var warnProps = { className: CHROME_CLASS };
    warnProps[PART_ATTR] = WARNING_PART;
    warnProps[INDEX_ATTR] = text(props.at);
    warnProps[ORDER_ATTR] = text(one.length > STEP ? one[STEP] : undefined);
    return element(DIV_TAG, warnProps, text(one.length ? one[ZERO] : undefined));
  }

  // Chrome draws nothing for a payload that is not an object.
  function Chrome(props) {
    if (!isPlainObject(props.model)) {
      return null;
    }
    var found = props.model;
    var chromeProps = {
      id: props.id,
      className: CHROME_CLASS,
      style: { display: FLEX, flexDirection: COLUMN_DIRECTION, minWidth: ZERO }
    };
    chromeProps[PART_ATTR] = CHROME_PART;
    chromeProps[CURRENT_ATTR] = text(found[SORT_ORDER]);
    chromeProps[REBUILDS_ATTR] = text(found[REBUILD_CALLS]);
    var drawn = [
      element(DespawnRows, { key: DESPAWN_ROWS_PART, model: found }),
      element(RowControls, {
        key: ROW_CONTROLS_PART,
        typed: props.typed,
        onPick: props.onPick,
        onType: props.onType
      })
    ];
    fillNames().forEach(function (fill) {
      drawn.push(element(BorderPlan, { key: BORDER_PLAN_PART + fill, fill: fill }));
    });
    listField(found, HIDDEN).forEach(function (flag, at) {
      drawn.push(
        element(HiddenRow, { key: HIDDEN_ROW_PART + String(at), at: at, hidden: flag })
      );
    });
    listField(found, PINS).forEach(function (pin, at) {
      drawn.push(element(ChromePin, { key: PIN_PART + String(at), pin: pin, at: at }));
    });
    listField(found, WARNINGS).forEach(function (one, at) {
      drawn.push(
        element(ChromeWarning, { key: WARNING_PART + String(at), warning: one, at: at })
      );
    });
    return element(DIV_TAG, chromeProps, drawn);
  }

  // pickOrder records the order the combo answered with, refusing an unknown one.
  function pickOrder(order) {
    if (offeredOrders().indexOf(order) < ZERO) {
      lastPick = { order: order, accepted: false, action: action(SORT_ACTION) };
      return lastPick;
    }
    lastPick = { order: order, accepted: true, action: action(SORT_ACTION) };
    return lastPick;
  }

  function typeFilter(needle) {
    lastType = { needle: needle, action: action(FILTER_ACTION) };
    return lastType;
  }

  function picked() {
    return lastPick;
  }

  function typed() {
    return lastType;
  }

  function heldFieldCount(found) {
    return DECLARED_FIELDS.filter(function (name) {
      return owns(found, name);
    }).length;
  }

  // Counts the fields, rows, elements and orders declared against those held.
  function report() {
    var found = held.model;
    return {
      declared: {
        fields: DECLARED_FIELDS.length,
        rows: found[ROW_COUNT],
        controls: found[CONTROL_COUNT],
        elements: listField(found, SCREEN_ELEMENTS).length,
        orders: offeredOrders().length
      },
      held: {
        fields: heldFieldCount(found),
        rows: listField(found, ROWS).length,
        controls: listField(found, CONTROLS).length,
        elements: Object.keys(objectField(found, ELEMENT_NAMES)).length,
        orders: offeredOrders().length
      },
      faults: chromeFaults.slice()
    };
  }

  function setChrome(found) {
    if (!isPlainObject(found)) {
      held = null;
      chromeFaults = [fault(null, null, NOT_AN_OBJECT_FAULT, kindOf(found))];
      return { declared: null, held: null, faults: chromeFaults.slice() };
    }
    held = { model: found };
    chromeFaults = [];
    checkFields(found);
    checkCounts(found);
    checkElements(found);
    checkOrder(found);
    checkColours(found);
    checkBagOrder(found);
    return report();
  }

  // Asks METHOD once, clearing asked so a refused first ask is retried.
  function loadChrome(params) {
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
        setChrome(found);
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
    return chromeFaults.slice();
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
  function renderChrome(target, found) {
    if (isPlainObject(found)) {
      setChrome(found);
    }
    return draw(target, element(Chrome, { model: held === null ? null : held.model }));
  }

  function spaceIn(root, part) {
    if (!root || typeof root.getAttribute !== "function") {
      return null;
    }
    if (root.getAttribute(PART_ATTR) === part) {
      return root;
    }
    if (typeof root.querySelector !== "function") {
      return null;
    }
    return root.querySelector(SELECT_OPEN + PART_ATTR + SELECT_IS + part + SELECT_CLOSE);
  }

  function forget() {
    held = null;
    chromeFaults = [];
    loadFault = null;
    asked = null;
    lastPick = null;
    lastType = null;
  }

  global.acervatorSetFoldChrome = setChrome;
  global.acervatorLoadFoldChrome = loadChrome;
  global.acervatorFoldChrome = {
    method: METHOD,
    Chrome: Chrome,
    RowControls: RowControls,
    DespawnRows: DespawnRows,
    DespawnRow: DespawnRow,
    SortCombo: SortCombo,
    FilterEdit: FilterEdit,
    payload: payload,
    declaredNames: declaredNames,
    field: field,
    bag: bag,
    list: list,
    bagKeys: bagKeys,
    rows: rows,
    rowNamed: rowNamed,
    rowLabel: rowLabel,
    rowValue: rowValue,
    rowStyle: rowStyle,
    rowTooltip: rowTooltip,
    controls: controls,
    controlNamed: controlNamed,
    controlNames: controlNames,
    elementName: elementName,
    offeredOrders: offeredOrders,
    sortOrder: sortOrder,
    fillNames: fillNames,
    borderFor: borderFor,
    borderWidth: borderWidth,
    colourNamed: colourNamed,
    shape: shape,
    textNamed: textNamed,
    hiddenRows: hiddenRows,
    pins: pins,
    warnings: warnings,
    deferred: deferred,
    calls: calls,
    action: action,
    pickOrder: pickOrder,
    typeFilter: typeFilter,
    picked: picked,
    typed: typed,
    valueStyle: valueStyle,
    isSwappedAlpha: isSwappedAlpha,
    isReorderedKey: isReorderedKey,
    kinds: kinds,
    notPlainData: notPlainData,
    faults: faults,
    loadError: loadError,
    isLoaded: isLoaded,
    renderChrome: renderChrome,
    spaceIn: spaceIn,
    forget: forget
  };
})(window);
