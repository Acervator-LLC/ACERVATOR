// The themes, as the Python surface serves them.
//
// Every colour, font stack, text size and corner rounding reaches this
// file over the bridge from `src/gui/main_tabs/theme_engine_surface.py`.
// This file holds no theme value of its own. A colour or a size written
// here would be a second source of truth for one skin.
//
// Two ways in, matching the pair `design_tokens.js` uses.
// `acervatorLoadThemes` asks the backend, once per page, the way
// `desktop/renderer/boot.js` asks for its view model.
// `acervatorSetThemes` takes a payload a caller already holds.
//
// A theme value that opens with `token:` names a design token. It is
// resolved through `design_tokens.js`, never copied. A name the theme
// itself carries is followed inside the theme first, so a chain that
// returns to a name already seen ends and is recorded.
//
// It reports and it does not repair. A theme the payload declares but
// does not carry, a theme carrying null, a value carrying null and a
// reference that reaches nothing are recorded in `faults` and left as
// they arrived.
(function (global) {
  "use strict";

  var METHOD = "theme_engine.state";

  var NAMES_FIELD = "theme_names";
  var THEMES_FIELD = "themes";
  var DISPLAY_FIELD = "display_names";
  var FIELDS_FIELD = "field_names";
  var STYLE_SHEETS_FIELD = "style_sheets";
  var CURRENT_FIELD = "current";
  var NAME_PARAM = "name";

  var MISSING_FAULT = "missing";
  var NULL_FAULT = "null";
  var NOT_AN_OBJECT_FAULT = "not-an-object";
  var NOT_A_TABLE_FAULT = "not-a-table";
  var UNRESOLVED_FAULT = "unresolved-reference";
  var CYCLE_FAULT = "reference-cycle";
  var NO_TOKENS_FAULT = "no-token-table";

  var REFERENCE_MARK = "token:";
  var CSS_PREFIX = "--";
  var NO_BRIDGE = "the preload bridge is not present";
  var WRITABLE_KINDS = { string: true, number: true };

  var held = null;
  var themeFaults = [];
  var loadFault = null;
  var asked = null;
  var selected = null;

  function isPlainObject(value) {
    return value !== null && typeof value === "object" && !Array.isArray(value);
  }

  function owns(bag, name) {
    return Object.prototype.hasOwnProperty.call(bag, name);
  }

  function contains(list, value) {
    var found = false;
    list.forEach(function (item) {
      if (item === value) {
        found = true;
      }
    });
    return found;
  }

  function objectField(model, field) {
    return isPlainObject(model) && isPlainObject(model[field]) ? model[field] : {};
  }

  function listField(model, field) {
    return isPlainObject(model) && Array.isArray(model[field]) ? model[field] : [];
  }

  function textField(model, field) {
    return isPlainObject(model) && typeof model[field] === "string"
      ? model[field]
      : null;
  }

  function copyOf(bag) {
    var found = {};
    Object.keys(bag).forEach(function (key) {
      found[key] = bag[key];
    });
    return found;
  }

  function fault(theme, field, kind, target) {
    return { theme: theme, field: field, fault: kind, target: target };
  }

  // The design-token table `design_tokens.js` publishes, or null when
  // that module has not run. A reference is left as it arrived rather
  // than resolved against a table that is not there.
  function tokenTable() {
    var api = global.acervatorTokens;
    var usable =
      api &&
      typeof api.has === "function" &&
      typeof api.token === "function" &&
      typeof api.names === "function";
    return usable ? api : null;
  }

  function isReference(value) {
    return typeof value === "string" && value.startsWith(REFERENCE_MARK);
  }

  // Follows one field's value while it names something else. A name the
  // theme carries is followed inside the theme; any other name is asked
  // of the token table. A name already seen ends the walk and the value
  // stays as it arrived.
  function follow(themeName, body, field, tokens) {
    var seen = [];
    var value = body[field];
    while (isReference(value)) {
      var target = value.slice(REFERENCE_MARK.length);
      if (contains(seen, target)) {
        themeFaults.push(fault(themeName, field, CYCLE_FAULT, target));
        return value;
      }
      seen.push(target);
      if (owns(body, target)) {
        value = body[target];
        continue;
      }
      if (tokens === null) {
        themeFaults.push(fault(themeName, field, NO_TOKENS_FAULT, target));
        return value;
      }
      if (!tokens.has(target)) {
        themeFaults.push(fault(themeName, field, UNRESOLVED_FAULT, target));
        return value;
      }
      return tokens.token(target);
    }
    return value;
  }

  // One theme's values after resolution, and one fault per declared
  // field the theme does not carry.
  function resolveTheme(themeName, body, tokens) {
    var found = {};
    held.fields.forEach(function (field) {
      if (!owns(body, field)) {
        themeFaults.push(fault(themeName, field, MISSING_FAULT, null));
      }
    });
    Object.keys(body).forEach(function (field) {
      if (body[field] === null) {
        themeFaults.push(fault(themeName, field, NULL_FAULT, null));
        found[field] = null;
        return;
      }
      found[field] = follow(themeName, body, field, tokens);
    });
    return found;
  }

  // The token name carrying the same value as each resolved field, for
  // a screen that paints from a CSS variable rather than from a colour.
  function nameTokens(values, tokens) {
    var found = {};
    if (tokens === null) {
      return found;
    }
    var tokenNames = tokens.names();
    Object.keys(values).forEach(function (field) {
      var value = values[field];
      if (!owns(WRITABLE_KINDS, typeof value)) {
        return;
      }
      var text = String(value);
      var match = null;
      tokenNames.forEach(function (tokenName) {
        if (match !== null) {
          return;
        }
        var candidate = tokens.token(tokenName);
        if (owns(WRITABLE_KINDS, typeof candidate) && String(candidate) === text) {
          match = tokenName;
        }
      });
      if (match !== null) {
        found[field] = match;
      }
    });
    return found;
  }

  // Rebuilds every theme's values and the whole fault list. Public, so a
  // page that receives the tokens after the themes can resolve again
  // rather than hold references nothing answered.
  function resolveAll() {
    themeFaults = [];
    if (held === null) {
      return { declared: null, held: null, faults: [] };
    }
    var tokens = tokenTable();
    held.resolved = {};
    held.tokenNameByField = {};
    held.declared.forEach(function (themeName) {
      if (!owns(held.raw, themeName)) {
        themeFaults.push(fault(themeName, null, MISSING_FAULT, null));
      }
    });
    Object.keys(held.raw).forEach(function (themeName) {
      var body = held.raw[themeName];
      if (body === null) {
        themeFaults.push(fault(themeName, null, NULL_FAULT, null));
        return;
      }
      if (!isPlainObject(body)) {
        themeFaults.push(fault(themeName, null, NOT_A_TABLE_FAULT, null));
        return;
      }
      held.resolved[themeName] = resolveTheme(themeName, body, tokens);
      held.tokenNameByField[themeName] = nameTokens(held.resolved[themeName], tokens);
    });
    if (selected !== null && !owns(held.resolved, selected)) {
      selected = null;
    }
    return report();
  }

  // The declared count and the held count are kept apart, so a payload
  // that promises more themes than it carries reads as a difference
  // rather than as a full table.
  function report() {
    return {
      declared: held.declared.length,
      held: Object.keys(held.resolved).length,
      faults: themeFaults.slice()
    };
  }

  function setThemes(model) {
    if (!isPlainObject(model)) {
      held = null;
      selected = null;
      themeFaults = [fault(THEMES_FIELD, null, NOT_AN_OBJECT_FAULT, null)];
      return { declared: null, held: null, faults: themeFaults.slice() };
    }
    held = {
      declared: listField(model, NAMES_FIELD),
      raw: objectField(model, THEMES_FIELD),
      display: objectField(model, DISPLAY_FIELD),
      fields: listField(model, FIELDS_FIELD),
      styleSheets: objectField(model, STYLE_SHEETS_FIELD),
      resolved: {},
      tokenNameByField: {}
    };
    selected = null;
    var counts = resolveAll();
    selected = select(textField(model, CURRENT_FIELD));
    return counts;
  }

  // Asks the backend once and remembers the request, so several panels
  // on one page cost one round trip. Resolves to null when the bridge is
  // absent or refuses; `loadError` then carries the reason. A failed ask
  // is not remembered, so a later caller reaches a backend that has
  // since started.
  function loadThemes(name) {
    if (asked !== null) {
      return asked;
    }
    if (!global.acervator || typeof global.acervator.call !== "function") {
      loadFault = NO_BRIDGE;
      return Promise.resolve(null);
    }
    var params = {};
    if (typeof name === "string") {
      params[NAME_PARAM] = name;
    }
    asked = global.acervator
      .call(METHOD, params)
      .then(function (model) {
        loadFault = null;
        setThemes(model);
        return model;
      })
      .catch(function (err) {
        loadFault = err.message;
        asked = null;
        return null;
      });
    return asked;
  }

  function has(name) {
    return held !== null && owns(held.resolved, name);
  }

  function names() {
    return held === null ? [] : Object.keys(held.resolved);
  }

  function declaredNames() {
    return held === null ? [] : held.declared.slice();
  }

  function fieldNames() {
    return held === null ? [] : held.fields.slice();
  }

  function theme(name) {
    return has(name) ? copyOf(held.resolved[name]) : {};
  }

  function value(name, field) {
    if (!has(name) || !owns(held.resolved[name], field)) {
      return undefined;
    }
    return held.resolved[name][field];
  }

  function raw(name) {
    if (held === null || !owns(held.raw, name) || !isPlainObject(held.raw[name])) {
      return {};
    }
    return copyOf(held.raw[name]);
  }

  function displayName(name) {
    if (held === null || !owns(held.display, name)) {
      return undefined;
    }
    return held.display[name];
  }

  function styleSheet(name) {
    if (held === null || !owns(held.styleSheets, name)) {
      return undefined;
    }
    return held.styleSheets[name];
  }

  function tokenNames(name) {
    if (held === null || !owns(held.tokenNameByField, name)) {
      return {};
    }
    return copyOf(held.tokenNameByField[name]);
  }

  function tokenNameFor(name, field) {
    var found = tokenNames(name);
    return owns(found, field) ? found[field] : undefined;
  }

  // A name the module does not hold changes nothing and answers null.
  function select(name) {
    if (!has(name)) {
      return null;
    }
    selected = name;
    return selected;
  }

  function current() {
    return selected;
  }

  // The values a screen paints with: the selected theme, resolved.
  function painted() {
    return selected === null ? {} : theme(selected);
  }

  // The JavaScript type each value of one theme arrived as, null
  // reported apart from object. A caller comparing this against the
  // Python side sees a value that changed shape in transit.
  function types(name) {
    var found = {};
    var values = theme(name);
    Object.keys(values).forEach(function (field) {
      found[field] = values[field] === null ? NULL_FAULT : typeof values[field];
    });
    return found;
  }

  function faults() {
    return themeFaults.slice();
  }

  function loadError() {
    return loadFault;
  }

  function isLoaded() {
    return held !== null;
  }

  // Writes every text and number value of the selected theme onto one
  // element as a CSS custom property under its own field name, and
  // returns the names written. A value that is neither text nor a number
  // reaches no stylesheet and is left out rather than flattened into one.
  function apply(target) {
    var written = [];
    var values = painted();
    if (!target || !target.style) {
      return written;
    }
    Object.keys(values).forEach(function (field) {
      if (!owns(WRITABLE_KINDS, typeof values[field])) {
        return;
      }
      target.style.setProperty(CSS_PREFIX + field, String(values[field]));
      written.push(field);
    });
    return written;
  }

  function forget() {
    held = null;
    themeFaults = [];
    loadFault = null;
    asked = null;
    selected = null;
  }

  global.acervatorSetThemes = setThemes;
  global.acervatorLoadThemes = loadThemes;
  global.acervatorThemes = {
    method: METHOD,
    referenceMark: REFERENCE_MARK,
    names: names,
    declaredNames: declaredNames,
    fieldNames: fieldNames,
    has: has,
    theme: theme,
    value: value,
    raw: raw,
    displayName: displayName,
    styleSheet: styleSheet,
    tokenNames: tokenNames,
    tokenNameFor: tokenNameFor,
    select: select,
    current: current,
    painted: painted,
    types: types,
    resolve: resolveAll,
    faults: faults,
    loadError: loadError,
    isLoaded: isLoaded,
    apply: apply,
    forget: forget
  };
})(window);
