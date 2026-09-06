// Draws the Market Inspector tab from the market_inspector_tab.state payload.
(function (global) {
  "use strict";

  var METHOD = "market_inspector_tab.state";

  var ACCESSIBLE_NAME = "accessible_name";
  var ACTIONS = "actions";
  var BUS_TOPICS = "bus_topics";
  var CALL_NAMES = "call_names";
  var CALLS = "calls";
  var DEFAULTS = "defaults";
  var DELEGATE = "delegate";
  var DELEGATED = "delegated";
  var DETAIL = "detail";
  var ERROR_TEXT = "error_text";
  var ERROR_TYPE = "error_type";
  var ERROR_TYPES = "error_types";
  var FALLBACK = "fallback";
  var LOGGER = "logger";
  var MESSAGE = "message";
  var ORDER = "order";
  var STYLE_SHEET = "style_sheet";
  var TEXTS = "texts";
  var TIMER_DELAYS_MS = "timer_delays_ms";
  var TIMERS = "timers";
  var VIEW = "view";
  var WARNINGS = "warnings";
  var WORD_WRAP = "word_wrap";

  // DECLARED_FIELDS lists every top-level field of the payload.
  var DECLARED_FIELDS = [
    ACCESSIBLE_NAME,
    ACTIONS,
    BUS_TOPICS,
    CALL_NAMES,
    CALLS,
    DEFAULTS,
    DELEGATE,
    DELEGATED,
    DETAIL,
    ERROR_TEXT,
    ERROR_TYPE,
    ERROR_TYPES,
    FALLBACK,
    LOGGER,
    MESSAGE,
    ORDER,
    STYLE_SHEET,
    TEXTS,
    TIMER_DELAYS_MS,
    TIMERS,
    VIEW,
    WARNINGS,
    WORD_WRAP
  ];

  var BOT_ATTRIBUTE = "bot_attribute";
  var COLOR = "color";
  var DETAIL_FORMAT = "detail_format";
  var ERROR_SEPARATOR = "error_separator";
  var FUNCTION_FIELD = "function";
  var HEADLINE = "headline";
  var HEADLINE_BREAKS = "headline_breaks";
  var HEADLINE_TEXT = "headline_text";
  var HEADLINE_WEIGHT = "headline_weight";
  var LABEL_CLASS = "label_class";
  var MARGINS_SET = "margins_set";
  var MODULE_FIELD = "module";
  var NAME = "name";
  var NO_MESSAGE = "no_message";
  var NO_STYLE = "no_style";
  var NO_VIEW = "no_view";
  var NO_WORD_WRAP = "no_word_wrap";
  var PADDING_PX = "padding_px";
  var SPACING_SET = "spacing_set";
  // STRETCH is the key whose value names the spacer inside `order`.
  var STRETCH = "stretch";
  var STYLE_FORMAT = "style_format";
  var TEXT_FORMAT = "text_format";
  var WARNING_FORMAT = "warning_format";

  var DELEGATE_FIELDS = [BOT_ATTRIBUTE, FUNCTION_FIELD, MODULE_FIELD];
  var FALLBACK_FIELDS = [
    COLOR,
    DETAIL_FORMAT,
    ERROR_SEPARATOR,
    HEADLINE,
    HEADLINE_BREAKS,
    HEADLINE_TEXT,
    HEADLINE_WEIGHT,
    LABEL_CLASS,
    MARGINS_SET,
    PADDING_PX,
    SPACING_SET,
    STRETCH,
    STYLE_FORMAT,
    TEXT_FORMAT,
    WORD_WRAP
  ];
  var LOGGER_FIELDS = [NAME, WARNING_FORMAT];
  var TEXTS_FIELDS = [NO_MESSAGE, NO_STYLE];
  var DEFAULTS_FIELDS = [ERROR_TYPE, NO_VIEW, NO_WORD_WRAP];

  var BAG_FIELDS = {};
  BAG_FIELDS[DELEGATE] = DELEGATE_FIELDS;
  BAG_FIELDS[FALLBACK] = FALLBACK_FIELDS;
  BAG_FIELDS[LOGGER] = LOGGER_FIELDS;
  BAG_FIELDS[TEXTS] = TEXTS_FIELDS;
  BAG_FIELDS[DEFAULTS] = DEFAULTS_FIELDS;

  var MISSING_FAULT = "missing";
  var NULL_FAULT = "null";
  var NOT_AN_OBJECT_FAULT = "not-an-object";
  var WRONG_TYPE_FAULT = "wrong-type";
  var MARKUP_FAULT = "markup";
  var NULL_KIND = "null";
  var OBJECT_KIND = "object";
  var NO_BRIDGE = "the preload bridge is not present";

  // MARKUP_OPEN starts a tag a rich-text label would read as formatting.
  var MARKUP_OPEN = "<";

  var EMPTY = "";
  var NEWLINE = "\n";
  var PATH_SPLIT = ".";
  var PX = "px";
  var VAR_OPEN = "var(--";
  var VAR_SPLIT = ", ";
  var VAR_CLOSE = ")";
  var CALC_OPEN = "calc(";
  var PX_FACTOR = " * 1px)";
  var FLEX = "flex";
  var FLEX_NONE = "none";
  var AUTO = "auto";
  var COLUMN = "column";
  var FULL = "100%";
  var PRE = "pre";
  var PRE_WRAP = "pre-wrap";
  var DIV_TAG = "div";
  var SPAN_TAG = "span";
  var STRONG_TAG = "strong";

  // Only these token groups carry a value a CSS length may borrow.
  var LENGTH_GROUPS = ["spacing", "radii", "target_sizes", "table_columns", "focus"];

  var PART_ATTR = "data-part";
  var LABEL_ATTR = "aria-label";

  var TAB_PART = "tab";
  var VIEW_PART = "view";
  var FALLBACK_PART = "fallback";
  var MESSAGE_PART = "message";
  var HEADLINE_PART = "headline";
  var DETAIL_PART = "detail";
  var SPACER_PART = "spacer";

  var TAB_CLASS = "acervator-market-inspector-tab";

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

  function objectField(model, field) {
    return isPlainObject(model) && isPlainObject(model[field]) ? model[field] : {};
  }

  function listField(model, field) {
    return isPlainObject(model) && Array.isArray(model[field]) ? model[field] : [];
  }

  function copyOf(value) {
    return JSON.parse(JSON.stringify(value));
  }

  function kindOf(value) {
    if (value === null) {
      return NULL_KIND;
    }
    return Array.isArray(value) ? OBJECT_KIND : typeof value;
  }

  function text(value) {
    return value === null || value === undefined ? undefined : String(value);
  }

  // An accessible name the surface left empty stays off the element.
  function label(value) {
    return typeof value === "string" && value.length ? value : undefined;
  }

  function fault(where, field, kind, detail) {
    return { where: where, field: field, fault: kind, detail: detail };
  }

  // `shared_widgets.js` owns the one-carrier rule that names a token.
  function variableFor(value) {
    var api = global.acervatorWidgets;
    if (!api || typeof api.variableFor !== "function") {
      return undefined;
    }
    return api.variableFor(value);
  }

  // Whether `name` sits in one of `groups`, so its meaning matches.
  function inGroups(name, groups) {
    var api = global.acervatorTokens;
    if (!api || typeof api.group !== "function") {
      return false;
    }
    var matched = groups.filter(function (one) {
      return owns(api.group(one), name);
    });
    return Boolean(matched.length);
  }

  // The token name for `value`, only from a group meaning the same thing.
  function variableInGroups(value, groups) {
    var name = variableFor(value);
    if (name === undefined || !inGroups(name, groups)) {
      return undefined;
    }
    return name;
  }

  // A token holds a bare number, so `calc` scales it to a CSS length.
  function length(value) {
    if (value === null || value === undefined) {
      return undefined;
    }
    var name = variableInGroups(value, LENGTH_GROUPS);
    if (name === undefined) {
      return String(value) + PX;
    }
    return (
      CALC_OPEN + VAR_OPEN + name + VAR_SPLIT + String(value) + VAR_CLOSE + PX_FACTOR
    );
  }

  // A colour painted through the one token that carries it.
  function colour(value) {
    var name = variableFor(value);
    if (name === undefined) {
      return text(value);
    }
    return VAR_OPEN + name + VAR_SPLIT + String(value) + VAR_CLOSE;
  }

  // `header_strip.js` owns the sheet parser and the camel-case rule.
  function declarations(sheet) {
    var api = global.acervatorHeader;
    if (!api || typeof api.declarations !== "function") {
      return [];
    }
    return api.declarations(sheet);
  }

  function stateRules(sheet) {
    var api = global.acervatorHeader;
    if (!api || typeof api.stateRules !== "function") {
      return [];
    }
    return api.stateRules(sheet);
  }

  function styleOf(sheet) {
    var api = global.acervatorHeader;
    if (!api || typeof api.styleOf !== "function") {
      return {};
    }
    return api.styleOf(sheet);
  }

  // Qt wraps a label at word ends, and clips it to one flow when it does not.
  function wrapMode(wraps) {
    return wraps ? PRE_WRAP : PRE;
  }

  function messageStyle(model) {
    var style = styleOf(model[STYLE_SHEET]);
    style.whiteSpace = wrapMode(model[WORD_WRAP]);
    style.flex = FLEX_NONE;
    return style;
  }

  function headlineStyle(model) {
    return { fontWeight: text(objectField(model, FALLBACK)[HEADLINE_WEIGHT]) };
  }

  // The blank run the headline's trailing breaks leave above the failure.
  function breakText(count) {
    try {
      return NEWLINE.repeat(count);
    } catch (refused) {
      return EMPTY;
    }
  }

  function paddingLength(model) {
    return length(objectField(model, FALLBACK)[PADDING_PX]);
  }

  function element() {
    return global.React.createElement.apply(null, arguments);
  }

  // The analyzer's per-bot view mounts here; this file draws none of it.
  function ViewSlot() {
    var props = { style: { flex: AUTO } };
    props[PART_ATTR] = VIEW_PART;
    return element(DIV_TAG, props);
  }

  // The failure line, drawn as text so a tag in it reaches the screen whole.
  function Message(props) {
    var model = props.model;
    var fallback = objectField(model, FALLBACK);
    var messageProps = { style: messageStyle(model) };
    messageProps[PART_ATTR] = MESSAGE_PART;
    var headlineProps = { style: headlineStyle(model) };
    headlineProps[PART_ATTR] = HEADLINE_PART;
    var detailProps = {};
    detailProps[PART_ATTR] = DETAIL_PART;
    return element(
      DIV_TAG,
      messageProps,
      element(STRONG_TAG, headlineProps, text(fallback[HEADLINE_TEXT])),
      breakText(fallback[HEADLINE_BREAKS]),
      element(SPAN_TAG, detailProps, text(model[DETAIL]))
    );
  }

  function Spacer() {
    var props = { style: { flex: AUTO } };
    props[PART_ATTR] = SPACER_PART;
    return element(DIV_TAG, props);
  }

  // Each `order` entry drawn under the name the surface gave it.
  function orderedChild(model, name, at) {
    var fallback = objectField(model, FALLBACK);
    var key = String(at);
    if (name === fallback[LABEL_CLASS]) {
      return element(Message, { key: key, model: model });
    }
    if (name === fallback[STRETCH]) {
      return element(Spacer, { key: key });
    }
    return null;
  }

  function Fallback(props) {
    var model = props.model;
    var fallbackProps = {
      style: { display: FLEX, flexDirection: COLUMN, flex: AUTO }
    };
    fallbackProps[PART_ATTR] = FALLBACK_PART;
    return element(
      DIV_TAG,
      fallbackProps,
      listField(model, ORDER).map(function (name, at) {
        return orderedChild(model, name, at);
      })
    );
  }

  function Tab(props) {
    var model = isPlainObject(props.model) ? props.model : {};
    var tabProps = {
      className: TAB_CLASS,
      style: { display: FLEX, flexDirection: COLUMN, height: FULL }
    };
    tabProps[PART_ATTR] = TAB_PART;
    tabProps[LABEL_ATTR] = label(model[ACCESSIBLE_NAME]);
    if (model[DELEGATED] === true) {
      return element(DIV_TAG, tabProps, element(ViewSlot, null));
    }
    return element(DIV_TAG, tabProps, element(Fallback, { model: model }));
  }

  function checkFields(model) {
    DECLARED_FIELDS.forEach(function (field) {
      if (!owns(model, field)) {
        tabFaults.push(fault(null, field, MISSING_FAULT, null));
        return;
      }
      if (model[field] === null && field !== VIEW) {
        tabFaults.push(fault(null, field, NULL_FAULT, null));
      }
    });
  }

  function checkBags(model) {
    Object.keys(BAG_FIELDS).forEach(function (where) {
      var bag = objectField(model, where);
      BAG_FIELDS[where].forEach(function (field) {
        if (!owns(bag, field)) {
          tabFaults.push(fault(where, field, MISSING_FAULT, null));
          return;
        }
        if (bag[field] === null && field !== NO_VIEW) {
          tabFaults.push(fault(where, field, NULL_FAULT, null));
        }
      });
    });
  }

  // A wrong type is named only where the surface publishes a default of
  // the same meaning to hold it against.
  function checkTypeAgainst(field, carried, against) {
    if (against === null || against === undefined) {
      return;
    }
    if (carried === undefined) {
      return;
    }
    if (kindOf(carried) !== kindOf(against)) {
      tabFaults.push(fault(null, field, WRONG_TYPE_FAULT, kindOf(carried)));
    }
  }

  function checkTypes(model) {
    var texts = objectField(model, TEXTS);
    var defaults = objectField(model, DEFAULTS);
    checkTypeAgainst(ACCESSIBLE_NAME, model[ACCESSIBLE_NAME], texts[NO_MESSAGE]);
    checkTypeAgainst(MESSAGE, model[MESSAGE], texts[NO_MESSAGE]);
    checkTypeAgainst(DETAIL, model[DETAIL], texts[NO_MESSAGE]);
    checkTypeAgainst(ERROR_TEXT, model[ERROR_TEXT], texts[NO_MESSAGE]);
    checkTypeAgainst(STYLE_SHEET, model[STYLE_SHEET], texts[NO_STYLE]);
    checkTypeAgainst(ERROR_TYPE, model[ERROR_TYPE], defaults[ERROR_TYPE]);
    checkTypeAgainst(WORD_WRAP, model[WORD_WRAP], defaults[NO_WORD_WRAP]);
  }

  // Names an error text carrying a tag, which this file draws as words.
  function checkMarkup(model) {
    var carried = model[ERROR_TEXT];
    if (typeof carried === "string" && carried.includes(MARKUP_OPEN)) {
      tabFaults.push(fault(null, ERROR_TEXT, MARKUP_FAULT, MARKUP_OPEN));
    }
  }

  function heldFieldCount() {
    return DECLARED_FIELDS.filter(function (field) {
      return held !== null && owns(held.model, field);
    }).length;
  }

  // Every nested field as one `bag.field` path, so the two counts pair up.
  function nestedPaths() {
    var found = [];
    Object.keys(BAG_FIELDS).forEach(function (where) {
      BAG_FIELDS[where].forEach(function (name) {
        found.push({ where: where, field: name });
      });
    });
    return found;
  }

  function heldNestedPaths(model) {
    return nestedPaths().filter(function (one) {
      return owns(objectField(model, one.where), one.field);
    });
  }

  // Counts the fields, the nested fields and the screen parts apart.
  function report() {
    var model = held.model;
    return {
      declared: {
        fields: DECLARED_FIELDS.length,
        nested: nestedPaths().length,
        parts: listField(model, CALL_NAMES).length
      },
      held: {
        fields: heldFieldCount(),
        nested: heldNestedPaths(model).length,
        parts: listField(model, ORDER).length
      },
      faults: tabFaults.slice()
    };
  }

  function setTab(model) {
    if (!isPlainObject(model)) {
      held = null;
      tabFaults = [fault(null, null, NOT_AN_OBJECT_FAULT, kindOf(model))];
      return { declared: null, held: null, faults: tabFaults.slice() };
    }
    held = { model: model };
    tabFaults = [];
    checkFields(model);
    checkBags(model);
    checkTypes(model);
    checkMarkup(model);
    return report();
  }

  // loadTab asks METHOD once, clearing asked so a refusal retries.
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
      .then(function (model) {
        loadFault = null;
        setTab(model);
        return model;
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

  function nestedNames(where) {
    return owns(BAG_FIELDS, where) ? BAG_FIELDS[where].slice() : [];
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

  function accessibleName() {
    return field(ACCESSIBLE_NAME);
  }

  function delegated() {
    return field(DELEGATED);
  }

  function viewHeld() {
    return field(VIEW);
  }

  function message() {
    return field(MESSAGE);
  }

  function detail() {
    return field(DETAIL);
  }

  function errorType() {
    return field(ERROR_TYPE);
  }

  function errorText() {
    return field(ERROR_TEXT);
  }

  function wordWrap() {
    return field(WORD_WRAP);
  }

  function styleSheet() {
    return field(STYLE_SHEET);
  }

  function order() {
    return list(ORDER);
  }

  function warnings() {
    return list(WARNINGS);
  }

  function calls() {
    return list(CALLS);
  }

  function callNames() {
    return list(CALL_NAMES);
  }

  function errorTypes() {
    return list(ERROR_TYPES);
  }

  function busTopics() {
    return list(BUS_TOPICS);
  }

  function timerDelays() {
    return list(TIMER_DELAYS_MS);
  }

  function actions() {
    return bag(ACTIONS);
  }

  function timers() {
    return bag(TIMERS);
  }

  // The JavaScript type each value arrived as, by dotted path.
  function kinds() {
    var found = {};
    if (held === null) {
      return found;
    }
    var model = held.model;
    Object.keys(model).forEach(function (name) {
      found[name] = kindOf(model[name]);
      if (!isPlainObject(model[name])) {
        return;
      }
      Object.keys(model[name]).forEach(function (inner) {
        found[name + PATH_SPLIT + inner] = kindOf(model[name][inner]);
      });
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

  // `flushSync` makes the document current before `draw` returns.
  function draw(target, node) {
    var root = rootFor(target);
    global.ReactDOM.flushSync(function () {
      root.render(node);
    });
    return target;
  }

  function renderTab(target, model) {
    var drawn = model;
    if (!isPlainObject(drawn)) {
      drawn = held === null ? null : held.model;
    }
    return draw(target, element(Tab, { model: drawn }));
  }

  function forget() {
    held = null;
    tabFaults = [];
    loadFault = null;
    asked = null;
  }

  // The shell draws this tab by its module name; the host reads that name
  // off the script tag running now, so it is written down nowhere.
  if (global.acervatorPanelHost) {
    global.acervatorPanelHost.register({
      render: renderTab,
      load: loadTab,
      loadError: loadError
    });
  }

  global.acervatorSetInspectorTab = setTab;
  global.acervatorLoadInspectorTab = loadTab;
  global.acervatorInspectorTab = {
    method: METHOD,
    Tab: Tab,
    Fallback: Fallback,
    Message: Message,
    Spacer: Spacer,
    ViewSlot: ViewSlot,
    payload: payload,
    declaredNames: declaredNames,
    nestedNames: nestedNames,
    field: field,
    bag: bag,
    accessibleName: accessibleName,
    delegated: delegated,
    viewHeld: viewHeld,
    message: message,
    detail: detail,
    errorType: errorType,
    errorText: errorText,
    wordWrap: wordWrap,
    styleSheet: styleSheet,
    order: order,
    warnings: warnings,
    calls: calls,
    callNames: callNames,
    errorTypes: errorTypes,
    busTopics: busTopics,
    timerDelays: timerDelays,
    actions: actions,
    timers: timers,
    messageStyle: messageStyle,
    headlineStyle: headlineStyle,
    paddingLength: paddingLength,
    wrapMode: wrapMode,
    breakText: breakText,
    styleOf: styleOf,
    declarations: declarations,
    stateRules: stateRules,
    variableFor: variableFor,
    variableInGroups: variableInGroups,
    colour: colour,
    length: length,
    kinds: kinds,
    faults: faults,
    loadError: loadError,
    isLoaded: isLoaded,
    renderTab: renderTab,
    forget: forget
  };
})(window);
