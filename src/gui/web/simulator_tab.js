// The Sim tab: the Trading tab's panes, drawn from the Python surface.
//
// Every value on screen comes from the payload simulator_tab_surface builds.
// The two chart windows scale the surface's unit-square points, so this side
// and the Qt side place the same points.
(function (global) {
  "use strict";

  var METHOD = "simulator_tab.state";

  var ACCESSIBLE_NAME = "accessible_name";
  var BUILT = "built";
  var FLEET = "fleet";
  var HEADING = "heading";
  var INDICATORS = "indicators";
  var ISSUE = "issue";
  var LAYER = "layer";
  var LAYERS = "layers";
  var METHOD_FIELD = "method";
  var PANES = "panes";
  var PLAYBACK = "playback";
  var PRIVACY_BUTTON = "privacy_button";
  var REPLAY_LOG = "replay_log";
  var RESERVED_ROWS = "reserved_rows";
  var SKIN = "skin";
  var TABLET = "tablet";
  var TABLETS = "tablets";
  var VWAP = "vwap";

  var DECLARED_FIELDS = [
    ACCESSIBLE_NAME,
    BUILT,
    FLEET,
    HEADING,
    INDICATORS,
    ISSUE,
    LAYER,
    LAYERS,
    METHOD_FIELD,
    PANES,
    PLAYBACK,
    PRIVACY_BUTTON,
    REPLAY_LOG,
    RESERVED_ROWS,
    SKIN,
    TABLET,
    TABLETS,
    VWAP
  ];

  var MISSING_FAULT = "missing";
  var NULL_FAULT = "null";
  var NOT_AN_OBJECT_FAULT = "not-an-object";

  var NO_BRIDGE = "the preload bridge is not present";

  var FLIP_ACTION = "flip_layer";
  var TABLET_ACTION = "choose_tablet";
  var PRIVACY_ACTION = "toggle_privacy";
  var ACTION_PREFIX = "acervator-act:";

  // The names the Qt widget gives the same parts, so one reader addresses both.
  var NAMES = {
    tab: "Sim",
    privacyButton: "sim-privacy-button",
    newsRow: "sim-news-ticker-row",
    poolRow: "sim-data-pool-row",
    fleetLabel: "sim-fleet-label",
    fleetTable: "sim-fleet-table",
    fleetEmpty: "sim-fleet-empty",
    tabletLabel: "sim-tablet-label",
    tabletSelector: "sim-tablet-selector",
    flipButton: "sim-flip-button",
    indicatorPane: "sim-indicator-pane",
    indicatorTitle: "sim-indicator-title",
    indicatorSummary: "sim-indicator-summary",
    indicatorTables: ["sim-indicator-table-a", "sim-indicator-table-b"],
    vwapView: "sim-vwap-view",
    playbackView: "sim-playback-view",
    replayTitle: "sim-replay-title",
    replayLog: "sim-replay-log"
  };

  var VIEW_BOX = "0 0 1000 1000";
  var LINE_WIDTH = 6;
  var WICK_WIDTH = 3;
  var UNIT = 1000;

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

  function text(value) {
    return value === null || value === undefined ? undefined : String(value);
  }

  function element() {
    return global.React.createElement.apply(null, arguments);
  }

  function skinStyle(skin) {
    var style = {};
    Object.keys(skin || {}).forEach(function (name) {
      style[name] = skin[name];
    });
    return style;
  }

  function postAction(action, value) {
    global.console.log(
      ACTION_PREFIX + JSON.stringify({ key: action, value: value })
    );
  }

  function pressable(action, value) {
    var props = {
      "data-action": action,
      onClick: function () {
        postAction(action, value);
      }
    };
    if (value !== undefined) {
      props["data-value"] = value;
    }
    return props;
  }

  function PrivacyRow(props) {
    return element(
      "div",
      { className: "sim-strip-row" },
      element(
        "button",
        Object.assign(
          {
            "aria-label": NAMES.privacyButton,
            "data-part": NAMES.privacyButton,
            "data-masked": String(props.button.masked),
            key: "privacy"
          },
          pressable(PRIVACY_ACTION)
        ),
        text(props.button.text)
      )
    );
  }

  // The crypto news ticker and the data pool line are not copied; their rows
  // keep their height and hold nothing.
  function ReservedRows(props) {
    var names = [NAMES.newsRow, NAMES.poolRow];
    return props.rows.map(function (row, index) {
      return element("div", {
        key: names[index],
        "aria-label": names[index],
        "data-part": names[index],
        "data-row-name": text(row.name),
        style: { height: String(row.height_px) + "px" }
      });
    });
  }

  function FleetTable(props) {
    var fleet = props.fleet;
    var head = element(
      "tr",
      null,
      fleet.columns.map(function (label, index) {
        var width = fleet.fixed_widths[String(index)];
        return element(
          "th",
          {
            key: "col" + index,
            "data-column": String(index),
            "data-fixed-width": width === undefined ? undefined : String(width)
          },
          text(label)
        );
      })
    );
    var body = (fleet.rows || []).map(function (row, index) {
      return element(
        "tr",
        { key: "row" + index },
        (row.cells || []).map(function (cell, cellIndex) {
          return element("td", { key: "cell" + cellIndex }, text(cell));
        })
      );
    });
    return element(
      "div",
      null,
      element(
        "div",
        { "aria-label": NAMES.fleetLabel, "data-part": NAMES.fleetLabel },
        text(fleet.label)
      ),
      element(
        "table",
        {
          "aria-label": NAMES.fleetTable,
          "data-part": NAMES.fleetTable,
          "data-column-count": String(fleet.column_count),
          "data-row-count": String(fleet.row_count)
        },
        element("thead", null, head),
        element("tbody", null, body)
      ),
      fleet.row_count === 0
        ? element(
            "div",
            { "aria-label": NAMES.fleetEmpty, "data-part": NAMES.fleetEmpty },
            text(fleet.empty_text)
          )
        : null
    );
  }

  function TabletSelector(props) {
    return element(
      "select",
      {
        "aria-label": NAMES.tabletSelector,
        "data-part": NAMES.tabletSelector,
        "data-chosen": props.chosen === null ? undefined : text(props.chosen.key),
        value: props.chosen === null ? "" : String(props.chosen.key),
        onChange: function (event) {
          postAction(TABLET_ACTION, event.target.value);
        }
      },
      props.tablets.map(function (row) {
        return element(
          "option",
          { key: row.key, value: row.key },
          text(row.asset + " " + row.year + " " + row.exchange_id)
        );
      })
    );
  }

  function IndicatorTable(props) {
    var spec = props.spec;
    return element(
      "table",
      {
        "aria-label": props.name,
        "data-part": props.name,
        "data-column-count": String(spec.titles.length),
        "data-row-count": String(spec.rows.length)
      },
      element(
        "thead",
        null,
        element(
          "tr",
          null,
          spec.titles.map(function (title, index) {
            return element("th", { key: "t" + index }, text(title));
          })
        )
      ),
      element(
        "tbody",
        null,
        spec.rows.map(function (row, rowIndex) {
          return element(
            "tr",
            { key: "r" + rowIndex },
            row.cells.map(function (cell, cellIndex) {
              return element(
                "td",
                {
                  key: "c" + cellIndex,
                  title: text(cell.tooltip),
                  style: { color: cell.text_color }
                },
                text(cell.text)
              );
            })
          );
        })
      )
    );
  }

  function IndicatorPane(props) {
    var panel = props.panel;
    return element(
      "div",
      { "aria-label": NAMES.indicatorPane, "data-part": NAMES.indicatorPane },
      element(
        "div",
        { "aria-label": NAMES.indicatorTitle, "data-part": NAMES.indicatorTitle },
        text(panel.title_text)
      ),
      element(
        "div",
        {
          "aria-label": NAMES.indicatorSummary,
          "data-part": NAMES.indicatorSummary
        },
        text(panel.summary_text)
      ),
      panel.tables.map(function (spec, index) {
        return element(IndicatorTable, {
          key: NAMES.indicatorTables[index],
          name: NAMES.indicatorTables[index],
          spec: spec
        });
      })
    );
  }

  function pathOf(points) {
    var parts = [];
    var pen = "M";
    points.forEach(function (point) {
      if (point === null) {
        pen = "M";
        return;
      }
      parts.push(pen + (point[0] * UNIT).toFixed(3) + " " + (point[1] * UNIT).toFixed(3));
      pen = "L";
    });
    return parts.join(" ");
  }

  function VwapView(props) {
    var window_ = props.vwap;
    return element(
      "svg",
      {
        "aria-label": NAMES.vwapView,
        "data-part": NAMES.vwapView,
        "data-point-count": String(window_.point_count),
        viewBox: VIEW_BOX,
        preserveAspectRatio: "none"
      },
      element("path", {
        "data-line": "close",
        d: pathOf(window_.close_points),
        fill: "none",
        stroke: "var(--sim-close-line)",
        strokeWidth: LINE_WIDTH
      }),
      element("path", {
        "data-line": "vwap",
        d: pathOf(window_.vwap_points),
        fill: "none",
        stroke: "var(--sim-vwap-line)",
        strokeWidth: LINE_WIDTH
      })
    );
  }

  function PlaybackView(props) {
    var window_ = props.playback;
    var shapes = window_.candles;
    var bodyWidth = shapes.length > 0 ? (UNIT / shapes.length) * 0.7 : 1;
    return element(
      "svg",
      {
        "aria-label": NAMES.playbackView,
        "data-part": NAMES.playbackView,
        "data-candle-count": String(window_.candle_count),
        viewBox: VIEW_BOX,
        preserveAspectRatio: "none"
      },
      shapes.map(function (shape, index) {
        var colour = shape.up ? "var(--sim-candle-up)" : "var(--sim-candle-down)";
        var x = shape.x * UNIT;
        var top = shape.body_top * UNIT;
        var bottom = shape.body_bottom * UNIT;
        return element(
          "g",
          { key: "candle" + index, "data-up": String(shape.up) },
          element("line", {
            x1: x,
            x2: x,
            y1: shape.wick_top * UNIT,
            y2: shape.wick_bottom * UNIT,
            stroke: colour,
            strokeWidth: WICK_WIDTH
          }),
          element("rect", {
            x: x - bodyWidth / 2,
            y: top,
            width: bodyWidth,
            height: Math.max(bottom - top, 1),
            fill: colour
          })
        );
      })
    );
  }

  function ReplayLog(props) {
    return element(
      "div",
      null,
      element(
        "div",
        { "aria-label": NAMES.replayTitle, "data-part": NAMES.replayTitle },
        text(props.log.title)
      ),
      element(
        "pre",
        { "aria-label": NAMES.replayLog, "data-part": NAMES.replayLog },
        props.log.lines.join("\n")
      )
    );
  }

  function SimulatorTab(props) {
    if (!isPlainObject(props.model)) {
      return null;
    }
    var model = props.model;
    var panes = model[PANES];
    var showing = model[LAYER];
    return element(
      "section",
      {
        className: "acervator-simulator-tab",
        "aria-label": text(model[ACCESSIBLE_NAME]),
        "data-built": text(model[BUILT]),
        "data-issue": text(model[ISSUE]),
        "data-layer": text(showing),
        style: skinStyle(model[SKIN])
      },
      element(
        "div",
        { className: "sim-fleet-pane" },
        element(PrivacyRow, { button: model[PRIVACY_BUTTON] }),
        element(ReservedRows, { rows: model[RESERVED_ROWS] }),
        element(FleetTable, { fleet: model[FLEET] })
      ),
      element(
        "div",
        { className: "sim-layer-pane" },
        element(
          "div",
          { className: "sim-layer-controls" },
          element(
            "span",
            { "aria-label": NAMES.tabletLabel, "data-part": NAMES.tabletLabel },
            text(panes.tablet_label_text)
          ),
          element(TabletSelector, {
            tablets: model[TABLETS],
            chosen: model[TABLET] === undefined ? null : model[TABLET]
          }),
          element(
            "button",
            Object.assign(
              {
                "aria-label": NAMES.flipButton,
                "data-part": NAMES.flipButton
              },
              pressable(FLIP_ACTION)
            ),
            text(panes.flip_button_text)
          )
        ),
        showing === "indicators"
          ? element(IndicatorPane, { panel: model[INDICATORS] })
          : element(
              "div",
              { className: "sim-chart-layer" },
              element(VwapView, { vwap: model[VWAP] }),
              element(PlaybackView, { playback: model[PLAYBACK] })
            )
      ),
      element(ReplayLog, { log: model[REPLAY_LOG] })
    );
  }

  function checkFields(model) {
    DECLARED_FIELDS.forEach(function (field) {
      if (!owns(model, field)) {
        tabFaults.push(fault(field, MISSING_FAULT, null));
        return;
      }
      if (model[field] === null && field !== TABLET) {
        tabFaults.push(fault(field, NULL_FAULT, null));
      }
    });
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

  function setSimulatorTab(model) {
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
  function loadSimulatorTab(params) {
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
        setSimulatorTab(model);
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
      root.render(element(SimulatorTab, { model: payload }));
    });
    return target;
  }

  function forget() {
    held = null;
    tabFaults = [];
    loadFault = null;
    asked = null;
  }

  if (global.acervatorPanelHost) {
    global.acervatorPanelHost.register({
      method: METHOD,
      render: renderTab,
      load: loadSimulatorTab,
      loadError: function () {
        return loadFault;
      }
    });
  }

  global.acervatorSetSimulatorTab = setSimulatorTab;
  global.acervatorLoadSimulatorTab = loadSimulatorTab;
  global.acervatorSimulatorTab = {
    method: METHOD,
    SimulatorTab: SimulatorTab,
    names: NAMES,
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
