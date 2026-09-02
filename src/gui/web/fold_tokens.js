// Draws the Fold Tranches token panel from the fold_tokens.state payload.
(function (global) {
  "use strict";

  var METHOD = "fold_tokens.state";

  var ACTIONS = "actions";
  var BUS_EMITS = "bus_emits";
  var BUS_TOPICS = "bus_topics";
  var CALLS = "calls";
  var METHOD_FIELD = "method";
  var RAN = "ran";
  var REFUSED = "refused";
  var STEP_NAMES = "step_names";
  var TIMERS = "timers";
  var TIMER_DELAYS_MS = "timer_delays_ms";
  var TOKENS = "tokens";

  // Every top-level name the fold_tokens.state payload carries.
  var DECLARED_FIELDS = [
    ACTIONS,
    BUS_EMITS,
    BUS_TOPICS,
    CALLS,
    METHOD_FIELD,
    RAN,
    REFUSED,
    STEP_NAMES,
    TIMER_DELAYS_MS,
    TIMERS,
    TOKENS
  ];

  var DECLARED_BAGS = [ACTIONS, TIMERS, TOKENS];
  var DECLARED_LISTS = [BUS_EMITS, BUS_TOPICS, CALLS, STEP_NAMES, TIMER_DELAYS_MS];

  // Token names this module reads; each names a value, never spells one.
  var BORDER_BY_FILL = "TRANCHE_ROW_BORDER_BY_BG";
  var SORT_ORDERS = "FOLD_SORT_ORDERS";
  var COLUMN_TIPS = "FOLD_COLUMN_TOOLTIPS";
  var ARBITER_LABELS = "ARBITER_LABELS";
  var ARBITER_PARENT = "ARBITER_PARENT";
  var ARBITER_SIBLING = "ARBITER_SIBLING";
  var SOURCE_TOOLTIPS = "FOLD_SOURCE_TOOLTIPS";
  var STEP_NAMES_TOKEN = "STEP_NAMES";
  var ROW_HEIGHT = "TRANCHE_ROW_HEIGHT_PX";
  var ROW_BORDER_WIDTH = "TRANCHE_ROW_BORDER_PX";
  var VISIBLE_ROWS = "TRANCHE_TABLE_VISIBLE_ROWS";

  // A token name ending with HEX_SUFFIX carries a colour.
  var HEX_SUFFIX = "_HEX";

  var REFUSAL_INDEX = "index";
  var REFUSAL_STEP = "step";
  var REFUSAL_TYPE = "refusal_type";
  var REFUSAL_FIELDS = [REFUSAL_INDEX, REFUSAL_STEP, REFUSAL_TYPE];

  var MISSING_FAULT = "missing";
  var NULL_FAULT = "null";
  var NOT_AN_OBJECT_FAULT = "not-an-object";
  var NOT_A_BAG_FAULT = "not-a-bag";
  var NOT_A_LIST_FAULT = "not-a-list";
  var SWAPPED_ALPHA_FAULT = "swapped-alpha";
  var REORDERED_KEY_FAULT = "reordered-key";
  var DISAGREES_FAULT = "disagrees";
  var UNKNOWN_STEP_FAULT = "unknown-step";

  var TOKEN_AT = "token:";
  var CALL_AT = "call:";
  var PATH_SPLIT = ".";
  var EMPTY = "";

  var NO_BRIDGE = "the preload bridge is not present";

  var PANEL_CLASS = "acervator-fold-tokens";

  var DIV_TAG = "div";
  var SPAN_TAG = "span";

  var PANEL_PART = "fold-tokens";
  var FILL_PART = "token-fill";
  var ORDER_PART = "token-order";
  var COLUMN_TIP_PART = "token-column-tip";
  var ARBITER_PART = "token-arbiter";
  var SOURCE_PART = "token-source";
  var STEP_PART = "token-step";
  var REFUSAL_PART = "token-refusal";

  var PART_ATTR = "data-part";
  var FILL_ATTR = "data-fill";
  var BORDER_ATTR = "data-border";
  var ORDER_ATTR = "data-order";
  var COLUMN_ATTR = "data-column";
  var VALUE_ATTR = "data-value";
  var LABEL_ATTR = "data-label";
  var STEP_ATTR = "data-step";
  var INDEX_ATTR = "data-index";
  var KIND_ATTR = "data-kind";
  var RAN_ATTR = "data-ran";
  var COUNT_ATTR = "data-count";
  var VISIBLE_ROWS_ATTR = "data-visible-rows";
  var TYPE_ATTR = "data-refusal-type";
  var ARIA_LABEL = "aria-label";

  // HASH_ESCAPE decodes to the mark every colour opens with.
  var HASH_ESCAPE = "%23";
  var HEX_MARK = decodeURIComponent(HASH_ESCAPE);
  // SWAPPED_LENGTH is the width of a colour written with eight hex digits.
  var SWAPPED_LENGTH = HEX_MARK.length + "aabbccdd".length;

  // A key made only of digits is the key a browser moves to the front.
  var DIGITS = "0123456789";

  var PX = "px";
  var SOLID = "solid";
  var BLOCK = "block";

  var ZERO = Number(EMPTY);
  var STEP = Number(true);

  var held = null;
  var tokenFaults = [];
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

  // Returns String(value), or undefined for null and undefined.
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

  // acervatorCells owns the rule that one carrier name resolves a colour.
  function colour(value) {
    var api = global.acervatorCells;
    if (!api || typeof api.colour !== "function") {
      return text(value);
    }
    return api.colour(value);
  }

  function tokenBag() {
    return held === null ? {} : objectField(held.model, TOKENS);
  }

  function token(name) {
    var found = tokenBag();
    return owns(found, name) ? found[name] : undefined;
  }

  function tokenNames() {
    return Object.keys(tokenBag());
  }

  // Every token naming a colour, plus both sides of the fill-to-border map.
  function colourTokens() {
    var found = [];
    var bag = tokenBag();
    Object.keys(bag).forEach(function (name) {
      if (name.slice(ZERO - HEX_SUFFIX.length) === HEX_SUFFIX) {
        found.push({ name: name, value: bag[name] });
      }
    });
    var borders = borderMap();
    Object.keys(borders).forEach(function (fill) {
      found.push({ name: BORDER_BY_FILL, value: fill });
      found.push({ name: BORDER_BY_FILL, value: borders[fill] });
    });
    return found;
  }

  function borderMap() {
    var found = token(BORDER_BY_FILL);
    return isPlainObject(found) ? found : {};
  }

  // The fill order as the payload wrote it, so no check reads a bag by position.
  function fillNames() {
    return Object.keys(borderMap());
  }

  function borderFor(fill) {
    var found = borderMap();
    return owns(found, fill) ? found[fill] : undefined;
  }

  function orders() {
    var found = token(SORT_ORDERS);
    return Array.isArray(found) ? found.slice() : [];
  }

  function columnTips() {
    var found = token(COLUMN_TIPS);
    return Array.isArray(found) ? found.slice() : [];
  }

  function arbiterValues() {
    return [token(ARBITER_PARENT), token(ARBITER_SIBLING)];
  }

  function arbiterLabel(value) {
    var labels = token(ARBITER_LABELS);
    if (!isPlainObject(labels)) {
      return undefined;
    }
    var parent = token(ARBITER_PARENT);
    var name = value === parent ? parent : token(ARBITER_SIBLING);
    return owns(labels, name) ? labels[name] : undefined;
  }

  function sourceNames() {
    var found = token(SOURCE_TOOLTIPS);
    return isPlainObject(found) ? Object.keys(found) : [];
  }

  function sourceTooltip(name) {
    var found = token(SOURCE_TOOLTIPS);
    return isPlainObject(found) && owns(found, name) ? found[name] : undefined;
  }

  function stepNames() {
    return held === null ? [] : listField(held.model, STEP_NAMES).slice();
  }

  function calls() {
    return held === null ? [] : listField(held.model, CALLS).slice();
  }

  // Each driven step by its own name, so a check never reads a call by position.
  function answers() {
    var found = {};
    calls().forEach(function (call) {
      if (Array.isArray(call) && call.length) {
        found[String(call[ZERO])] = call[STEP];
      }
    });
    return found;
  }

  function refusal() {
    return held === null ? null : held.model[REFUSED];
  }

  function checkFields(model) {
    DECLARED_FIELDS.forEach(function (name) {
      if (!owns(model, name)) {
        tokenFaults.push(fault(null, name, MISSING_FAULT, null));
      }
    });
    DECLARED_BAGS.forEach(function (name) {
      if (owns(model, name) && !isPlainObject(model[name])) {
        tokenFaults.push(fault(null, name, NOT_A_BAG_FAULT, kindOf(model[name])));
      }
    });
    DECLARED_LISTS.forEach(function (name) {
      if (owns(model, name) && !Array.isArray(model[name])) {
        tokenFaults.push(fault(null, name, NOT_A_LIST_FAULT, kindOf(model[name])));
      }
    });
    if (owns(model, METHOD_FIELD) && model[METHOD_FIELD] !== METHOD) {
      tokenFaults.push(
        fault(null, METHOD_FIELD, DISAGREES_FAULT, model[METHOD_FIELD])
      );
    }
  }

  function checkColours() {
    colourTokens().forEach(function (one) {
      if (isSwappedAlpha(one.value)) {
        tokenFaults.push(fault(TOKEN_AT + one.name, TOKENS, SWAPPED_ALPHA_FAULT, one.value));
      }
    });
  }

  // A bag whose key a browser moves loses the order the payload wrote it in.
  function checkBagOrder(model) {
    DECLARED_BAGS.forEach(function (name) {
      Object.keys(objectField(model, name)).forEach(function (key) {
        if (isReorderedKey(key)) {
          tokenFaults.push(fault(null, name, REORDERED_KEY_FAULT, key));
        }
      });
    });
    Object.keys(borderMap()).forEach(function (key) {
      if (isReorderedKey(key)) {
        tokenFaults.push(fault(TOKEN_AT + BORDER_BY_FILL, TOKENS, REORDERED_KEY_FAULT, key));
      }
    });
  }

  // The steps the payload names must be the steps the token bag declares.
  function checkSteps(model) {
    var declared = Array.isArray(token(STEP_NAMES_TOKEN)) ? token(STEP_NAMES_TOKEN) : [];
    var named = listField(model, STEP_NAMES);
    if (declared.length !== named.length) {
      tokenFaults.push(fault(null, STEP_NAMES, DISAGREES_FAULT, named.length));
    }
    listField(model, CALLS).forEach(function (call, at) {
      var name = Array.isArray(call) && call.length ? String(call[ZERO]) : undefined;
      if (named.indexOf(name) < ZERO) {
        tokenFaults.push(fault(CALL_AT + String(at), CALLS, UNKNOWN_STEP_FAULT, name));
      }
    });
    if (listField(model, CALLS).length !== model[RAN]) {
      tokenFaults.push(fault(null, RAN, DISAGREES_FAULT, model[RAN]));
    }
  }

  function checkRefusal(model) {
    var found = model[REFUSED];
    if (found === null || found === undefined) {
      return;
    }
    if (!isPlainObject(found)) {
      tokenFaults.push(fault(null, REFUSED, NOT_AN_OBJECT_FAULT, kindOf(found)));
      return;
    }
    REFUSAL_FIELDS.forEach(function (name) {
      if (!owns(found, name)) {
        tokenFaults.push(fault(null, REFUSED, MISSING_FAULT, name));
      }
    });
  }

  function element() {
    return global.React.createElement.apply(null, arguments);
  }

  function FillSwatch(props) {
    var fill = props.fill;
    var border = borderFor(fill);
    var style = {
      display: BLOCK,
      background: colour(fill),
      borderStyle: SOLID,
      borderWidth: length(token(ROW_BORDER_WIDTH)),
      borderColor: colour(border),
      height: length(token(ROW_HEIGHT))
    };
    var swatchProps = { className: PANEL_CLASS, style: style };
    swatchProps[PART_ATTR] = FILL_PART;
    swatchProps[FILL_ATTR] = text(fill);
    swatchProps[BORDER_ATTR] = text(border);
    swatchProps[ARIA_LABEL] = label(fill);
    return element(DIV_TAG, swatchProps, null);
  }

  function OrderName(props) {
    var orderProps = { className: PANEL_CLASS };
    orderProps[PART_ATTR] = ORDER_PART;
    orderProps[ORDER_ATTR] = text(props.order);
    orderProps[INDEX_ATTR] = text(props.at);
    return element(SPAN_TAG, orderProps, text(props.order));
  }

  function ColumnTip(props) {
    var tipProps = { className: PANEL_CLASS, title: label(props.tip) };
    tipProps[PART_ATTR] = COLUMN_TIP_PART;
    tipProps[COLUMN_ATTR] = text(props.at);
    return element(SPAN_TAG, tipProps, text(props.tip));
  }

  function ArbiterWord(props) {
    var word = arbiterLabel(props.value);
    var wordProps = { className: PANEL_CLASS };
    wordProps[PART_ATTR] = ARBITER_PART;
    wordProps[VALUE_ATTR] = text(props.value);
    wordProps[LABEL_ATTR] = text(word);
    return element(SPAN_TAG, wordProps, text(word));
  }

  function SourceTip(props) {
    var tipProps = { className: PANEL_CLASS, title: label(sourceTooltip(props.name)) };
    tipProps[PART_ATTR] = SOURCE_PART;
    tipProps[LABEL_ATTR] = text(props.name);
    return element(SPAN_TAG, tipProps, text(props.name));
  }

  function StepRow(props) {
    var call = Array.isArray(props.call) ? props.call : [];
    var name = call.length ? call[ZERO] : undefined;
    var answer = call.length > STEP ? call[STEP] : undefined;
    var rowProps = { className: PANEL_CLASS };
    rowProps[PART_ATTR] = STEP_PART;
    rowProps[STEP_ATTR] = text(name);
    rowProps[INDEX_ATTR] = text(props.at);
    rowProps[KIND_ATTR] = kindOf(answer);
    return element(DIV_TAG, rowProps, text(answer));
  }

  function Refusal(props) {
    var found = props.refused;
    if (!isPlainObject(found)) {
      return null;
    }
    var refusalProps = { className: PANEL_CLASS };
    refusalProps[PART_ATTR] = REFUSAL_PART;
    refusalProps[STEP_ATTR] = text(found[REFUSAL_STEP]);
    refusalProps[INDEX_ATTR] = text(found[REFUSAL_INDEX]);
    refusalProps[TYPE_ATTR] = text(found[REFUSAL_TYPE]);
    return element(DIV_TAG, refusalProps, text(found[REFUSAL_STEP]));
  }

  // Panel draws nothing for a payload that is not an object.
  function Panel(props) {
    if (!isPlainObject(props.model)) {
      return null;
    }
    var model = props.model;
    var panelProps = { id: props.id, className: PANEL_CLASS };
    panelProps[PART_ATTR] = PANEL_PART;
    panelProps[RAN_ATTR] = text(model[RAN]);
    panelProps[COUNT_ATTR] = text(listField(model, STEP_NAMES).length);
    panelProps[VISIBLE_ROWS_ATTR] = text(token(VISIBLE_ROWS));
    var drawn = [];
    fillNames().forEach(function (fill) {
      drawn.push(element(FillSwatch, { key: FILL_PART + fill, fill: fill }));
    });
    orders().forEach(function (order, at) {
      drawn.push(element(OrderName, { key: ORDER_PART + String(at), order: order, at: at }));
    });
    columnTips().forEach(function (tip, at) {
      drawn.push(element(ColumnTip, { key: COLUMN_TIP_PART + String(at), tip: tip, at: at }));
    });
    arbiterValues().forEach(function (value, at) {
      drawn.push(element(ArbiterWord, { key: ARBITER_PART + String(at), value: value }));
    });
    sourceNames().forEach(function (name) {
      drawn.push(element(SourceTip, { key: SOURCE_PART + name, name: name }));
    });
    listField(model, CALLS).forEach(function (call, at) {
      drawn.push(element(StepRow, { key: STEP_PART + String(at), call: call, at: at }));
    });
    drawn.push(element(Refusal, { key: REFUSAL_PART, refused: model[REFUSED] }));
    return element(DIV_TAG, panelProps, drawn);
  }

  function heldFieldCount(model) {
    return DECLARED_FIELDS.filter(function (name) {
      return owns(model, name);
    }).length;
  }

  // Counts the fields, tokens and steps declared against those held.
  function report() {
    var model = held.model;
    var declared = Array.isArray(token(STEP_NAMES_TOKEN)) ? token(STEP_NAMES_TOKEN) : [];
    return {
      declared: {
        fields: DECLARED_FIELDS.length,
        steps: declared.length,
        ran: model[RAN],
        colours: colourTokens().length
      },
      held: {
        fields: heldFieldCount(model),
        steps: listField(model, STEP_NAMES).length,
        ran: listField(model, CALLS).length,
        colours: colourTokens().length
      },
      faults: tokenFaults.slice()
    };
  }

  function setTokens(model) {
    if (!isPlainObject(model)) {
      held = null;
      tokenFaults = [fault(null, null, NOT_AN_OBJECT_FAULT, kindOf(model))];
      return { declared: null, held: null, faults: tokenFaults.slice() };
    }
    held = { model: model };
    tokenFaults = [];
    checkFields(model);
    checkColours();
    checkBagOrder(model);
    checkSteps(model);
    checkRefusal(model);
    return report();
  }

  // Asks METHOD once, clearing asked so a refused first ask is retried.
  function loadTokens(params) {
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
        setTokens(model);
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

  // The JavaScript type of every value in the payload, by dotted path.
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
    return tokenFaults.slice();
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
  function renderPanel(target, model) {
    if (isPlainObject(model)) {
      setTokens(model);
    }
    return draw(target, element(Panel, { model: held === null ? null : held.model }));
  }

  function forget() {
    held = null;
    tokenFaults = [];
    loadFault = null;
    asked = null;
  }

  global.acervatorSetFoldTokens = setTokens;
  global.acervatorLoadFoldTokens = loadTokens;
  global.acervatorFoldTokens = {
    method: METHOD,
    Panel: Panel,
    FillSwatch: FillSwatch,
    StepRow: StepRow,
    payload: payload,
    declaredNames: declaredNames,
    field: field,
    bag: bag,
    list: list,
    bagKeys: bagKeys,
    tokenNames: tokenNames,
    token: token,
    colourTokens: colourTokens,
    fillNames: fillNames,
    borderFor: borderFor,
    orders: orders,
    columnTips: columnTips,
    arbiterValues: arbiterValues,
    arbiterLabel: arbiterLabel,
    sourceNames: sourceNames,
    sourceTooltip: sourceTooltip,
    stepNames: stepNames,
    calls: calls,
    answers: answers,
    refusal: refusal,
    isSwappedAlpha: isSwappedAlpha,
    isReorderedKey: isReorderedKey,
    colour: colour,
    kinds: kinds,
    notPlainData: notPlainData,
    faults: faults,
    loadError: loadError,
    isLoaded: isLoaded,
    renderPanel: renderPanel,
    forget: forget
  };
})(window);
