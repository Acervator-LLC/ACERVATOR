// The `privacy_dot.state` payload, drawn with `acervatorHeader.PrivacyDot`.
(function (global) {
  "use strict";

  var METHOD = "privacy_dot.state";

  var FIELD_ID = "field_id";
  var MASKED = "masked";
  var TEXT = "text";
  var TOOLTIP = "tooltip";
  var STYLE_SHEET = "style_sheet";
  var FLAT = "flat";
  var FOCUS_POLICY = "focus_policy";
  var CURSOR_SHAPE = "cursor_shape";
  var GLYPHS = "glyphs";
  var STATES = "states";
  var ACTIONS = "actions";
  var TIMERS = "timers";
  var TIMER_DELAYS = "timer_delays_ms";
  var BUS_TOPICS = "bus_topics";
  var CALL_NAMES = "call_names";
  var CALLS = "calls";
  var METHOD_FIELD = "method";
  var REVEALED = "revealed";

  var DECLARED_FIELDS = [
    ACTIONS,
    BUS_TOPICS,
    CALLS,
    CALL_NAMES,
    CURSOR_SHAPE,
    FIELD_ID,
    FLAT,
    FOCUS_POLICY,
    GLYPHS,
    MASKED,
    METHOD_FIELD,
    STATES,
    STYLE_SHEET,
    TEXT,
    TIMERS,
    TIMER_DELAYS,
    TOOLTIP
  ];

  var MISSING_FAULT = "missing";
  var NULL_FAULT = "null";
  var NOT_AN_OBJECT_FAULT = "not-an-object";
  var WRONG_TYPE_FAULT = "wrong-type";
  var WRONG_GLYPH_FAULT = "wrong-glyph";
  var WRONG_TOOLTIP_FAULT = "wrong-tooltip";
  var UNNAMED_CALL_FAULT = "unnamed-call";
  var NO_SPAN_FAULT = "no-dot-span";

  var NO_BRIDGE = "the preload bridge is not present";

  var PATH_SPLIT = ".";
  var EMPTY = "";

  var HOST_CLASS = "acervator-privacy-dot";
  var HOST_PART = "dot";
  var STYLE_PART = "dot-style";
  var PART_ATTR = "data-part";
  var FLAT_ATTR = "data-flat";
  var FOCUS_ATTR = "data-focus-policy";
  var CURSOR_ATTR = "data-cursor-shape";
  var ACTION_ATTR = "data-action";
  var ROLE_ATTR = "role";
  var BUTTON_ROLE = "button";

  var CLICKED = "clicked";
  var CLICKS = "clicks";
  var ONE_CLICK = 1;

  var CLASS_MARK = ".";
  var COLON = ":";
  var CHILD_SPAN = " span";
  var BLOCK_OPEN = "{";
  var BLOCK_CLOSE = "}";

  // The one cursor name the surface publishes, as CSS spells it.
  var CURSOR_BY_NAME = { PointingHandCursor: "pointer" };

  var held = null;
  var dotFaults = [];
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

  function fault(where, field, kind, detail) {
    return { where: where, field: field, fault: kind, detail: detail };
  }

  // Undefined leaves an attribute off the element instead of writing one.
  function text(value) {
    return value === null || value === undefined ? undefined : String(value);
  }

  // The `glyphs` and `states` key the `masked` flag names.
  function stateName(masked) {
    return masked === true ? MASKED : REVEALED;
  }

  function element() {
    return global.React.createElement.apply(null, arguments);
  }

  // The strip's own dot span, absent on a page that never loaded it.
  function dotSpan() {
    var api = global.acervatorHeader;
    return api && api.PrivacyDot ? api.PrivacyDot : null;
  }

  // No inline style carries a hover colour, so `stateRules` becomes a
  // page rule.
  function hoverCss(sheet) {
    var api = global.acervatorHeader;
    if (!api || typeof api.stateRules !== "function") {
      return EMPTY;
    }
    return api
      .stateRules(sheet)
      .map(function (rule) {
        var states = String(rule.selector).split(COLON);
        states.shift();
        return (
          CLASS_MARK +
          HOST_CLASS +
          COLON +
          states.join(COLON) +
          CHILD_SPAN +
          BLOCK_OPEN +
          rule.body +
          BLOCK_CLOSE
        );
      })
      .join(EMPTY);
  }

  function Dot(props) {
    var model = props.model;
    if (!isPlainObject(model)) {
      return null;
    }
    var span = dotSpan();
    var style = {};
    if (owns(CURSOR_BY_NAME, model[CURSOR_SHAPE])) {
      style.cursor = CURSOR_BY_NAME[model[CURSOR_SHAPE]];
    }
    var hostProps = { className: HOST_CLASS, style: style, onClick: clicked };
    hostProps[PART_ATTR] = HOST_PART;
    hostProps[ROLE_ATTR] = BUTTON_ROLE;
    hostProps[FLAT_ATTR] = text(model[FLAT]);
    hostProps[FOCUS_ATTR] = text(model[FOCUS_POLICY]);
    hostProps[CURSOR_ATTR] = text(model[CURSOR_SHAPE]);
    hostProps[ACTION_ATTR] = text(objectField(model, ACTIONS)[CLICKED]);

    var css = hoverCss(model[STYLE_SHEET]);
    var styleProps = {};
    styleProps[PART_ATTR] = STYLE_PART;

    return element(
      "span",
      hostProps,
      css ? element("style", styleProps, css) : null,
      span === null ? null : element(span, { dot: model })
    );
  }

  function checkFields(model) {
    DECLARED_FIELDS.forEach(function (field) {
      if (!owns(model, field)) {
        dotFaults.push(fault(null, field, MISSING_FAULT, null));
        return;
      }
      if (model[field] === null) {
        dotFaults.push(fault(null, field, NULL_FAULT, null));
      }
    });
  }

  // A wrong type is named only where `defaults` publishes one of the
  // same meaning.
  function checkAgainstDefault(field, defaults, defaultField) {
    if (!owns(defaults, defaultField) || defaults[defaultField] === null) {
      return;
    }
    var wanted = kindOf(defaults[defaultField]);
    if (!owns(held.model, field)) {
      return;
    }
    if (held.model[field] !== null && kindOf(held.model[field]) !== wanted) {
      dotFaults.push(
        fault(null, field, WRONG_TYPE_FAULT, kindOf(held.model[field]))
      );
    }
  }

  // The dot hides money, so a glyph that disagrees with `masked` would
  // show a revealed amount as hidden.
  function checkGlyph(model) {
    var glyphs = objectField(model, GLYPHS);
    var name = stateName(model[MASKED]);
    if (!owns(glyphs, name)) {
      dotFaults.push(fault(GLYPHS, name, MISSING_FAULT, null));
      return;
    }
    if (model[TEXT] !== glyphs[name]) {
      dotFaults.push(fault(null, TEXT, WRONG_GLYPH_FAULT, kindOf(model[TEXT])));
    }
  }

  // The tooltip names the field and ends in the state the flag names.
  function checkTooltip(model) {
    var states = objectField(model, STATES);
    var name = stateName(model[MASKED]);
    if (!owns(states, name) || typeof model[TOOLTIP] !== "string") {
      return;
    }
    var tip = model[TOOLTIP];
    var opens = tip.startsWith(String(model[FIELD_ID]));
    var closes = tip.endsWith(String(states[name]));
    if (!opens || !closes) {
      dotFaults.push(fault(null, TOOLTIP, WRONG_TOOLTIP_FAULT, tip));
    }
  }

  // A branch the dot took that `call_names` never declared.
  function checkCalls(model) {
    var declared = listField(model, CALL_NAMES);
    listField(model, CALLS).forEach(function (name) {
      var known = false;
      declared.forEach(function (one) {
        if (one === name) {
          known = true;
        }
      });
      if (!known) {
        dotFaults.push(fault(CALLS, name, UNNAMED_CALL_FAULT, null));
      }
    });
  }

  function checkSpan() {
    if (dotSpan() === null) {
      dotFaults.push(fault(null, TEXT, NO_SPAN_FAULT, null));
    }
  }

  function heldFieldCount() {
    return DECLARED_FIELDS.filter(function (field) {
      return held !== null && owns(held.model, field);
    }).length;
  }

  function report() {
    return {
      declared: {
        fields: DECLARED_FIELDS.length,
        calls: listField(held.model, CALL_NAMES).length
      },
      held: {
        fields: heldFieldCount(),
        calls: listField(held.model, CALLS).length
      },
      faults: dotFaults.slice()
    };
  }

  function setDot(model) {
    if (!isPlainObject(model)) {
      held = null;
      dotFaults = [fault(null, null, NOT_AN_OBJECT_FAULT, kindOf(model))];
      return { declared: null, held: null, faults: dotFaults.slice() };
    }
    held = { model: model };
    dotFaults = [];
    checkFields(model);
    checkAgainstDefault(TEXT, objectField(model, GLYPHS), MASKED);
    checkAgainstDefault(TOOLTIP, objectField(model, STATES), MASKED);
    checkGlyph(model);
    checkTooltip(model);
    checkCalls(model);
    checkSpan();
    return report();
  }

  // A click flips the field's mask through the surface and draws the
  // answer, which is what the Qt button does.
  function clicked() {
    if (held === null) {
      return Promise.resolve(null);
    }
    if (!global.acervator || typeof global.acervator.call !== "function") {
      loadFault = NO_BRIDGE;
      return Promise.resolve(null);
    }
    var params = {};
    params[FIELD_ID] = held.model[FIELD_ID];
    params[CLICKS] = ONE_CLICK;
    return global.acervator
      .call(METHOD, params)
      .then(function (model) {
        loadFault = null;
        setDot(model);
        redraw();
        return model;
      })
      .catch(function (err) {
        loadFault = err.message;
        return null;
      });
  }

  // One round trip per page, and a failed ask is not remembered.
  function loadDot(params) {
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
        setDot(model);
        return model;
      })
      .catch(function (err) {
        loadFault = err.message;
        asked = null;
        return null;
      });
    return asked;
  }

  function field(name) {
    return held === null ? undefined : held.model[name];
  }

  function bag(name) {
    return held === null ? {} : copyOf(objectField(held.model, name));
  }

  function list(name) {
    return held === null ? [] : listField(held.model, name).slice();
  }

  function fieldId() {
    return field(FIELD_ID);
  }

  function masked() {
    return field(MASKED);
  }

  function glyphText() {
    return field(TEXT);
  }

  function tooltip() {
    return field(TOOLTIP);
  }

  function styleSheet() {
    return field(STYLE_SHEET);
  }

  function flat() {
    return field(FLAT);
  }

  function focusPolicy() {
    return field(FOCUS_POLICY);
  }

  function cursorShape() {
    return field(CURSOR_SHAPE);
  }

  function glyphs() {
    return bag(GLYPHS);
  }

  function states() {
    return bag(STATES);
  }

  function actions() {
    return bag(ACTIONS);
  }

  function timers() {
    return bag(TIMERS);
  }

  function timerDelaysMs() {
    return list(TIMER_DELAYS);
  }

  function busTopics() {
    return list(BUS_TOPICS);
  }

  function callNames() {
    return list(CALL_NAMES);
  }

  function calls() {
    return list(CALLS);
  }

  function methodName() {
    return field(METHOD_FIELD);
  }

  function glyph(name) {
    var found = glyphs();
    return owns(found, name) ? found[name] : undefined;
  }

  function state(name) {
    var found = states();
    return owns(found, name) ? found[name] : undefined;
  }

  function action(name) {
    var found = actions();
    return owns(found, name) ? found[name] : undefined;
  }

  function declaredFields() {
    return DECLARED_FIELDS.slice();
  }

  function cursorNames() {
    return Object.keys(CURSOR_BY_NAME);
  }

  // Every payload value's JavaScript type, by dotted path, null apart.
  function kinds() {
    var found = {};
    function walk(prefix, node) {
      Object.keys(node).forEach(function (name) {
        var path = prefix ? prefix + PATH_SPLIT + name : name;
        found[path] = kindOf(node[name]);
        descend(path, node[name]);
      });
    }
    function descend(path, value) {
      if (isPlainObject(value)) {
        walk(path, value);
        return;
      }
      if (Array.isArray(value)) {
        value.forEach(function (one, at) {
          var inner = path + PATH_SPLIT + String(at);
          found[inner] = kindOf(one);
          descend(inner, one);
        });
      }
    }
    if (held !== null) {
      walk(EMPTY, held.model);
    }
    return found;
  }

  function faults() {
    return dotFaults.slice();
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

  function renderDot(target, model) {
    var payload = model;
    if (!isPlainObject(payload)) {
      payload = held === null ? null : held.model;
    }
    return draw(target, element(Dot, { model: payload }));
  }

  // Every target already drawn into, redrawn from the state now held.
  function redraw() {
    roots.forEach(function (pair) {
      draw(pair.node, element(Dot, { model: held === null ? null : held.model }));
    });
  }

  function forget() {
    held = null;
    dotFaults = [];
    loadFault = null;
    asked = null;
  }

  global.acervatorSetDot = setDot;
  global.acervatorLoadDot = loadDot;
  global.acervatorDot = {
    method: METHOD,
    Dot: Dot,
    clicked: clicked,
    hoverCss: hoverCss,
    fieldId: fieldId,
    masked: masked,
    text: glyphText,
    tooltip: tooltip,
    styleSheet: styleSheet,
    flat: flat,
    focusPolicy: focusPolicy,
    cursorShape: cursorShape,
    glyphs: glyphs,
    glyph: glyph,
    states: states,
    state: state,
    actions: actions,
    action: action,
    timers: timers,
    timerDelaysMs: timerDelaysMs,
    busTopics: busTopics,
    callNames: callNames,
    calls: calls,
    methodName: methodName,
    declaredFields: declaredFields,
    cursorNames: cursorNames,
    kinds: kinds,
    faults: faults,
    loadError: loadError,
    isLoaded: isLoaded,
    renderDot: renderDot,
    forget: forget
  };
})(window);
