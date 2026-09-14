// The Paper tab: the Trading tab's panes, drawn from the Python surface.
//
// Every value on screen comes from the payload paper_trader_tab_surface
// builds. The part names match the Qt widget's, so one reader addresses both.
(function (global) {
  "use strict";

  var METHOD = "paper_trader_tab.state";

  var ACCESSIBLE_NAME = "accessible_name";
  var BALANCE = "balance";
  var BUILT = "built";
  var FEED = "feed";
  var FLEET = "fleet";
  var HEADING = "heading";
  var INDICATORS = "indicators";
  var ISSUE = "issue";
  var LEDGER = "ledger";
  var METHOD_FIELD = "method";
  var PANES = "panes";
  var PRIVACY_BUTTON = "privacy_button";
  var RESERVED_ROWS = "reserved_rows";
  var RUN = "run";
  var SKIN = "skin";
  var SYMBOL = "symbol";
  var SYMBOLS = "symbols";

  var DECLARED_FIELDS = [
    ACCESSIBLE_NAME,
    BALANCE,
    BUILT,
    FEED,
    FLEET,
    HEADING,
    INDICATORS,
    ISSUE,
    LEDGER,
    METHOD_FIELD,
    PANES,
    PRIVACY_BUTTON,
    RESERVED_ROWS,
    RUN,
    SKIN,
    SYMBOL,
    SYMBOLS
  ];

  var MISSING_FAULT = "missing";
  var NULL_FAULT = "null";
  var NOT_AN_OBJECT_FAULT = "not-an-object";

  var NO_BRIDGE = "the preload bridge is not present";

  var SYMBOL_ACTION = "choose_symbol";
  var PRIVACY_ACTION = "toggle_privacy";
  var ACTION_PREFIX = "acervator-act:";

  // The names the Qt widget gives the same parts, so one reader addresses both.
  var NAMES = {
    tab: "Paper",
    privacyButton: "paper-privacy-button",
    newsRow: "paper-news-ticker-row",
    poolRow: "paper-data-pool-row",
    symbolLabel: "paper-symbol-label",
    symbolSelector: "paper-symbol-selector",
    fleetLabel: "paper-fleet-label",
    fleetTable: "paper-fleet-table",
    fleetEmpty: "paper-fleet-empty",
    indicatorPane: "paper-indicator-pane",
    indicatorTitle: "paper-indicator-title",
    indicatorSummary: "paper-indicator-summary",
    indicatorTables: ["paper-indicator-table-a", "paper-indicator-table-b"],
    feedTitle: "paper-feed-title",
    feedLines: "paper-feed-lines",
    balanceTitle: "paper-balance-title",
    balanceTable: "paper-balance-table",
    balanceEmpty: "paper-balance-empty",
    ledgerTitle: "paper-ledger-title",
    ledgerFigures: "paper-ledger-figures",
    ledgerOpening: "paper-ledger-opening",
    runTitle: "paper-run-title",
    runState: "paper-run-state",
    runLines: "paper-run-lines",
    runTable: "paper-run-table"
  };

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
      { className: "paper-strip-row" },
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
  // carry Import Live Fleet and the Start or Stop press.
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

  function SymbolSelector(props) {
    return element(
      "select",
      {
        "aria-label": NAMES.symbolSelector,
        "data-part": NAMES.symbolSelector,
        "data-chosen": text(props.chosen),
        value: String(props.chosen || ""),
        onChange: function (event) {
          postAction(SYMBOL_ACTION, event.target.value);
        }
      },
      props.symbols.map(function (row) {
        return element(
          "option",
          { key: row.symbol, value: row.symbol },
          text(row.symbol + " " + row.timeframe)
        );
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
            { key: "r" + rowIndex, "data-side": text(row.side) },
            row.cells.map(function (cell, cellIndex) {
              return element("td", { key: "c" + cellIndex }, text(cell));
            })
          );
        })
      )
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
            "data-fixed-width": width === undefined ? undefined : String(width),
            style:
              width === undefined ? undefined : { width: String(width) + "px" }
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
      { className: "paper-fleet-table-pane" },
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
      element(
        "div",
        {
          "aria-label": NAMES.fleetEmpty,
          "data-part": NAMES.fleetEmpty,
          hidden: fleet.row_count !== 0
        },
        text(fleet.empty_text)
      )
    );
  }

  function indicatorRows(spec) {
    return (spec.rows || []).map(function (row) {
      return {
        cells: (row.cells || []).map(function (cell) {
          return cell.text;
        })
      };
    });
  }

  function IndicatorPane(props) {
    var panel = props.indicators;
    return element(
      "div",
      {
        className: "paper-indicator-pane",
        "aria-label": NAMES.indicatorPane,
        "data-part": NAMES.indicatorPane
      },
      element(
        "div",
        { className: "paper-pane-head" },
        element(
          "div",
          {
            "aria-label": NAMES.indicatorTitle,
            "data-part": NAMES.indicatorTitle
          },
          text(panel.title_text)
        ),
        element(
          "div",
          {
            "aria-label": NAMES.indicatorSummary,
            "data-part": NAMES.indicatorSummary,
            hidden: !(panel.no_data || {}).text
          },
          text((panel.no_data || {}).text)
        )
      ),
      (panel.tables || []).map(function (spec, index) {
        return element(CellTable, {
          key: NAMES.indicatorTables[index],
          name: NAMES.indicatorTables[index],
          titles: spec.titles || [],
          rows: indicatorRows(spec)
        });
      })
    );
  }

  function LedgerStrip(props) {
    var ledger = props.ledger;
    return element(
      "div",
      { className: "paper-ledger-strip" },
      element(
        "div",
        { "aria-label": NAMES.ledgerTitle, "data-part": NAMES.ledgerTitle },
        text(ledger.title)
      ),
      element(
        "div",
        {
          "aria-label": NAMES.ledgerFigures,
          "data-part": NAMES.ledgerFigures,
          "data-spendable": text(ledger.figures.spendable_usd),
          "data-locked": text(ledger.figures.locked_usd),
          "data-realized": text(ledger.figures.realized_profit_usd),
          "data-mature": text(ledger.figures.mature_profit_usd)
        },
        ledger.opened ? text(ledger.text) : text(ledger.empty_text)
      ),
      element(
        "div",
        { "aria-label": NAMES.ledgerOpening, "data-part": NAMES.ledgerOpening },
        text(ledger.opening_text)
      )
    );
  }

  function FeedPane(props) {
    var feed = props.feed;
    var balance = props.balance;
    return element(
      "div",
      { className: "paper-feed-pane" },
      element(
        "div",
        {
          "aria-label": NAMES.feedTitle,
          "data-part": NAMES.feedTitle,
          "data-venue": text(feed.venue),
          "data-product-id": text(feed.product_id),
          "data-candle-count": String(feed.candle_count),
          "data-asked-at": text(feed.asked_at)
        },
        text(feed.title)
      ),
      element(
        "pre",
        { "aria-label": NAMES.feedLines, "data-part": NAMES.feedLines },
        feed.lines.join("\n")
      ),
      element(LedgerStrip, { ledger: props.ledger }),
      element(
        "div",
        {
          "aria-label": NAMES.balanceTitle,
          "data-part": NAMES.balanceTitle,
          "data-budget": text(balance.budget_text)
        },
        text(balance.title)
      ),
      element(CellTable, {
        name: NAMES.balanceTable,
        titles: balance.columns,
        rows: balance.rows
      }),
      element(
        "div",
        {
          "aria-label": NAMES.balanceEmpty,
          "data-part": NAMES.balanceEmpty,
          hidden: balance.row_count !== 0
        },
        text(balance.empty_text)
      )
    );
  }

  function RunPane(props) {
    var run = props.run;
    return element(
      "div",
      { className: "paper-run-pane" },
      element(
        "div",
        { className: "paper-pane-head" },
        element(
          "div",
          {
            "aria-label": NAMES.runTitle,
            "data-part": NAMES.runTitle,
            "data-state": text(run.state),
            "data-running": String(run.running)
          },
          text(run.title)
        ),
        element(
          "div",
          { "aria-label": NAMES.runState, "data-part": NAMES.runState },
          text(run.state_text)
        )
      ),
      element(
        "pre",
        { "aria-label": NAMES.runLines, "data-part": NAMES.runLines },
        run.lines.join("\n")
      ),
      element(CellTable, {
        name: NAMES.runTable,
        titles: run.columns,
        rows: run.rows
      })
    );
  }

  function PaperTraderTab(props) {
    if (!isPlainObject(props.model)) {
      return null;
    }
    var model = props.model;
    var panes = model[PANES];
    return element(
      "section",
      {
        className: "paper-tab",
        "aria-label": text(model[ACCESSIBLE_NAME]),
        "data-part": NAMES.tab,
        "data-built": String(model[BUILT]),
        "data-issue": String(model[ISSUE]),
        "data-symbol": text(model[SYMBOL]),
        style: skinStyle(model[SKIN])
      },
      element(
        "div",
        { className: "paper-top" },
        element(
          "div",
          { className: "paper-fleet-pane" },
          element(PrivacyRow, { button: model[PRIVACY_BUTTON] }),
          element(
            "div",
            { className: "paper-symbol-row" },
            element(
              "span",
              {
                "aria-label": NAMES.symbolLabel,
                "data-part": NAMES.symbolLabel
              },
              text(panes.symbol_label_text)
            ),
            element(SymbolSelector, {
              chosen: model[SYMBOL],
              symbols: model[SYMBOLS]
            })
          ),
          element(ReservedRows, { rows: model[RESERVED_ROWS] }),
          element(FleetTable, { fleet: model[FLEET] })
        ),
        element(IndicatorPane, { indicators: model[INDICATORS] })
      ),
      element(
        "div",
        { className: "paper-bottom" },
        element(FeedPane, {
          feed: model[FEED],
          balance: model[BALANCE],
          ledger: model[LEDGER]
        }),
        element(RunPane, { run: model[RUN] })
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

  function setPaperTraderTab(model) {
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
  function loadPaperTraderTab(params) {
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
        setPaperTraderTab(model);
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
      root.render(element(PaperTraderTab, { model: payload }));
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
      load: loadPaperTraderTab,
      loadError: function () {
        return loadFault;
      }
    });
  }

  global.acervatorSetPaperTraderTab = setPaperTraderTab;
  global.acervatorLoadPaperTraderTab = loadPaperTraderTab;
  global.acervatorPaperTraderTab = {
    method: METHOD,
    PaperTraderTab: PaperTraderTab,
    names: NAMES,
    FeedPane: FeedPane,
    RunPane: RunPane,
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
