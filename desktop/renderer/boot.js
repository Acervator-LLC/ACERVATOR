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
//
// Every other converted panel is drawn by `panel_host.js` into `#panels`,
// one host element each, and only when the bridge is there to answer.
//
// `tab_bar.js` puts one tab in `#tabs` for each screen and shows the
// selected one on its own. `acervatorMountPanels` still draws them all
// at once for a caller that wants the whole set.
//
// A panel that registers as chrome takes no tab. It is drawn once into
// `#chrome`, above the bar, and stays there whichever tab is selected.

"use strict";

(function (global) {
  var METHOD = "history.view_model";
  var PANELS_ID = "panels";
  var TABS_ID = "tabs";
  var CHROME_ID = "chrome";

  function hasBridge() {
    return Boolean(global.acervator) && typeof global.acervator.call === "function";
  }

  function showError(message) {
    var box = document.getElementById("bridge-error");
    box.textContent = "Backend unreachable: " + message;
    box.hidden = false;
  }

  function load() {
    if (!hasBridge()) {
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

  // Every panel the manifest names and a module registered, each into its
  // own host element under `#panels`. The History surface keeps `#root`.
  function mountPanels() {
    if (!global.acervatorPanelHost) {
      showError("the panel host is not present");
      return Promise.resolve([]);
    }
    return global.acervatorPanelHost.mountAll(
      document.getElementById(PANELS_ID)
    );
  }

  // Every panel that registered as chrome, drawn into `#chrome` above the
  // bar. No tab selection reaches it.
  function buildChrome() {
    if (!global.acervatorPanelHost) {
      showError("the panel host is not present");
      return Promise.resolve([]);
    }
    var host = global.acervatorPanelHost;
    var area = document.getElementById(CHROME_ID);
    var asked = host.chrome();
    var opened = [];
    for (var index = 0; index < asked.length; index++) {
      opened.push(host.open(asked[index], host.hostFor(area, asked[index])));
    }
    return Promise.all(opened).then(function () {
      return asked;
    });
  }

  function buildTabs() {
    if (!global.acervatorTabBar) {
      showError("the tab bar is not present");
      return [];
    }
    return global.acervatorTabBar.build(
      document.getElementById(TABS_ID),
      document.getElementById(PANELS_ID)
    );
  }

  global.acervatorReload = load;
  global.acervatorReloadTokens = loadTokens;
  global.acervatorMountPanels = mountPanels;
  global.acervatorBuildChrome = buildChrome;
  global.acervatorBuildTabs = buildTabs;
  loadTokens();
  load();
  if (hasBridge()) {
    buildChrome();
    buildTabs();
  }
})(window);
