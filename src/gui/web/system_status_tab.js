// The Status tab's emitter network read-out, as the Python surface serves it.
//
// Two groupings of one payload: a panel per subsystem carrying that
// subsystem's emitter read-outs, and a row per tab carrying the subsystems that
// tab holds. Every word and every number comes from the payload.
(function (global) {
  "use strict";

  var METHOD = "system_status_tab.state";

  var ACCESSIBLE_NAME = "accessible_name";
  var BUILT = "built";
  var FEED = "feed";
  var HEADING = "heading";
  var HEALTH_STATES = "health_states";
  var LABELS = "labels";
  var LEGEND = "legend";
  var METHOD_FIELD = "method";
  var NO_EMITTERS_TEXT = "no_emitters_text";
  var NO_FEED_TEXT = "no_feed_text";
  var NO_RECORDS_TEXT = "no_records_text";
  var SUBSYSTEMS = "subsystems";
  var TABS = "tabs";
  var TOTALS = "totals";

  var DECLARED_FIELDS = [
    ACCESSIBLE_NAME,
    BUILT,
    FEED,
    HEADING,
    HEALTH_STATES,
    LABELS,
    LEGEND,
    METHOD_FIELD,
    NO_EMITTERS_TEXT,
    NO_FEED_TEXT,
    NO_RECORDS_TEXT,
    SUBSYSTEMS,
    TABS,
    TOTALS
  ];

  var MISSING_FAULT = "missing";
  var NULL_FAULT = "null";
  var NOT_AN_OBJECT_FAULT = "not-an-object";
  // Raised when the payload claims a tab that is not built; this module draws
  // a built read-out and has no empty state.
  var CLAIMS_UNBUILT_FAULT = "claims-unbuilt";
  var NOT_A_LIST_FAULT = "not-a-list";

  var NO_BRIDGE = "the preload bridge is not present";

  var TAB_CLASS = "acervator-status-tab";

  var PART_ATTR = "data-part";
  var BUILT_ATTR = "data-built";
  var HEALTH_ATTR = "data-health";
  var SUBSYSTEM_ATTR = "data-subsystem";
  var TAB_ATTR = "data-tab";

  var LABEL_FIELD = 0;
  var LABEL_TEXT = 1;

  var EMITTER_NAME = "name";
  var EMITTER_CADENCE = "cadence";
  var EMITTER_EMITTED = "emitted";
  var EMITTER_FAILED = "failed";
  var EMITTER_LATEST = "latest";
  var EMITTER_FIELDS = [EMITTER_NAME, EMITTER_CADENCE, EMITTER_EMITTED, EMITTER_FAILED, EMITTER_LATEST];

  var HEALTH = "health";
  var EMITTERS = "emitters";
  var SUBSYSTEM = "subsystem";
  var TAB = "tab";
  var INSTALLED = "installed";

  var held = null;
  var tabFaults = [];
  var loadFault = null;
  var asked = null;
  var roots = [];

  function isPlainObject(value) {
    return value !== null && typeof value === "object" && !Array.isArray(value);
  }

  function isList(value) {
    return Array.isArray(value);
  }

  function owns(bag, name) {
    return Object.prototype.hasOwnProperty.call(bag, name);
  }

  function kindOf(value) {
    return value === null ? NULL_FAULT : typeof value;
  }

  function fault(field, kind, detail) {
    return { field: field, fault: kind, detail: detail };
  }

  // Returns undefined for an absent value so no attribute is written.
  function text(value) {
    return value === null || value === undefined ? undefined : String(value);
  }

  function element() {
    return global.React.createElement.apply(null, arguments);
  }

  function part(name, extra) {
    var props = extra || {};
    props[PART_ATTR] = name;
    return props;
  }

  function labelsOf(model) {
    return isPlainObject(model[LABELS]) ? model[LABELS] : {};
  }

  function pairs(labels, name) {
    return isList(labels[name]) ? labels[name] : [];
  }

  // One `label value` item per declared pair, read off `row` by field name.
  function counts(row, labels, name, partName) {
    return pairs(labels, name).map(function (pair) {
      return element(
        "span",
        part(partName + "-" + pair[LABEL_FIELD], { key: pair[LABEL_FIELD] }),
        element("span", part("count-label"), pair[LABEL_TEXT]),
        element("span", part("count-value"), text(row[pair[LABEL_FIELD]]))
      );
    });
  }

  function light(row, model, partName) {
    var state = row[HEALTH];
    var props = part(partName, {});
    props[HEALTH_ATTR] = text(state);
    return element(
      "span",
      props,
      state === null || state === undefined
        ? text(model[NO_RECORDS_TEXT])
        : text(state)
    );
  }

  function emitterRow(emitter) {
    return element(
      "tr",
      part("emitter", { key: String(emitter[EMITTER_NAME]) }),
      EMITTER_FIELDS.map(function (field) {
        return element(
          "td",
          part("emitter-" + field, { key: field }),
          text(emitter[field])
        );
      })
    );
  }

  function emitterTable(row, labels) {
    var columns = pairs(labels, "emitter_columns");
    var emitters = isList(row[EMITTERS]) ? row[EMITTERS] : [];
    return element(
      "table",
      part("emitters"),
      element(
        "thead",
        null,
        element(
          "tr",
          part("emitter-columns"),
          columns.map(function (name, index) {
            return element(
              "th",
              part("emitter-column", { key: index, scope: "col" }),
              text(name)
            );
          })
        )
      ),
      element("tbody", null, emitters.map(emitterRow))
    );
  }

  function subsystemPanel(row, model, labels) {
    var props = part("subsystem", { key: String(row[SUBSYSTEM]) });
    props[SUBSYSTEM_ATTR] = text(row[SUBSYSTEM]);
    props[HEALTH_ATTR] = text(row[HEALTH]);
    return element(
      "section",
      props,
      element(
        "header",
        part("subsystem-header"),
        element("h3", part("subsystem-name"), text(row[SUBSYSTEM])),
        light(row, model, "subsystem-light"),
        element("span", part("subsystem-tab"), text(row[TAB]))
      ),
      element(
        "div",
        part("subsystem-counts"),
        counts(row, labels, "counts", "subsystem-count")
      ),
      emitterTable(row, labels)
    );
  }

  function tabGroup(row, model, labels) {
    var names = isList(row[SUBSYSTEMS]) ? row[SUBSYSTEMS] : [];
    var props = part("tab-group", { key: String(row[TAB]) });
    props[TAB_ATTR] = text(row[TAB]);
    props[HEALTH_ATTR] = text(row[HEALTH]);
    return element(
      "section",
      props,
      element(
        "header",
        part("tab-group-header"),
        element("h3", part("tab-group-name"), text(row[TAB])),
        light(row, model, "tab-group-light"),
        element(
          "span",
          part("tab-group-subsystems"),
          names.length ? names.join(", ") : text(model[NO_EMITTERS_TEXT])
        )
      ),
      element(
        "div",
        part("tab-group-counts"),
        counts(row, labels, "counts", "tab-group-count")
      )
    );
  }

  function feedLine(model, labels) {
    var feed = isPlainObject(model[FEED]) ? model[FEED] : {};
    if (feed[INSTALLED] !== true) {
      return element("p", part("feed"), text(model[NO_FEED_TEXT]));
    }
    return element(
      "p",
      part("feed"),
      counts(feed, labels, "feed", "feed")
    );
  }

  function StatusTab(props) {
    if (!isPlainObject(props.model)) {
      return null;
    }
    var model = props.model;
    var labels = labelsOf(model);
    var tabProps = {
      className: TAB_CLASS,
      "aria-label": text(model[ACCESSIBLE_NAME])
    };
    tabProps[BUILT_ATTR] = text(model[BUILT]);
    var subsystems = isList(model[SUBSYSTEMS]) ? model[SUBSYSTEMS] : [];
    var tabs = isList(model[TABS]) ? model[TABS] : [];
    var totals = isPlainObject(model[TOTALS]) ? model[TOTALS] : {};
    return element(
      "section",
      tabProps,
      element("h1", part("heading"), text(model[HEADING])),
      feedLine(model, labels),
      element(
        "div",
        part("totals"),
        counts(totals, labels, "totals", "total")
      ),
      element("p", part("legend"), text(model[LEGEND])),
      element("h2", part("subsystems-heading"), text(labels[SUBSYSTEMS])),
      element(
        "div",
        part("subsystems"),
        subsystems.map(function (row) {
          return subsystemPanel(row, model, labels);
        })
      ),
      element("h2", part("tabs-heading"), text(labels[TABS])),
      element(
        "div",
        part("tabs"),
        tabs.map(function (row) {
          return tabGroup(row, model, labels);
        })
      )
    );
  }

  function checkFields(model) {
    DECLARED_FIELDS.forEach(function (field) {
      if (!owns(model, field)) {
        tabFaults.push(fault(field, MISSING_FAULT, null));
        return;
      }
      if (model[field] === null) {
        tabFaults.push(fault(field, NULL_FAULT, null));
      }
    });
    [SUBSYSTEMS, TABS].forEach(function (field) {
      if (owns(model, field) && !isList(model[field])) {
        tabFaults.push(fault(field, NOT_A_LIST_FAULT, kindOf(model[field])));
      }
    });
    if (model[BUILT] !== true) {
      tabFaults.push(fault(BUILT, CLAIMS_UNBUILT_FAULT, kindOf(model[BUILT])));
    }
  }

  function heldFieldCount(model) {
    return DECLARED_FIELDS.filter(function (field) {
      return owns(model, field);
    }).length;
  }

  function report() {
    return {
      declared: { fields: DECLARED_FIELDS.length },
      held: { fields: heldFieldCount(held) },
      faults: tabFaults.slice()
    };
  }

  function setSystemStatusTab(model) {
    if (!isPlainObject(model)) {
      held = null;
      tabFaults = [fault(null, NOT_AN_OBJECT_FAULT, kindOf(model))];
      return { declared: null, held: null, faults: tabFaults.slice() };
    }
    held = model;
    tabFaults = [];
    checkFields(model);
    return report();
  }

  // Asks once, and forgets a refused ask so the next mount asks again.
  function loadSystemStatusTab(params) {
    if (asked !== null) {
      return asked;
    }
    if (!global.acervator || typeof global.acervator.call !== "function") {
      loadFault = NO_BRIDGE;
      return Promise.resolve(null);
    }
    asked = global.acervator
      .call(METHOD, isPlainObject(params) ? params : {})
      .then(function (model) {
        loadFault = null;
        setSystemStatusTab(model);
        return model;
      })
      .catch(function (err) {
        loadFault = err.message;
        asked = null;
        return null;
      });
    return asked;
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

  // flushSync so the document is current when renderTab returns.
  function renderTab(target, model) {
    var payload = isPlainObject(model) ? model : held;
    var root = rootFor(target);
    global.ReactDOM.flushSync(function () {
      root.render(element(StatusTab, { model: payload }));
    });
    return target;
  }

  function forget() {
    held = null;
    tabFaults = [];
    loadFault = null;
    asked = null;
  }

  // The shell draws this tab by its module name; the host reads that name
  // off the script tag running now, so it is written down nowhere.
  if (global.acervatorPanelHost) {
    global.acervatorPanelHost.register({
      method: METHOD,
      render: renderTab,
      load: loadSystemStatusTab,
      loadError: function () {
        return loadFault;
      }
    });
  }

  global.acervatorSetSystemStatusTab = setSystemStatusTab;
  global.acervatorLoadSystemStatusTab = loadSystemStatusTab;
  global.acervatorSystemStatusTab = {
    method: METHOD,
    StatusTab: StatusTab,
    declaredFields: function () {
      return DECLARED_FIELDS.slice();
    },
    state: function () {
      return held;
    },
    faults: function () {
      return tabFaults.slice();
    },
    loadError: function () {
      return loadFault;
    },
    isLoaded: function () {
      return held !== null && tabFaults.length === 0;
    },
    renderTab: renderTab,
    forget: forget
  };
})(window);
