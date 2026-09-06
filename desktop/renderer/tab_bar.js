// The shell's navigation: one tab per registered screen, one screen on show.
//
// The tab set is `acervatorPanelHost.screens()` — the generated manifest kept
// to the modules that registered as a screen — so the bar holds no list of its
// own and a module that lands or leaves moves the bar with it. A panel that
// registers as chrome draws outside the bar and gets no tab. A tab's label is
// its module name with a trailing `_tab` dropped and each word capitalised.
//
// Selecting a tab shows that screen's host element and every element declaring
// itself a part of that screen, and hides the rest. A panel is asked for its
// view model the first time its tab is selected.

"use strict";

(function (global, doc) {
  var TAB_ATTRIBUTE = "data-tab";
  var SELECTED_ATTRIBUTE = "data-selected";
  var SELECTED_ARIA = "aria-selected";
  var SUFFIX = "_tab";
  var SEPARATOR = "_";
  var SPACE = " ";
  var opened = {};
  var current = null;
  var bar = null;
  var container = null;

  function host() {
    return global.acervatorPanelHost || null;
  }

  function names() {
    var found = host();
    return found ? found.screens() : [];
  }

  function label(name) {
    var text = String(name);
    var at = text.length - SUFFIX.length;
    if (at > 0 && text.slice(at) === SUFFIX) {
      text = text.slice(0, at);
    }
    var words = text.split(SEPARATOR);
    var shown = [];
    for (var index = 0; index < words.length; index++) {
      if (words[index]) {
        shown.push(words[index].charAt(0).toUpperCase() + words[index].slice(1));
      }
    }
    return shown.join(SPACE);
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

  function mark(name) {
    if (bar === null) {
      return;
    }
    var buttons = bar.querySelectorAll("[" + TAB_ATTRIBUTE + "]");
    for (var index = 0; index < buttons.length; index++) {
      var chosen = buttons[index].getAttribute(TAB_ATTRIBUTE) === name;
      buttons[index].setAttribute(SELECTED_ARIA, chosen ? "true" : "false");
      if (chosen) {
        buttons[index].setAttribute(SELECTED_ATTRIBUTE, "true");
      } else {
        buttons[index].removeAttribute(SELECTED_ATTRIBUTE);
      }
    }
  }

  function select(name) {
    if (host() === null || container === null || names().indexOf(name) < 0) {
      return Promise.resolve(false);
    }
    current = name;
    var target = host().hostFor(container, name);
    show(name);
    mark(name);
    if (opened[name] === undefined) {
      opened[name] = host().open(name, target);
    }
    return opened[name];
  }

  function button(name) {
    var made = doc.createElement("button");
    made.setAttribute("type", "button");
    made.setAttribute("role", "tab");
    made.setAttribute(TAB_ATTRIBUTE, name);
    made.textContent = label(name);
    made.addEventListener("click", function () {
      select(name);
    });
    return made;
  }

  function build(barElement, panelContainer) {
    if (!barElement || !panelContainer || host() === null) {
      return [];
    }
    bar = barElement;
    container = panelContainer;
    bar.setAttribute("role", "tablist");
    bar.textContent = "";
    var found = names();
    for (var index = 0; index < found.length; index++) {
      bar.appendChild(button(found[index]));
    }
    if (found.length) {
      select(found[0]);
    }
    return found;
  }

  function selected() {
    return current;
  }

  function forget() {
    opened = {};
    current = null;
    bar = null;
    container = null;
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
})(window, document);
