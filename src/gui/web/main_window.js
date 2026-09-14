// The main window's own chrome: the tab bar, drawn by React.
//
// `label` derives a tab's text from its screen name -- a trailing `_tab` is
// dropped and each word capitalised. A caller that knows the application's own
// label for a name passes it in `labels`, and that text is drawn instead.
// `renderTabBar` draws one button per name into a host element and marks the
// selected one with `data-selected`.
//
// Both hosts of the bar draw through this module: the Electron shell reaches
// it from `desktop/renderer/tab_bar.js`, and the Qt window reaches it from
// `src/gui/react_main_window.py`. A caller that supplies `onMove` gets
// draggable buttons and is told the index a tab was dropped on.

"use strict";

(function (global) {
  var TAB_ATTRIBUTE = "data-tab";
  var SELECTED_ATTRIBUTE = "data-selected";
  var SELECTED_ARIA = "aria-selected";
  var DRAG_TYPE = "text/plain";
  var SUFFIX = "_tab";
  var SEPARATOR = "_";
  var SPACE = " ";
  var FUNCTION_KIND = "function";

  var roots = [];
  var dragging = null;

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

  function element() {
    return global.React.createElement.apply(null, arguments);
  }

  function TabButton(props) {
    var chosen = props.name === props.selected;
    var made = {
      type: "button",
      role: "tab",
      "aria-label": props.text,
      onClick: function () {
        props.onSelect(props.name);
      }
    };
    made[TAB_ATTRIBUTE] = props.name;
    made[SELECTED_ARIA] = chosen ? "true" : "false";
    made[SELECTED_ATTRIBUTE] = chosen ? "true" : undefined;
    if (typeof props.onMove === FUNCTION_KIND) {
      made.draggable = true;
      made.onDragStart = function (event) {
        dragging = props.at;
        event.dataTransfer.setData(DRAG_TYPE, String(props.at));
      };
      made.onDragOver = function (event) {
        event.preventDefault();
      };
      made.onDrop = function (event) {
        event.preventDefault();
        if (dragging !== null && dragging !== props.at) {
          props.onMove(dragging, props.at);
        }
        dragging = null;
      };
    }
    return element("button", made, props.text);
  }

  function textFor(name, given) {
    return given && typeof given[name] === "string" ? given[name] : label(name);
  }

  function TabBar(props) {
    var made = [];
    for (var index = 0; index < props.names.length; index++) {
      made.push(
        element(TabButton, {
          key: props.names[index],
          at: index,
          name: props.names[index],
          text: textFor(props.names[index], props.labels),
          selected: props.selected,
          onSelect: props.onSelect,
          onMove: props.onMove
        })
      );
    }
    return element(global.React.Fragment, null, made);
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

  function ignore() {
    return null;
  }

  // flushSync so the buttons are on the page when this returns.
  function renderTabBar(target, model) {
    if (!target) {
      return null;
    }
    var root = rootFor(target);
    global.ReactDOM.flushSync(function () {
      root.render(
        element(TabBar, {
          names: Array.isArray(model.names) ? model.names : [],
          labels: model.labels,
          selected: model.selected,
          onSelect:
            typeof model.onSelect === FUNCTION_KIND ? model.onSelect : ignore,
          onMove: model.onMove
        })
      );
    });
    return target;
  }

  function forget() {
    roots.forEach(function (pair) {
      pair.root.unmount();
    });
    roots = [];
    dragging = null;
  }

  global.acervatorMainWindow = {
    tabAttribute: TAB_ATTRIBUTE,
    selectedAttribute: SELECTED_ATTRIBUTE,
    label: label,
    TabBar: TabBar,
    TabButton: TabButton,
    renderTabBar: renderTabBar,
    forget: forget
  };
})(window);
