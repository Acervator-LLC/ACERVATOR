// The History tab's chrome and controls, as the Python surface serves them.
//
// The ROWS are not drawn here. `history_panel.js` is the one table
// renderer, and this module hands it the columns and page off the same
// payload, with the panel's own chrome turned off. Drawing a second
// table here would be the second implementation of History that the
// Python contract exists to prevent.
(function (global) {
  "use strict";

  var METHOD = "history_tab.chrome";
  var PANEL_CHROME = { summary: false, filters: false, pager: false };

  var ACCESSIBLE_NAME = "accessible_name";
  var ACTIONS = "actions";
  var BUTTONS = "buttons";
  var COLUMNS = "columns";
  var EXPORT = "export";
  var FILTERS = "filters";
  var FILTER_GROUP_TITLE = "filter_group_title";
  var LOADED = "loaded";
  var PAGE = "page";
  var PAGER = "pager";
  var PAINTED = "painted";
  var PROGRESS = "progress";
  var SUMMARY = "summary";
  var TITLE = "title";
  var WIDGETS = "widgets";

  var DECLARED_FIELDS = [
    ACCESSIBLE_NAME,
    ACTIONS,
    BUTTONS,
    COLUMNS,
    EXPORT,
    FILTERS,
    FILTER_GROUP_TITLE,
    LOADED,
    PAGE,
    PAGER,
    PAINTED,
    PROGRESS,
    SUMMARY,
    TITLE,
    WIDGETS
  ];

  var COMBOS = "combos";
  var ENABLED = "enabled";
  var KEY = "key";
  var LABEL = "label";
  var OPTIONS = "options";
  var ROWS = "rows";
  var STYLE_SHEET = "style_sheet";
  var TEXT = "text";
  var TOOLTIP = "tooltip";
  var VALUE = "value";
  var VISIBLE = "visible";

  var MISSING_FAULT = "missing";
  var NULL_FAULT = "null";
  var NO_BRIDGE = "no bridge: window.acervator.call is not a function";
  var NO_PANEL = "no table renderer: window.acervatorSetState is not a function";

  // The keys whose value the surface answers without touching an
  // exchange or a file. The other two need the host.
  var BRIDGED = ["apply", "reset", "prev", "next"];

  var SEMICOLON = ";";
  var COLON = ":";
  var QT_ONLY = "q";

  var TAB_CLASS = "acervator-history-tab";
  var FILTERS_CLASS = "acervator-history-filters";
  var SUMMARY_CLASS = "acervator-history-summary";
  var TABLE_CLASS = "acervator-history-table";
  var FOOTER_CLASS = "acervator-history-footer";
  var TABLE_MOUNT_ID = "history-tab-table";

  var h = global.React ? global.React.createElement : null;

  var model = null;
  var modelFaults = [];
  var loadFault = null;
  var asked = null;
  var host = null;
  var root = null;
  var held = {};

  function isPlainObject(value) {
    return value !== null && typeof value === "object" && !Array.isArray(value);
  }

  function owns(bag, name) {
    return Object.prototype.hasOwnProperty.call(bag, name);
  }

  function objectField(bag, field) {
    return isPlainObject(bag) && isPlainObject(bag[field]) ? bag[field] : {};
  }

  function listField(bag, field) {
    return isPlainObject(bag) && Array.isArray(bag[field]) ? bag[field] : [];
  }

  function fault(where, field, why) {
    return { where: where, field: field, why: why };
  }

  function checkDeclared(state) {
    modelFaults = [];
    if (!isPlainObject(state)) {
      modelFaults.push(fault(null, null, MISSING_FAULT));
      return;
    }
    DECLARED_FIELDS.forEach(function (field) {
      if (!owns(state, field)) {
        modelFaults.push(fault(null, field, MISSING_FAULT));
        return;
      }
      if (state[field] === null) {
        modelFaults.push(fault(null, field, NULL_FAULT));
      }
    });
  }

  // A Qt style sheet as a React style object. A value Qt alone
  // understands is dropped rather than handed to the browser.
  function declarations(sheet) {
    var found = [];
    if (typeof sheet !== "string") {
      return found;
    }
    sheet.split(SEMICOLON).forEach(function (one) {
      var parts = one.split(COLON);
      var property = String(parts.shift()).trim();
      var value = parts.join(COLON).trim();
      if (property && value) {
        found.push({ property: property, value: value });
      }
    });
    return found;
  }

  function camelCase(property) {
    return property.replace(/-([a-z])/g, function (all, letter) {
      return letter.toUpperCase();
    });
  }

  function styleOf(sheet) {
    var style = {};
    declarations(sheet).forEach(function (one) {
      if (one.value.slice(0, 1).toLowerCase() === QT_ONLY) {
        return;
      }
      style[camelCase(one.property)] = one.value;
    });
    return style;
  }

  // -- the pieces -------------------------------------------------------

  function Combo(props) {
    var combo = props.combo;
    return h(
      "label",
      { key: combo[KEY], className: "combo", "data-key": combo[KEY] },
      combo[LABEL],
      h(
        "select",
        {
          id: "history-" + combo[KEY],
          value: combo[VALUE],
          onChange: function (event) {
            props.onFilter(combo[KEY], event.target.value);
          }
        },
        (combo[OPTIONS] || []).map(function (option) {
          return h("option", { key: option, value: option }, option);
        })
      )
    );
  }

  function pad(value) {
    return (value < 10 ? "0" : "") + value;
  }

  function stampOf(seconds) {
    var when = new Date(Number(seconds) * 1000);
    return (
      when.getFullYear() +
      "-" +
      pad(when.getMonth() + 1) +
      "-" +
      pad(when.getDate()) +
      "T" +
      pad(when.getHours()) +
      ":" +
      pad(when.getMinutes())
    );
  }

  function secondsOf(stamp) {
    var when = new Date(stamp);
    var epoch = when.getTime();
    return epoch !== epoch ? 0 : Math.floor(epoch / 1000);
  }

  function DateBound(props) {
    var bound = props.bound;
    return h(
      "label",
      { className: "date", "data-key": props.name },
      bound[LABEL],
      h("input", {
        id: "history-" + props.name,
        type: "datetime-local",
        title: bound[TOOLTIP],
        value: stampOf(bound.seconds),
        onChange: function (event) {
          props.onBound(props.name, secondsOf(event.target.value));
        }
      })
    );
  }

  function Button(props) {
    var button = props.button;
    return h(
      "button",
      {
        key: button[KEY],
        id: "history-" + button[KEY],
        disabled: !button[ENABLED],
        title: button[TOOLTIP],
        onClick: function () {
          props.onAct(button[KEY]);
        }
      },
      button[TEXT]
    );
  }

  function FilterBar(props) {
    var filters = objectField(props.state, FILTERS);
    return h(
      "fieldset",
      { className: FILTERS_CLASS },
      h("legend", null, props.state[FILTER_GROUP_TITLE]),
      h(DateBound, {
        key: "from",
        name: "from",
        bound: objectField(filters, "from"),
        onBound: props.onBound
      }),
      h(DateBound, {
        key: "to",
        name: "to",
        bound: objectField(filters, "to"),
        onBound: props.onBound
      }),
      listField(filters, COMBOS).map(function (combo) {
        return h(Combo, { key: combo[KEY], combo: combo, onFilter: props.onFilter });
      }),
      props.buttons.filter(inBar).map(function (button) {
        return h(Button, { key: button[KEY], button: button, onAct: props.onAct });
      })
    );
  }

  function inBar(button) {
    return ["apply", "reset", "refresh"].indexOf(button[KEY]) !== -1;
  }

  function inFooter(button) {
    return !inBar(button);
  }

  function Summary(props) {
    var summary = objectField(props.state, SUMMARY);
    return h(
      "div",
      {
        id: "history-summary",
        className: SUMMARY_CLASS,
        style: styleOf(summary[STYLE_SHEET])
      },
      summary[TEXT]
    );
  }

  function Footer(props) {
    var pager = objectField(props.state, PAGER);
    var progress = objectField(props.state, PROGRESS);
    var ordered = ["prev", "next", "export"];
    var buttons = props.buttons.filter(inFooter).sort(function (left, right) {
      return ordered.indexOf(left[KEY]) - ordered.indexOf(right[KEY]);
    });
    return h(
      "div",
      { className: FOOTER_CLASS },
      h(Button, { key: "prev", button: buttons[0], onAct: props.onAct }),
      h("span", { id: "history-page-label" }, pager[LABEL]),
      h(Button, { key: "next", button: buttons[1], onAct: props.onAct }),
      progress[VISIBLE]
        ? h("progress", { id: "history-progress" })
        : null,
      h(Button, { key: "export", button: buttons[2], onAct: props.onAct })
    );
  }

  function Tab(props) {
    var state = props.state;
    var buttons = listField(state, BUTTONS);
    return h(
      "section",
      { className: TAB_CLASS, "aria-label": state[ACCESSIBLE_NAME] },
      h(FilterBar, {
        state: state,
        buttons: buttons,
        onFilter: props.onFilter,
        onBound: props.onBound,
        onAct: props.onAct
      }),
      h(Summary, { state: state }),
      h("div", { id: TABLE_MOUNT_ID, className: TABLE_CLASS }),
      h(Footer, { state: state, buttons: buttons, onAct: props.onAct })
    );
  }

  // -- the table, drawn by the one renderer that draws tables ------------

  // The Qt table carries no column header until the tab draws a page, so
  // the panel's header row is turned off until `painted`.
  function panelChromeFor(state) {
    return {
      summary: PANEL_CHROME.summary,
      filters: PANEL_CHROME.filters,
      pager: PANEL_CHROME.pager,
      headers: isPlainObject(state) && state[PAINTED] !== false
    };
  }

  function pushRows(state) {
    if (typeof global.acervatorSetState !== "function") {
      loadFault = NO_PANEL;
      return false;
    }
    global.acervatorSetState({
      columns: listField(state, COLUMNS),
      page: objectField(state, PAGE),
      summary: objectField(state, SUMMARY)[TEXT],
      filters: objectField(objectField(state, FILTERS), "values"),
      filter_options: {},
      loaded: state[LOADED],
      chrome: panelChromeFor(state)
    });
    return true;
  }

  // -- the bridge -------------------------------------------------------

  function call(params) {
    if (!global.acervator || typeof global.acervator.call !== "function") {
      loadFault = NO_BRIDGE;
      return Promise.resolve(null);
    }
    return global.acervator
      .call(METHOD, isPlainObject(params) ? params : {})
      .then(function (next) {
        loadFault = null;
        if (isPlainObject(next)) {
          setTab(next);
        }
        return next;
      })
      .catch(function (err) {
        loadFault = err.message;
        return null;
      });
  }

  function loadTab(params) {
    if (asked !== null) {
      return asked;
    }
    asked = call(params).then(function (next) {
      if (next === null) {
        asked = null;
      }
      return next;
    });
    return asked;
  }

  function setTab(next) {
    model = next;
    checkDeclared(next);
    draw();
    return model;
  }

  function bridgedAction(key) {
    return BRIDGED.indexOf(key) !== -1;
  }

  function forget() {
    model = null;
    modelFaults = [];
    loadFault = null;
    asked = null;
    host = null;
    root = null;
    held = {};
  }

  // Refresh needs an exchange and Export needs a file dialog, so a host
  // that can reach those answers them through acervatorHistoryTabHostAction.
  function onAct(key) {
    if (!bridgedAction(key)) {
      if (typeof global.acervatorHistoryTabHostAction === "function") {
        return global.acervatorHistoryTabHostAction(key);
      }
      return null;
    }
    var pager = objectField(model, PAGER);
    var next = { action: key, page: pager[PAGE] };
    if (key === "prev") {
      next.page = pager[PAGE] - 1;
    } else if (key === "next") {
      next.page = pager[PAGE] + 1;
    } else if (key === "reset") {
      // Reset clears what onFilter and onBound held, or the next Apply
      // sends the filter Reset just cleared.
      held.filters = {};
      next.filters = {};
      next.page = 0;
    } else {
      next.filters = held.filters || {};
      next.page = 0;
    }
    next.trades = held.trades || [];
    return call(next);
  }

  function onFilter(key, value) {
    held.filters = held.filters || {};
    held.filters[key] = value;
    return onAct("apply");
  }

  function onBound(name, seconds) {
    held.filters = held.filters || {};
    held.filters[name + "_ts"] = seconds;
    return onAct("apply");
  }

  function draw() {
    if (h === null || model === null || host === null) {
      return null;
    }
    if (root === null) {
      root = global.ReactDOM.createRoot(host);
    }
    // flushSync, as the panel does: the rows are pushed synchronously below,
    // so a scheduled chrome render would trail them by one click.
    global.ReactDOM.flushSync(function () {
      root.render(
        h(Tab, {
          state: model,
          onFilter: onFilter,
          onBound: onBound,
          onAct: onAct
        })
      );
    });
    pushRows(model);
    if (typeof global.acervatorHistoryTabDrawn === "function") {
      global.acervatorHistoryTabDrawn();
    }
    return root;
  }

  function renderTab(node, params) {
    host = node;
    held = isPlainObject(params) ? params : {};
    return draw();
  }

  // A Qt host replaces acervatorHistoryTabHostAction and acervatorHistoryTabDrawn.
  global.acervatorHistoryTabHostAction = function () {
    return null;
  };

  global.acervatorHistoryTabDrawn = function () {
    return false;
  };

  // The shell draws this tab by its module name; the host reads that name
  // off the script tag running now, so it is written down nowhere.
  if (global.acervatorPanelHost) {
    global.acervatorPanelHost.register({
      method: METHOD,
      render: function (target) {
        return renderTab(target, {});
      },
      load: loadTab,
      loadError: function () {
        return loadFault;
      }
    });
  }

  global.acervatorHistoryTab = {
    method: METHOD,
    panelChrome: PANEL_CHROME,
    panelChromeFor: panelChromeFor,
    Tab: Tab,
    FilterBar: FilterBar,
    Summary: Summary,
    Footer: Footer,
    Button: Button,
    Combo: Combo,
    DateBound: DateBound,
    declaredFields: function () {
      return DECLARED_FIELDS.slice();
    },
    bridgedActions: function () {
      return BRIDGED.slice();
    },
    isBridged: bridgedAction,
    declarations: declarations,
    styleOf: styleOf,
    setTab: setTab,
    loadTab: loadTab,
    renderTab: renderTab,
    stampOf: stampOf,
    secondsOf: secondsOf,
    pushRows: pushRows,
    state: function () {
      return model;
    },
    faults: function () {
      return modelFaults.slice();
    },
    loadError: function () {
      return loadFault;
    },
    isLoaded: function () {
      return model !== null && modelFaults.length === 0;
    },
    forget: forget
  };
})(window);
