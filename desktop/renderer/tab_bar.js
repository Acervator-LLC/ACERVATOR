// The shell's navigation: one tab per registered screen, one screen on show.
//
// The tab set is `acervatorPanelHost.screens()` — the generated manifest kept
// to the modules that registered as a screen — so the bar holds no list of its
// own and a module that lands or leaves moves the bar with it. A panel that
// registers as chrome draws outside the bar and gets no tab. A tab's label is
// its module name with a trailing `_tab` dropped and each word capitalised.
//
// `apply` takes the tab book the running application reports and narrows the
// bar to it: the order and every label come from the application, and each tab
// is filled by the registered screen calling the bridge method the application
// serves that tab from. A screen calling none of those methods draws under no
// tab; `unclaimed` names an application tab no registered screen draws.
//
// The buttons are drawn by `acervatorMainWindow.renderTabBar`, the one React
// bar both the shell and the Qt window use, so the two cannot drift.
//
// Selecting a tab shows that screen's host element and every element declaring
// itself a part of that screen, and hides the rest. A panel is asked for its
// view model the first time its tab is selected.

"use strict";

(function (global) {
  var TAB_ATTRIBUTE = "data-tab";
  var SELECTED_ATTRIBUTE = "data-selected";
  var FUNCTION_KIND = "function";
  var opened = {};
  var current = null;
  var bar = null;
  var container = null;
  var onMove = null;
  var ordered = null;
  var labels = {};
  var missing = [];

  function host() {
    return global.acervatorPanelHost || null;
  }

  function react() {
    return global.acervatorMainWindow || null;
  }

  function names() {
    if (ordered !== null) {
      return ordered.slice();
    }
    var found = host();
    return found ? found.screens() : [];
  }

  function label(name) {
    if (Object.prototype.hasOwnProperty.call(labels, name)) {
      return labels[name];
    }
    var drawn = react();
    return drawn === null ? String(name) : drawn.label(name);
  }

  function drawnBy(method) {
    var found = host();
    var screens = found === null ? [] : found.screens();
    for (var index = 0; index < screens.length; index++) {
      if (found.methodOf(screens[index]) === method) {
        return screens[index];
      }
    }
    return null;
  }

  // The application's own tab book decides the order and every label. A tab
  // no registered screen draws is left off the bar and named by `unclaimed`.
  function apply(appTabs, appMethods) {
    var listed = Object.prototype.toString.call(appTabs) === "[object Array]";
    if (host() === null || !listed || !appMethods) {
      return names();
    }
    ordered = [];
    labels = {};
    missing = [];
    for (var index = 0; index < appTabs.length; index++) {
      var drawer = drawnBy(appMethods[appTabs[index]]);
      if (drawer === null) {
        missing.push(appTabs[index]);
        continue;
      }
      ordered.push(drawer);
      labels[drawer] = appTabs[index];
    }
    if (bar !== null && container !== null) {
      if (ordered.indexOf(current) < 0) {
        current = null;
      }
      draw();
      if (current === null && ordered.length) {
        select(ordered[0]);
      }
    }
    return names();
  }

  function unclaimed() {
    return missing.slice();
  }

  function elements(attribute) {
    if (container === null) {
      return [];
    }
    return Array.prototype.slice.call(
      container.querySelectorAll("[" + attribute + "]")
    );
  }

  // Every element the bar shows and hides: a screen's host, and any mount
  // declared a part of that screen.
  function governed() {
    var found = host();
    if (found === null) {
      return [];
    }
    return elements(found.hostAttribute).concat(elements(found.partAttribute));
  }

  function screenOf(element) {
    var found = host();
    return (
      element.getAttribute(found.hostAttribute) ||
      element.getAttribute(found.partAttribute)
    );
  }

  function visible() {
    var shown = [];
    var all = governed();
    for (var index = 0; index < all.length; index++) {
      var name = screenOf(all[index]);
      if (!all[index].hidden && shown.indexOf(name) < 0) {
        shown.push(name);
      }
    }
    return shown;
  }

  function show(name) {
    var all = governed();
    for (var index = 0; index < all.length; index++) {
      all[index].hidden = screenOf(all[index]) !== name;
    }
  }

  function draw() {
    var drawn = react();
    var found = names();
    if (bar === null || drawn === null) {
      return found;
    }
    drawn.renderTabBar(bar, {
      names: found,
      labels: labels,
      selected: current,
      onSelect: select,
      onMove: onMove
    });
    return found;
  }

  function mark() {
    draw();
  }

  function select(name) {
    if (host() === null || container === null || names().indexOf(name) < 0) {
      return Promise.resolve(false);
    }
    current = name;
    var target = host().hostFor(container, name);
    show(name);
    mark();
    if (opened[name] === undefined) {
      opened[name] = host().open(name, target);
    }
    return opened[name];
  }

  function build(barElement, panelContainer, moveHandler) {
    if (!barElement || !panelContainer || host() === null) {
      return [];
    }
    bar = barElement;
    container = panelContainer;
    onMove = typeof moveHandler === FUNCTION_KIND ? moveHandler : null;
    bar.setAttribute("role", "tablist");
    var found = draw();
    if (found.length) {
      select(found[0]);
    }
    return found;
  }

  function selected() {
    return current;
  }

  function forget() {
    var drawn = react();
    if (drawn !== null) {
      drawn.forget();
    }
    opened = {};
    current = null;
    bar = null;
    container = null;
    onMove = null;
    ordered = null;
    labels = {};
    missing = [];
  }

  global.acervatorTabBar = {
    tabAttribute: TAB_ATTRIBUTE,
    selectedAttribute: SELECTED_ATTRIBUTE,
    names: names,
    label: label,
    build: build,
    apply: apply,
    unclaimed: unclaimed,
    select: select,
    selected: selected,
    visible: visible,
    forget: forget
  };
})(window);
