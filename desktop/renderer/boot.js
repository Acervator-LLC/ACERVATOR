// Fills the History surface from the Python backend.
//
// `history_panel.js` has already defined `acervatorSetState` and drawn
// its empty state by the time this runs. This asks the backend for the
// view model and pushes it in; the panel draws whatever it is given and
// derives nothing.

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

  global.acervatorReload = load;
  load();
})(window);
