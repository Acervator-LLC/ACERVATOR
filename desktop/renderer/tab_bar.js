// The shell's navigation: one tab per registered screen, one screen on show.
//
// The tab set is `acervatorPanelHost.screens()` — the generated manifest kept
// to the modules that registered as a screen — so the bar holds no list of its
// own and a module that lands or leaves moves the bar with it. A panel that
// registers as chrome draws outside the bar and gets no tab. A tab's label is
// its module name with a trailing `_tab` dropped and each word capitalised.
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

  function host() {
    return global.acervatorPanelHost || null;
  }

  function react() {
    return global.acervatorMainWindow || null;
  }

  function names() {
    var found = host();
    return found ? found.screens() : [];
  }

  function label(name) {
    var drawn = react();
    return drawn === null ? String(name) : drawn.label(name);
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
  }

  global.acervatorTabBar = {
    tabAttribute: TAB_ATTRIBUTE,
    selectedAttribute: SELECTED_ATTRIBUTE,
    names: names,
    label: label,
    build: build,
    select: select,
    selected: selected,
    visible: visible,
    forget: forget
  };
})(window);
