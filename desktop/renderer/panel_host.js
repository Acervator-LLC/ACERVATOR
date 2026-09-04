// Draws a converted panel into a host element addressed by the panel's name,
// and names on screen every panel that did not draw and the reason it did not.
//
// A panel name is its module file name without the extension. The roster of
// names is `window.ACERVATOR_MODULES`, which `tools/sync_renderer_modules.py`
// writes, so the shell holds no list of its own. A module joins the roster by
// calling `register` from its own script tag; `document.currentScript` names
// the file, so the module spells out no name either.

"use strict";

(function (global, doc) {
  var HOST_ATTRIBUTE = "data-panel";
  var FAULT_ATTRIBUTE = "data-panel-error";
  var SUFFIX = ".js";
  var UNNAMED = "(unnamed)";
  var panels = {};
  var recorded = [];

  function fileName(url) {
    var path = String(url).split("?")[0].split("#")[0];
    var parts = path.split("/");
    return parts[parts.length - 1];
  }

  function baseName(name) {
    var text = String(name);
    var at = text.length - SUFFIX.length;
    return at > 0 && text.slice(at) === SUFFIX ? text.slice(0, at) : text;
  }

  function names() {
    var list = global.ACERVATOR_MODULES;
    if (Object.prototype.toString.call(list) !== "[object Array]") {
      return [];
    }
    var found = [];
    for (var index = 0; index < list.length; index++) {
      found.push(baseName(list[index]));
    }
    return found;
  }

  function registered() {
    var found = [];
    for (var name in panels) {
      if (Object.prototype.hasOwnProperty.call(panels, name)) {
        found.push(name);
      }
    }
    found.sort();
    return found;
  }

  function faults() {
    var found = [];
    for (var index = 0; index < recorded.length; index++) {
      found.push({
        panel: recorded[index].panel,
        reason: recorded[index].reason
      });
    }
    return found;
  }

  function stamp() {
    var named = [];
    for (var index = 0; index < recorded.length; index++) {
      named.push(recorded[index].panel);
    }
    if (named.length) {
      doc.documentElement.setAttribute(FAULT_ATTRIBUTE, named.join(","));
    } else {
      doc.documentElement.removeAttribute(FAULT_ATTRIBUTE);
    }
  }

  function dropFault(name) {
    var kept = [];
    for (var index = 0; index < recorded.length; index++) {
      if (recorded[index].panel !== name) {
        kept.push(recorded[index]);
      }
    }
    recorded = kept;
    stamp();
  }

  function record(name, reason) {
    dropFault(name);
    recorded.push({ panel: name, reason: reason });
    global.console.error("Acervator panel not drawn: " + name + ": " + reason);
    stamp();
  }

  function show(target, name, reason) {
    if (!target) {
      return;
    }
    target.setAttribute(FAULT_ATTRIBUTE, reason);
    target.textContent = "Panel " + name + " did not draw: " + reason;
  }

  function scriptName() {
    var tag = doc.currentScript;
    return tag && tag.src ? baseName(fileName(tag.src)) : null;
  }

  // Called by a panel module from its own script tag. `called` is for a
  // caller with no script tag of its own, which is how a test registers.
  function register(spec, called) {
    var name = called || scriptName();
    if (!name) {
      record(UNNAMED, "register ran outside a script tag and was given no name");
      return null;
    }
    if (!spec || typeof spec.render !== "function") {
      record(name, "registered no render function");
      return null;
    }
    panels[name] = spec;
    dropFault(name);
    return name;
  }

  function reasonFor(name) {
    var declared = names();
    if (!declared.length) {
      return "module_manifest.js named no modules, so no panel has a name";
    }
    if (declared.indexOf(name) < 0) {
      return "the manifest names no " + name + SUFFIX;
    }
    var broken = global.acervatorModuleErrors
      ? global.acervatorModuleErrors.names()
      : [];
    if (broken.indexOf(name + SUFFIX) >= 0) {
      return name + SUFFIX + " did not load";
    }
    if (!Object.prototype.hasOwnProperty.call(panels, name)) {
      return name + SUFFIX + " registered no panel to draw";
    }
    return null;
  }

  function messageOf(err) {
    return err && err.message ? String(err.message) : String(err);
  }

  function mount(name, target, model) {
    if (!target) {
      record(name, "no host element to draw into");
      return false;
    }
    var reason = reasonFor(name);
    if (reason === null) {
      try {
        panels[name].render(target, model);
      } catch (err) {
        reason = "the panel threw while drawing: " + messageOf(err);
      }
    }
    if (reason !== null) {
      show(target, name, reason);
      record(name, reason);
      return false;
    }
    target.removeAttribute(FAULT_ATTRIBUTE);
    dropFault(name);
    return true;
  }

  // Asks the panel's own loader for its view model, then draws it. Both
  // outcomes of the promise are handled here: a refusal is named on the
  // host element rather than dropped.
  function open(name, target) {
    var reason = reasonFor(name);
    if (reason !== null) {
      show(target, name, reason);
      record(name, reason);
      return Promise.resolve(false);
    }
    var spec = panels[name];
    if (typeof spec.load !== "function") {
      return Promise.resolve(mount(name, target, null));
    }
    return spec.load({}).then(
      function (model) {
        var refused =
          typeof spec.loadError === "function" ? spec.loadError() : null;
        if (refused) {
          var why = "the backend refused the view model: " + refused;
          show(target, name, why);
          record(name, why);
          return false;
        }
        return mount(name, target, model);
      },
      function (err) {
        var why = "the view model never arrived: " + messageOf(err);
        show(target, name, why);
        record(name, why);
        return false;
      }
    );
  }

  function hostFor(container, name) {
    var found = container.querySelector(
      "[" + HOST_ATTRIBUTE + '="' + name + '"]'
    );
    if (found === null) {
      found = doc.createElement("div");
      found.setAttribute(HOST_ATTRIBUTE, name);
      container.appendChild(found);
    }
    return found;
  }

  function wanted() {
    var declared = names();
    var found = [];
    for (var index = 0; index < declared.length; index++) {
      if (Object.prototype.hasOwnProperty.call(panels, declared[index])) {
        found.push(declared[index]);
      }
    }
    return found;
  }

  function reportStrays() {
    var declared = names();
    var known = registered();
    for (var index = 0; index < known.length; index++) {
      if (declared.indexOf(known[index]) < 0) {
        record(known[index], reasonFor(known[index]));
      }
    }
  }

  function mountAll(container) {
    if (!container) {
      record(UNNAMED, "the page holds no container for the panels");
      return Promise.resolve([]);
    }
    reportStrays();
    var asked = wanted();
    var opened = [];
    for (var index = 0; index < asked.length; index++) {
      opened.push(open(asked[index], hostFor(container, asked[index])));
    }
    return Promise.all(opened).then(function (results) {
      var drawn = [];
      for (var at = 0; at < results.length; at++) {
        if (results[at]) {
          drawn.push(asked[at]);
        }
      }
      return drawn;
    });
  }

  function forget() {
    panels = {};
    recorded = [];
    stamp();
  }

  global.acervatorPanelHost = {
    hostAttribute: HOST_ATTRIBUTE,
    faultAttribute: FAULT_ATTRIBUTE,
    register: register,
    registered: registered,
    names: names,
    wanted: wanted,
    reasonFor: reasonFor,
    hostFor: hostFor,
    mount: mount,
    open: open,
    mountAll: mountAll,
    faults: faults,
    forget: forget
  };
})(window, document);
