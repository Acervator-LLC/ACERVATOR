// The Proof of Accumulation tab's empty state, as the Python surface serves it.
//
// Every word on screen comes from the payload. The module carries the
// bridge method name and nothing else a reader would see.
(function (global) {
  "use strict";

  var METHOD = "proof_of_accumulation_tab.state";

  var ACCESSIBLE_NAME = "accessible_name";
  var BUILT = "built";
  var HEADING = "heading";
  var ISSUE = "issue";
  var ISSUE_TEXT = "issue_text";
  var METHOD_FIELD = "method";
  var STATE_TEXT = "state_text";

  var DECLARED_FIELDS = [
    ACCESSIBLE_NAME,
    BUILT,
    HEADING,
    ISSUE,
    ISSUE_TEXT,
    METHOD_FIELD,
    STATE_TEXT
  ];

  var MISSING_FAULT = "missing";
  var NULL_FAULT = "null";
  var NOT_AN_OBJECT_FAULT = "not-an-object";
  // Raised when the payload claims a built tab this module cannot draw.
  var CLAIMS_BUILT_FAULT = "claims-built";

  var NO_BRIDGE = "the preload bridge is not present";

  var TAB_CLASS = "acervator-empty-tab";
  var HEADING_CLASS = "acervator-empty-tab-heading";
  var STATE_CLASS = "acervator-empty-tab-state";
  var ISSUE_CLASS = "acervator-empty-tab-issue";

  var PART_ATTR = "data-part";
  var BUILT_ATTR = "data-built";
  var ISSUE_ATTR = "data-issue";

  var HEADING_PART = "heading";
  var STATE_PART = "state";
  var ISSUE_PART = "issue";

  var held = null;
  var tabFaults = [];
  var loadFault = null;
  var asked = null;
  var roots = [];

  function isPlainObject(value) {
    return value !== null && typeof value === "object" && !Array.isArray(value);
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

  function part(className, name) {
    var props = { className: className };
    props[PART_ATTR] = name;
    return props;
  }

  function EmptyTab(props) {
    if (!isPlainObject(props.model)) {
      return null;
    }
    var model = props.model;
    var tabProps = {
      className: TAB_CLASS,
      "aria-label": text(model[ACCESSIBLE_NAME])
    };
    tabProps[BUILT_ATTR] = text(model[BUILT]);
    tabProps[ISSUE_ATTR] = text(model[ISSUE]);
    return element(
      "section",
      tabProps,
      element("h1", part(HEADING_CLASS, HEADING_PART), text(model[HEADING])),
      element("p", part(STATE_CLASS, STATE_PART), text(model[STATE_TEXT])),
      element("p", part(ISSUE_CLASS, ISSUE_PART), text(model[ISSUE_TEXT]))
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
    if (model[BUILT] === true) {
      tabFaults.push(fault(BUILT, CLAIMS_BUILT_FAULT, kindOf(model[BUILT])));
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

  function setProofOfAccumulationTab(model) {
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
  function loadProofOfAccumulationTab(params) {
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
        setProofOfAccumulationTab(model);
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
      root.render(element(EmptyTab, { model: payload }));
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
      render: renderTab,
      load: loadProofOfAccumulationTab,
      loadError: function () {
        return loadFault;
      }
    });
  }

  global.acervatorSetProofOfAccumulationTab = setProofOfAccumulationTab;
  global.acervatorLoadProofOfAccumulationTab = loadProofOfAccumulationTab;
  global.acervatorProofOfAccumulationTab = {
    method: METHOD,
    EmptyTab: EmptyTab,
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
