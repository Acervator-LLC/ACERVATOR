// The design tokens, as the Python surface serves them.
//
// Every colour, size, spacing step, radius and duration reaches this
// file over the bridge from `src/gui/main_tabs/design_system_surface.py`.
// This file holds no token value of its own. A colour or a size written
// here would be a second source of truth for one skin.
//
// Two ways in, matching the pair the History panel already uses.
// `acervatorLoadTokens` asks the backend, once per page, the way
// `desktop/renderer/boot.js` asks for its view model.
// `acervatorSetTokens` takes a payload a caller already holds.
//
// It reports and it does not repair. A name the payload declares but
// does not carry, and a name carrying null, are recorded in `faults` and
// left as they arrived.
(function (global) {
  "use strict";

  var METHOD = "design_system.state";

  var NAMES_FIELD = "token_names";
  var VALUES_FIELD = "tokens";
  var GROUPS_FIELD = "groups";
  var GROUP_NAMES_FIELD = "group_names";
  var ALIASES_FIELD = "alias_targets";

  var MISSING_FAULT = "missing";
  var NULL_FAULT = "null";
  var NOT_AN_OBJECT_FAULT = "not-an-object";
  var NO_BRIDGE = "the preload bridge is not present";

  var CSS_PREFIX = "--";
  var WRITABLE_KINDS = { string: true, number: true };

  var held = null;
  var tokenFaults = [];
  var loadFault = null;
  var asked = null;

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

  // Records one entry per declared name the payload does not honour.
  function faultsIn(declared, values) {
    var found = [];
    declared.forEach(function (name) {
      if (!owns(values, name)) {
        found.push({ name: name, fault: MISSING_FAULT });
        return;
      }
      if (values[name] === null) {
        found.push({ name: name, fault: NULL_FAULT });
      }
    });
    return found;
  }

  // Takes one payload and returns a count of what arrived. `declared` is
  // the name list the surface published, `held` the values it carried;
  // the two are counted apart so a payload that declares more than it
  // carries reads as a difference rather than as a full table.
  function setTokens(model) {
    if (!isPlainObject(model)) {
      held = null;
      tokenFaults = [{ name: VALUES_FIELD, fault: NOT_AN_OBJECT_FAULT }];
      return { declared: null, held: null, faults: tokenFaults.slice() };
    }
    var declared = listField(model, NAMES_FIELD);
    var values = objectField(model, VALUES_FIELD);
    tokenFaults = faultsIn(declared, values);
    held = {
      declared: declared,
      values: values,
      groups: objectField(model, GROUPS_FIELD),
      groupNames: listField(model, GROUP_NAMES_FIELD),
      aliases: objectField(model, ALIASES_FIELD)
    };
    return {
      declared: declared.length,
      held: Object.keys(values).length,
      faults: tokenFaults.slice()
    };
  }

  // Asks the backend once and remembers the request, so several panels
  // on one page cost one round trip. Resolves to null when the bridge is
  // absent or refuses; `loadError` then carries the reason. A failed ask
  // is not remembered, so a later caller reaches a backend that has
  // since started.
  function loadTokens() {
    if (asked !== null) {
      return asked;
    }
    if (!global.acervator || typeof global.acervator.call !== "function") {
      loadFault = NO_BRIDGE;
      return Promise.resolve(null);
    }
    asked = global.acervator
      .call(METHOD, {})
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

  function token(name) {
    return has(name) ? held.values[name] : undefined;
  }

  function has(name) {
    return held !== null && owns(held.values, name);
  }

  function names() {
    return held === null ? [] : Object.keys(held.values);
  }

  function declaredNames() {
    return held === null ? [] : held.declared.slice();
  }

  function group(name) {
    var found = held === null ? undefined : held.groups[name];
    return isPlainObject(found) ? found : {};
  }

  function groupNames() {
    return held === null ? [] : held.groupNames.slice();
  }

  function aliasTarget(name) {
    if (held === null || !owns(held.aliases, name)) {
      return undefined;
    }
    return held.aliases[name];
  }

  // The JavaScript type each value arrived as, null reported apart from
  // object. A caller comparing this against the Python side sees a value
  // that changed shape in transit.
  function types() {
    var found = {};
    names().forEach(function (name) {
      var value = held.values[name];
      found[name] = value === null ? NULL_FAULT : typeof value;
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

  // Writes every text and number token onto one element as a CSS custom
  // property under its own name, and returns the names written. A value
  // that is neither text nor a number reaches no stylesheet and is left
  // out rather than flattened into one.
  function apply(target) {
    var written = [];
    if (held === null || !target || !target.style) {
      return written;
    }
    Object.keys(held.values).forEach(function (name) {
      var value = held.values[name];
      if (!owns(WRITABLE_KINDS, typeof value)) {
        return;
      }
      target.style.setProperty(CSS_PREFIX + name, String(value));
      written.push(name);
    });
    return written;
  }

  function forget() {
    held = null;
    tokenFaults = [];
    loadFault = null;
    asked = null;
  }

  global.acervatorSetTokens = setTokens;
  global.acervatorLoadTokens = loadTokens;
  global.acervatorTokens = {
    method: METHOD,
    token: token,
    has: has,
    names: names,
    declaredNames: declaredNames,
    group: group,
    groupNames: groupNames,
    aliasTarget: aliasTarget,
    types: types,
    faults: faults,
    loadError: loadError,
    isLoaded: isLoaded,
    apply: apply,
    forget: forget
  };
})(window);
