// The Sim tab: the Trading tab's panes, drawn from the Python surface.
//
// Every value on screen comes from the payload simulator_tab_surface builds.
// The two chart windows scale the surface's unit-square points, so this side
// and the Qt side place the same points.
(function (global) {
  "use strict";

  var METHOD = "simulator_tab.state";

  var ACCESSIBLE_NAME = "accessible_name";
  var BACK_TEST = "back_test";
  var BATTERY = "battery";
  var BUILT = "built";
  var FLEET = "fleet";
  var HEADING = "heading";
  var INDICATORS = "indicators";
  var ISSUE = "issue";
  var LAYER = "layer";
  var LAYERS = "layers";
  var METHOD_FIELD = "method";
  var MODE = "mode";
  var MODES = "modes";
  var PANES = "panes";
  var PLAYBACK = "playback";
  var PRIVACY_BUTTON = "privacy_button";
  var REPLAY_LOG = "replay_log";
  var RESERVED_ROWS = "reserved_rows";
  var SKIN = "skin";
  var TABLET = "tablet";
  var TABLETS = "tablets";
  var VALIDATION = "validation";
  var VWAP = "vwap";

  var DECLARED_FIELDS = [
    ACCESSIBLE_NAME,
    BACK_TEST,
    BATTERY,
    BUILT,
    FLEET,
    HEADING,
    INDICATORS,
    ISSUE,
    LAYER,
    LAYERS,
    METHOD_FIELD,
    MODE,
    MODES,
    PANES,
    PLAYBACK,
    PRIVACY_BUTTON,
    REPLAY_LOG,
    RESERVED_ROWS,
    SKIN,
    TABLET,
    TABLETS,
    VALIDATION,
    VWAP
  ];

  var MISSING_FAULT = "missing";
  var NULL_FAULT = "null";
  var NOT_AN_OBJECT_FAULT = "not-an-object";

  var NO_BRIDGE = "the preload bridge is not present";

  var FLIP_ACTION = "flip_layer";
  var TABLET_ACTION = "choose_tablet";
  var MODE_ACTION = "choose_mode";
  var PORTFOLIO_ACTION = "choose_portfolio";
  var SPAN_ACTION = "choose_span";
  var PRIVACY_ACTION = "toggle_privacy";
  var ACTION_PREFIX = "acervator-act:";
  var BACK_TEST_MODE = "back_test";
  var BATTERY_MODE = "portfolio_battery";

  var VALIDATION_COLUMNS = [
    "Bot ID",
    "Symbol",
    "Trade",
    "Candle",
    "Gate row",
    "Lights agreed",
    "Latches"
  ];
  var LIGHT_COLUMNS = ["Bank", "Gate", "Recorded", "Rerun", "Driven by"];

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
    replayLog: "sim-replay-log",
    modeLabel: "sim-mode-label",
    modeSelector: "sim-mode-selector",
    validationTitle: "sim-validation-title",
    validationPrompt: "sim-validation-prompt",
    validationLines: "sim-validation-lines",
    validationTable: "sim-validation-table",
    validationLights: "sim-validation-lights",
    backTestTitle: "sim-back-test-title",
    backTestLines: "sim-back-test-lines",
    backTestTable: "sim-back-test-table",
    batteryRow: "sim-battery-row",
    portfolioLabel: "sim-portfolio-label",
    portfolioSelector: "sim-portfolio-selector",
    spanLabel: "sim-span-label",
    spanSelector: "sim-span-selector",
    batteryTitle: "sim-battery-title",
    batteryLines: "sim-battery-lines",
    batteryTable: "sim-battery-table"
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
  // carry the two ways into whichever mode is showing.
  function ReservedRows(props) {
    var names = [NAMES.newsRow, NAMES.poolRow];
    return props.rows.map(function (row, index) {
      return element(
        "div",
        {
          key: names[index],
          "aria-label": names[index],
          "data-part": names[index],
          "data-row-name": text(row.name),
          style: { height: String(row.height_px) + "px" }
        },
        element(
          "button",
          Object.assign(
            {
              "aria-label": row.button_name,
              "data-part": row.button_name
            },
            pressable(row.action)
          ),
          text(row.text)
        )
      );
    });
  }

  function ModeSelector(props) {
    return element(
      "select",
      {
        "aria-label": NAMES.modeSelector,
        "data-part": NAMES.modeSelector,
        "data-chosen": text(props.chosen),
        value: String(props.chosen),
        onChange: function (event) {
          postAction(MODE_ACTION, event.target.value);
        }
      },
      props.modes.map(function (row) {
        return element(
          "option",
          { key: row.name, value: row.name },
          text(row.text)
        );
      })
    );
  }

  // Both selectors send the same shape the mode selector sends.
  function NameSelector(props) {
    return element(
      "select",
      {
        "aria-label": props.name,
        "data-part": props.name,
        "data-chosen": text(props.chosen),
        value: String(props.chosen),
        onChange: function (event) {
          postAction(props.action, event.target.value);
        }
      },
      props.options.map(function (row) {
        return element("option", { key: row, value: row }, text(row));
      })
    );
  }

  function BatteryRow(props) {
    var battery = props.battery;
    return element(
      "div",
      {
        className: "sim-battery-row",
        "aria-label": NAMES.batteryRow,
        "data-part": NAMES.batteryRow,
        hidden: !props.shown
      },
      element(
        "span",
        { "aria-label": NAMES.portfolioLabel, "data-part": NAMES.portfolioLabel },
        text(props.panes.portfolio_label_text)
      ),
      element(NameSelector, {
        name: NAMES.portfolioSelector,
        action: PORTFOLIO_ACTION,
        chosen: battery.portfolio,
        options: battery.portfolios.map(function (row) {
          return row.name;
        })
      }),
      element(
        "span",
        { "aria-label": NAMES.spanLabel, "data-part": NAMES.spanLabel },
        text(props.panes.span_label_text)
      ),
      element(NameSelector, {
        name: NAMES.spanSelector,
        action: SPAN_ACTION,
        chosen: battery.span,
        options: battery.spans
      })
    );
  }

  function batteryRows(rows) {
    return rows.map(function (row) {
      return {
        verdict: row.verdict,
        cells: [
          row.portfolio,
          row.timeframe,
          row.span_text,
          row.symbols_text,
          row.bars,
          row.ticks,
          row.trades,
          row.baseline_text,
          row.accumulation_text,
          row.improvement_text,
          row.missing_text
        ]
      };
    });
  }

  function BatteryPane(props) {
    var found = props.battery;
    return element(
      "div",
      { className: "sim-battery-pane" },
      element(
        "div",
        {
          "aria-label": NAMES.batteryTitle,
          "data-part": NAMES.batteryTitle,
          "data-ran": String(found.ran)
        },
        text(found.title)
      ),
      element(
        "pre",
        { "aria-label": NAMES.batteryLines, "data-part": NAMES.batteryLines },
        found.lines.join("\n")
      ),
      element(CellTable, {
        name: NAMES.batteryTable,
        titles: found.columns,
        rows: batteryRows(found.rows)
      })
    );
  }

  function backTestRows(rows) {
    return rows.map(function (row) {
      return {
        cells: [
          row.bot_id,
          row.symbol,
          row.tablet_key,
          row.candles_read,
          row.ticks,
          row.scrum_latched + " / " + row.fold_latched,
          row.scrum_trades + " / " + row.fold_trades,
          row.units_text,
          row.cash_text
        ]
      };
    });
  }

  function BackTestPane(props) {
    var found = props.backTest;
    return element(
      "div",
      { className: "sim-back-test-pane" },
      element(
        "div",
        {
          "aria-label": NAMES.backTestTitle,
          "data-part": NAMES.backTestTitle,
          "data-ran": String(found.ran)
        },
        text(found.title)
      ),
      element(
        "pre",
        { "aria-label": NAMES.backTestLines, "data-part": NAMES.backTestLines },
        found.lines.join("\n")
      ),
      element(CellTable, {
        name: NAMES.backTestTable,
        titles: found.columns,
        rows: backTestRows(found.rows)
      })
    );
  }

  function CellTable(props) {
    return element(
      "table",
      {
        "aria-label": props.name,
        "data-part": props.name,
        "data-column-count": String(props.titles.length),
        "data-row-count": String(props.rows.length)
      },
      element(
        "thead",
        null,
        element(
          "tr",
          null,
          props.titles.map(function (title, index) {
            return element("th", { key: "t" + index }, text(title));
          })
        )
      ),
      element(
        "tbody",
        null,
        props.rows.map(function (row, rowIndex) {
          return element(
            "tr",
            {
              key: "r" + rowIndex,
              "data-agrees": text(row.agrees),
              "data-verdict": text(row.verdict)
            },
            row.cells.map(function (cell, cellIndex) {
              return element("td", { key: "c" + cellIndex }, text(cell));
            })
          );
        })
      )
    );
  }

  function validationRows(rows) {
    return rows.map(function (row) {
      return {
        cells: [
          row.bot_id,
          row.symbol,
          row.trade_at,
          row.candle_at,
          row.gate_at,
          row.agreed + " of " + row.light_count,
          row.latches_identically ? "yes" : "no"
        ]
      };
    });
  }

  function lightRows(lights) {
    return lights.map(function (light) {
      return {
        agrees: light.agrees,
        cells: [
          light.bank,
          light.label,
          light.recorded,
          light.rerun,
          light.driven_by
        ]
      };
    });
  }

  function ValidationPane(props) {
    var found = props.validation;
    var lights = found.rows.length > 0 ? found.rows[0].lights : [];
    return element(
      "div",
      { className: "sim-validation-pane" },
      element(
        "div",
        {
          "aria-label": NAMES.validationTitle,
          "data-part": NAMES.validationTitle,
          "data-ran": String(found.ran)
        },
        text(found.title)
      ),
      found.prompt_text
        ? element(
            "div",
            {
              "aria-label": NAMES.validationPrompt,
              "data-part": NAMES.validationPrompt
            },
            text(found.prompt_text)
          )
        : null,
      element(
        "pre",
        {
          "aria-label": NAMES.validationLines,
          "data-part": NAMES.validationLines
        },
        found.lines.join("\n")
      ),
      element(CellTable, {
        name: NAMES.validationTable,
        titles: VALIDATION_COLUMNS,
        rows: validationRows(found.rows)
      }),
      element(CellTable, {
        name: NAMES.validationLights,
        titles: LIGHT_COLUMNS,
        rows: lightRows(lights)
      })
    );
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
        { key: "row" + index, "data-origin": text(row.origin) },
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
        element(
          "div",
          { className: "sim-mode-row" },
          element(
            "span",
            { "aria-label": NAMES.modeLabel, "data-part": NAMES.modeLabel },
            text(panes.mode_label_text)
          ),
          element(ModeSelector, { modes: model[MODES], chosen: model[MODE] })
        ),
        element(BatteryRow, {
          battery: model[BATTERY],
          panes: panes,
          shown: panes.battery_row_shown
        }),
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
      element(
        "div",
        { className: "sim-bottom-pane" },
        element(ReplayLog, { log: model[REPLAY_LOG] }),
        element(
          "div",
          { className: "sim-result-stack", "data-showing": text(model[MODE]) },
          element(
            "div",
            {
              key: "validation",
              hidden:
                model[MODE] === BACK_TEST_MODE || model[MODE] === BATTERY_MODE
            },
            element(ValidationPane, { validation: model[VALIDATION] })
          ),
          element(
            "div",
            { key: "back-test", hidden: model[MODE] !== BACK_TEST_MODE },
            element(BackTestPane, { backTest: model[BACK_TEST] })
          ),
          element(
            "div",
            { key: "battery", hidden: model[MODE] !== BATTERY_MODE },
            element(BatteryPane, { battery: model[BATTERY] })
          )
        )
      )
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
    BackTestPane: BackTestPane,
    BatteryPane: BatteryPane,
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
