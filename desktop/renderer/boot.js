// Fills the History surface from the Python backend, and puts the design
// tokens on the page for every panel to skin from.
//
// `history_panel.js` has already defined `acervatorSetState` and drawn
// its empty state by the time this runs. This asks the backend for the
// view model and pushes it in; the panel draws whatever it is given and
// derives nothing.
//
// The tokens are asked for once here. `design_tokens.js` writes each one
// onto the root element as a CSS custom property under its own name, so
// a stylesheet reads `var(--SURFACE_0)` and no panel carries a colour.

"use strict";

(function (global) {
  var METHOD = "history.view_model";

  function showError(message) {
    var box = document.getElementById("bridge-error");
    box.textContent = "Backend unreachable: " + message;
    box.hidden = false;
  }

  function load() {
    if (!global.acervator || typeof global.acervator.call !== "function") {
      showError("the preload bridge is not present");
      return Promise.resolve(null);
    }
    // No `chrome` key, so the panel draws its own summary, filters and
    // pager. The Qt host suppressed all three and supplied its own.
    return global.acervator
      .call(METHOD, { page: 0 })
      .then(function (model) {
        global.acervatorSetState(model);
        return model;
      })
      .catch(function (err) {
        showError(err.message);
        return null;
      });
  }

  function loadTokens() {
    if (typeof global.acervatorLoadTokens !== "function") {
      return Promise.resolve(null);
    }
    return global.acervatorLoadTokens().then(function (model) {
      var reason = global.acervatorTokens.loadError();
      if (reason) {
        showError(reason);
        return null;
      }
      global.acervatorTokens.apply(document.documentElement);
      return model;
    });
  }

  global.acervatorReload = load;
  global.acervatorReloadTokens = loadTokens;
  loadTokens();
  load();
})(window);
