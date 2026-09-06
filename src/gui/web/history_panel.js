// React History panel. Issue #128 units R4 and R6.
//
// This file RENDERS. It does not compute. Every string on screen is a
// `text` field the Python contract already produced, every colour is its
// `color` field, and every gate light is a `state`/`color` pair from
// `src/trading/gate_vocabulary.py`. Deriving a cost, a grade, a colour or
// a light state here would be a second implementation of the thing R3
// exists to be the only one of.
(function (global) {
  "use strict";

  var h = global.React.createElement;

  // Milliseconds a pointer must rest on a cell before its tooltip shows.
  // Qt's QToolTip wakes at the same figure.
  var TOOLTIP_DELAY_MS = 700;

  // The bridge method the pager re-asks for a neighbouring page.
  var VIEW_MODEL_METHOD = "history.view_model";

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

  // Which chrome strips the page draws. The Qt tab that hosts the table
  // owns its own filter bar, summary line and pager, and turns these off
  // so the operator is not shown two of each.
  var CHROME_DEFAULT = {
    summary: true,
    filters: true,
    pager: true,
    headers: true
  };

  function chromeOf(state) {
    var given = (state && state.chrome) || {};
    return {
      summary: given.summary !== false,
      filters: given.filters !== false,
      pager: given.pager !== false,
      headers: given.headers !== false
    };
  }

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

  // ── tooltips ─────────────────────────────────────────────────────────
  //
  // Qt's setToolTip renders a string as rich text when it looks like
  // markup, and as plain text otherwise. A `title=` attribute renders
  // markup literally, so a tooltip carrying <b> or <span style=color>
  // reaches the operator as source. These functions reproduce Qt's
  // behaviour: detect, sanitize, render.

  // Tag -> the attributes it may keep. Every other element is unwrapped
  // to its text. The builders in history_helpers.py emit b, i, span and
  // pre.
  var TOOLTIP_TAGS = {
    B: ["style"],
    STRONG: ["style"],
    I: ["style"],
    EM: ["style"],
    SPAN: ["style"],
    PRE: ["style"],
    BR: []
  };

  // Qt::mightBeRichText: a tag-shaped '<' or an HTML entity.
  var RICH_TAG = /<\s*\/?\s*[a-zA-Z][^>]*>/;
  var RICH_ENTITY = /&(#[0-9]+|[a-zA-Z][a-zA-Z0-9]*);/;

  function mightBeRichText(text) {
    return RICH_TAG.test(text) || RICH_ENTITY.test(text);
  }

  // DOMParser builds an INERT document: no script runs in it and no
  // resource is fetched from it. Only allowlisted elements and the style
  // attribute are copied into the live document, so an event-handler
  // attribute cannot survive the copy.
  function sanitizeInto(html, target) {
    var parsed = new global.DOMParser().parseFromString(html, "text/html");
    (function walk(source, destination) {
      Array.prototype.forEach.call(source.childNodes, function (node) {
        if (node.nodeType === 3) {
          destination.appendChild(document.createTextNode(node.nodeValue));
          return;
        }
        if (node.nodeType !== 1) {
          return;
        }
        var allowed = TOOLTIP_TAGS[node.tagName];
        if (!allowed) {
          walk(node, destination);
          return;
        }
        var el = document.createElement(node.tagName.toLowerCase());
        allowed.forEach(function (attr) {
          var value = node.getAttribute(attr);
          if (value) {
            el.setAttribute(attr, value);
          }
        });
        walk(node, el);
        destination.appendChild(el);
      });
    })(parsed.body, target);
    return target;
  }

  function renderTooltip(node, text) {
    while (node.firstChild) {
      node.removeChild(node.firstChild);
    }
    if (mightBeRichText(text)) {
      node.setAttribute("data-tooltip-mode", "rich");
      sanitizeInto(text, node);
    } else {
      node.setAttribute("data-tooltip-mode", "plain");
      node.appendChild(document.createTextNode(text));
    }
    return node;
  }

  var tooltipTimer = null;

  function tooltipNode() {
    var node = document.getElementById("panel-tooltip");
    if (node === null) {
      node = document.createElement("div");
      node.id = "panel-tooltip";
      node.className = "tooltip";
      node.setAttribute("data-state", "hidden");
      document.body.appendChild(node);
    }
    return node;
  }

  function hideTooltip() {
    if (tooltipTimer !== null) {
      global.clearTimeout(tooltipTimer);
      tooltipTimer = null;
    }
    var node = tooltipNode();
    node.setAttribute("data-state", "hidden");
    node.style.display = "none";
  }

  function showTooltip(text, x, y) {
    var node = tooltipNode();
    renderTooltip(node, text);
    node.setAttribute("data-state", "shown");
    node.style.display = "block";
    node.style.left = String(x + 12) + "px";
    node.style.top = String(y + 16) + "px";
  }

  function armTooltip(event) {
    hideTooltip();
    var host =
      event.target && event.target.closest
        ? event.target.closest("[data-cell-tooltip]")
        : null;
    if (host === null) {
      return;
    }
    var text = host.getAttribute("data-cell-tooltip");
    if (!text) {
      return;
    }
    var x = event.clientX;
    var y = event.clientY;
    tooltipTimer = global.setTimeout(function () {
      tooltipTimer = null;
      showTooltip(text, x, y);
    }, TOOLTIP_DELAY_MS);
  }

  document.addEventListener("mouseover", armTooltip, true);
  document.addEventListener("mouseout", hideTooltip, true);
  document.addEventListener("scroll", hideTooltip, true);

  // ── components ───────────────────────────────────────────────────────

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

  // The nineteen labelled lights the Simulator's GateLightsCell paints:
  // the ten scrum gates then the nine fold gates, label above the light,
  // bank marker after each bank. `state` and `color` arrive resolved.
  function GateLights(props) {
    var lights = props.lights;
    if (!lights || !Array.isArray(lights.lights) || lights.lights.length === 0) {
      return null;
    }
    var banks = [];
    lights.lights.forEach(function (light, i) {
      var bank = banks.length ? banks[banks.length - 1] : null;
      if (bank === null || bank.name !== light.bank) {
        bank = { name: light.bank, items: [] };
        banks.push(bank);
      }
      bank.items.push(
        h(
          "span",
          {
            key: light.bank + ":" + light.label + ":" + i,
            className: "light",
            "data-light-bank": light.bank,
            "data-light-label": light.label,
            "data-light-state": light.state,
            "data-light-color": light.color
          },
          h("span", { className: "light-label" }, light.label),
          h("i", {
            className: "light-dot",
            style: { background: light.color }
          })
        )
      );
    });
    return h(
      "span",
      {
        className: "gate-lights",
        "data-light-count": String(lights.lights.length)
      },
      banks.map(function (bank) {
        return h(
          "span",
          { key: bank.name, className: "light-bank", "data-bank": bank.name },
          bank.items.concat([
            h("span", { key: "marker", className: "bank-marker" }, bank.name)
          ])
        );
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
    // No `title` attribute. The tooltip is drawn by renderTooltip, which
    // honours the markup Qt honours; a `title` would show the same text
    // a second time, unrendered.
    return h(
      "td",
      {
        className: "cell cell-" + cell.key,
        "data-col-key": cell.key,
        "data-row-index": String(props.rowIndex),
        "data-cell-color": cell.color === null ? "" : String(cell.color),
        "data-cell-tooltip": cell.tooltip === null ? "" : String(cell.tooltip),
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
    var head = props.headers === false
      ? null
      : h(
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
                  "data-cell-tooltip": col.header_tooltip || "",
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

  // A host that draws this pager reaches the backend itself; a host that
  // hides it behind its own control bar never calls this.
  function turnTo(page) {
    if (!global.acervator || typeof global.acervator.call !== "function") {
      return null;
    }
    return global.acervator
      .call(VIEW_MODEL_METHOD, { page: page })
      .then(function (next) {
        if (next !== null && typeof next === "object") {
          global.acervatorSetState(next);
        }
        return next;
      });
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
          title: "Show the previous page of trades.",
          onClick: function () {
            turnTo(props.page - 1);
          }
        },
        "Prev"
      ),
      h("span", { id: "pager-label", className: "pager-label" }, props.label),
      h(
        "button",
        {
          id: "pager-next",
          disabled: !props.nextEnabled,
          title: "Show the next page of trades.",
          onClick: function () {
            turnTo(props.page + 1);
          }
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
        {
          className: "panel",
          id: "panel-root",
          "data-render-seq": String(props.seq)
        },
        h(ErrorBanner, { reason: reason })
      );
    }
    var page = state.page;
    var chrome = chromeOf(state);
    var parts = [];
    if (chrome.summary) {
      parts.push(h(SummaryStrip, { key: "summary", summary: state.summary }));
    }
    if (chrome.filters) {
      parts.push(
        h(FilterStrip, {
          key: "filters",
          filters: state.filters,
          filterOptions: state.filter_options,
          fromText: state.from_text,
          toText: state.to_text
        })
      );
    }
    parts.push(
      h(Table, {
        key: "table",
        columns: state.columns,
        rows: page.rows,
        headers: chrome.headers
      })
    );
    if (chrome.pager) {
      parts.push(
        h(Pager, {
          key: "pager",
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
    return h(
      "div",
      {
        className: "panel",
        id: "panel-root",
        "data-render-seq": String(props.seq),
        "data-chrome": [
          chrome.summary ? "summary" : "",
          chrome.filters ? "filters" : "",
          chrome.pager ? "pager" : "",
          chrome.headers ? "headers" : ""
        ]
          .filter(Boolean)
          .join(",")
      },
      parts
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
    hideTooltip();
    var root = ensureMount();
    global.ReactDOM.flushSync(function () {
      root.render(h(Panel, { state: state, seq: seq }));
    });
    return seq;
  };

  // The tooltip renderer, reachable without a pointer. The agreement
  // test compares what the page RENDERS against what Qt renders, which
  // a `title` attribute could never answer.
  global.acervatorRenderTooltip = function (text) {
    return renderTooltip(document.createElement("div"), text);
  };
  global.acervatorChromeDefault = CHROME_DEFAULT;
  global.acervatorHistoryPanelTurnTo = turnTo;

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
