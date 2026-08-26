// React History panel. Issue #128 unit R4.
//
// This file RENDERS. It does not compute. Every string on screen is a
// `text` field the Python contract already produced, and every colour is
// its `color` field. Deriving a cost, a grade or a colour here would be a
// second implementation of the thing R3 exists to be the only one of.
(function (global) {
  "use strict";

  var h = global.React.createElement;

  // The one shape the bridge may deliver. A payload missing any of these
  // renders the error banner instead of a half-drawn table.
  var REQUIRED_KEYS = [
    "columns",
    "page",
    "summary",
    "filters",
    "filter_options",
    "loaded"
  ];

  function describeBadState(state) {
    if (state === null || state === undefined) {
      return "the bridge delivered no state: Python never called acervatorSetState";
    }
    if (typeof state !== "object") {
      return "the bridge delivered a " + typeof state + ", not an object";
    }
    var missing = REQUIRED_KEYS.filter(function (k) {
      return !(k in state);
    });
    if (missing.length) {
      return "the bridge delivered a payload with no " + missing.join(", ");
    }
    var page = state.page;
    if (!page || !Array.isArray(page.rows)) {
      return "the bridge delivered a page with no rows array";
    }
    if (!Array.isArray(state.columns) || state.columns.length === 0) {
      return "the bridge delivered no columns";
    }
    return null;
  }

  function ErrorBanner(props) {
    return h(
      "div",
      { id: "panel-error", className: "panel-error" },
      "History bridge fault: " + props.reason
    );
  }

  function SummaryStrip(props) {
    return h(
      "div",
      { id: "panel-summary", className: "summary" },
      props.summary
    );
  }

  // The three dropdowns the contract exposes, shown with their live value.
  // They carry `disabled`: the bridge is one-way, so the Qt control bar
  // above the page owns the change events.
  function FilterStrip(props) {
    var opts = props.filterOptions;
    var filters = props.filters;
    var selects = ["exchange", "symbol", "side"].map(function (key) {
      var values = opts[key] || [];
      return h(
        "label",
        { key: key, className: "filter" },
        h("span", { className: "filter-name" }, key),
        h(
          "select",
          {
            id: "filter-" + key,
            "data-filter-key": key,
            value: filters[key],
            disabled: true,
            onChange: function () {},
            title: "Read-only mirror. The Qt control bar owns this filter."
          },
          values.map(function (v) {
            return h("option", { key: v, value: v }, v);
          })
        )
      );
    });
    var dates = h(
      "span",
      { id: "filter-dates", className: "filter-dates" },
      "from " + props.fromText + " to " + props.toText
    );
    return h(
      "div",
      { id: "panel-filters", className: "filters" },
      selects.concat([dates])
    );
  }

  function GateLights(props) {
    var lights = props.lights;
    if (!lights) {
      return null;
    }
    var keys = Object.keys(lights).sort();
    return h(
      "span",
      { className: "gate-lights", "data-light-count": String(keys.length) },
      keys.map(function (k) {
        var light = lights[k];
        var text = light === null || typeof light !== "object" ? String(light) : "";
        return h("i", {
          key: k,
          className: "light",
          "data-light-key": k,
          "data-light-value": text,
          title: k + ": " + text,
          style: { background: "currentColor" }
        });
      })
    );
  }

  function Cell(props) {
    var cell = props.cell;
    var style = {};
    if (cell.color) {
      style.color = cell.color;
    }
    var kids = [cell.text];
    if (props.gateLights) {
      kids.push(h(GateLights, { key: "lights", lights: props.gateLights }));
    }
    return h(
      "td",
      {
        className: "cell cell-" + cell.key,
        "data-col-key": cell.key,
        "data-row-index": String(props.rowIndex),
        "data-cell-color": cell.color === null ? "" : String(cell.color),
        "data-cell-tooltip": cell.tooltip === null ? "" : String(cell.tooltip),
        title: cell.tooltip || "",
        style: style
      },
      kids
    );
  }

  function Row(props) {
    var row = props.row;
    return h(
      "tr",
      {
        className: "row",
        "data-trade-id": row.trade_id,
        "data-row-index": String(props.rowIndex),
        "data-timestamp": String(row.timestamp)
      },
      row.cells.map(function (cell) {
        return h(Cell, {
          key: cell.key,
          cell: cell,
          rowIndex: props.rowIndex,
          gateLights: cell.key === "gates" ? row.gate_lights : null
        });
      })
    );
  }

  function Table(props) {
    var head = h(
      "thead",
      null,
      h(
        "tr",
        null,
        props.columns.map(function (col) {
          return h(
            "th",
            {
              key: col.key,
              "data-col-key": col.key,
              "data-col-index": String(col.index),
              title: col.header_tooltip || ""
            },
            col.header
          );
        })
      )
    );
    var body = h(
      "tbody",
      { id: "panel-rows" },
      props.rows.map(function (row, i) {
        return h(Row, { key: row.trade_id + ":" + i, row: row, rowIndex: i });
      })
    );
    return h("table", { id: "panel-table", className: "history" }, head, body);
  }

  function Pager(props) {
    return h(
      "div",
      { id: "panel-pager", className: "pager" },
      h(
        "button",
        {
          id: "pager-prev",
          disabled: !props.prevEnabled,
          title: "Read-only mirror. The Qt control bar turns the page."
        },
        "Prev"
      ),
      h("span", { id: "pager-label", className: "pager-label" }, props.label),
      h(
        "button",
        {
          id: "pager-next",
          disabled: !props.nextEnabled,
          title: "Read-only mirror. The Qt control bar turns the page."
        },
        "Next"
      ),
      h(
        "span",
        {
          id: "pager-counts",
          "data-page": String(props.page),
          "data-pages": String(props.pages),
          "data-total": String(props.total),
          "data-page-size": String(props.pageSize),
          "data-row-count": String(props.rowCount)
        },
        props.rowCount + " rows on this page"
      )
    );
  }

  function Panel(props) {
    var state = props.state;
    var reason = describeBadState(state);
    if (reason !== null) {
      return h(
        "div",
        { className: "panel", id: "panel-root", "data-render-seq": String(props.seq) },
        h(ErrorBanner, { reason: reason })
      );
    }
    var page = state.page;
    return h(
      "div",
      {
        className: "panel",
        id: "panel-root",
        "data-render-seq": String(props.seq)
      },
      h(SummaryStrip, { summary: state.summary }),
      h(FilterStrip, {
        filters: state.filters,
        filterOptions: state.filter_options,
        fromText: state.from_text,
        toText: state.to_text
      }),
      h(Table, { columns: state.columns, rows: page.rows }),
      h(Pager, {
        label: page.page_label,
        prevEnabled: page.prev_enabled,
        nextEnabled: page.next_enabled,
        page: page.page,
        pages: page.pages,
        total: page.total,
        pageSize: page.page_size,
        rowCount: page.rows.length
      })
    );
  }

  var mount = null;
  var seq = 0;

  function ensureMount() {
    if (mount === null) {
      mount = global.ReactDOM.createRoot(document.getElementById("root"));
    }
    return mount;
  }

  // The bridge's only entry point. Python calls this with a plain object.
  // `flushSync` makes the DOM current before this returns, so a reader
  // that polls right after a push sees this render and not the last one.
  global.acervatorSetState = function (state) {
    seq += 1;
    var root = ensureMount();
    global.ReactDOM.flushSync(function () {
      root.render(h(Panel, { state: state, seq: seq }));
    });
    return seq;
  };

  // Render once with nothing, so a bridge that never fires shows the
  // banner rather than a blank page that agrees with every claim.
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      if (seq === 0) {
        global.acervatorSetState(null);
      }
    });
  } else if (seq === 0) {
    global.acervatorSetState(null);
  }
})(window);
