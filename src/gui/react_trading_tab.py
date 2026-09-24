# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
"""The Live tab drawn by React inside ``QWebEngineView``.

``TradingTabReact`` asks ``trading_tab_surface`` for the tab and draws
``src/gui/web/trading_tab.js`` through the Electron shell's ``panel_host.js``,
so the page in the desktop window and the page in the shell run the same
module. ``trading_tab.js`` mounts ``indicator_panel.js``, ``status_log.js`` and
``exchange_tab.js`` into slots it keeps for them, so the voting panel, the
Activity Log and the venue page need no registration of their own.
``hold_venue`` takes one ``ExchangeTabReact``, whose ``published`` signal
carries each fresh fleet payload to the page. ``page_html`` inlines
``trading_tab.css``, ``exchange_tab.css`` and every script, so the page
fetches nothing.
"""

from __future__ import annotations

import json
import logging
import math
from typing import Any, Optional

from .main_tabs import bot_status_table_surface as scrum_surface
from .main_tabs import crypto_news_ticker_surface as ticker_surface
from .main_tabs import design_system_surface as token_surface
from .main_tabs import exchange_tab_surface as venue_surface
from .main_tabs import extractor_bot_table_surface as extractor_surface
from .main_tabs import indicator_panel_surface, status_log_surface, trading_tab_surface
from .react_history_panel import STYLE_SOURCE_ASSETS, page_html, read_asset
from .react_main_window import read_renderer_asset

try:
    from PySide6.QtWebEngineCore import QWebEnginePage
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWidgets import QVBoxLayout, QWidget

    _HAS_WEBENGINE = True
except ImportError:
    # Without WebEngine, TradingTabReact is never defined and its import
    # fails by name.
    _HAS_WEBENGINE = False

logger = logging.getLogger("acervator.gui.react_trading_tab")

ACCESSIBLE_NAME = "React Live Tab"

#: The element ``trading_tab.js`` draws the tab into.
PANEL_ROOT_ID = "panel-root"

#: The console line an ask carrying an action goes out on, and the key
#: that marks such an ask. A read is served from the page's own payload.
ASK_PREFIX = "acervator-ask:"
ACTION_PARAM = "action"

#: The renderer module the page draws.
PANEL_MODULE = "trading_tab.js"

#: The modules ``trading_tab.js`` mounts into its own slots. Order is load
#: order. ``exchange_tab.js`` mounts the four modules ahead of it.
CHILD_MODULES: tuple[str, ...] = (
    "status_log.js",
    "indicator_panel.js",
    "table_cells.js",
    "bot_status_table.js",
    "extractor_bot_table.js",
    "crypto_news_ticker.js",
    "exchange_tab.js",
)

#: The style sheets the page carries.
STYLE_ASSETS: tuple[str, ...] = ("trading_tab.css", "exchange_tab.css")

#: The global each module defines once it has run to its end.
MODULE_GLOBALS: dict[str, str] = {
    "design_tokens.js": "acervatorTokens",
    "theme_engine.js": "acervatorThemes",
    "shared_widgets.js": "acervatorWidgets",
    "header_strip.js": "acervatorHeader",
    "status_log.js": "acervatorLog",
    "indicator_panel.js": "acervatorIndicatorPanel",
    "table_cells.js": "acervatorCells",
    "bot_status_table.js": "acervatorBotTable",
    "extractor_bot_table.js": "acervatorExtractorTable",
    "crypto_news_ticker.js": "acervatorTicker",
    "exchange_tab.js": "acervatorExchangeTab",
    PANEL_MODULE: "acervatorTrading",
}

#: The setter each venue module publishes for the payload of its own method.
VENUE_SETTERS: dict[str, str] = {
    scrum_surface.METHOD: "acervatorSetBotTable",
    extractor_surface.METHOD: "acervatorSetExtractorTable",
    ticker_surface.METHOD: "acervatorSetTicker",
    venue_surface.METHOD: "acervatorSetExchangeTab",
}

#: The setter ``design_tokens.js`` publishes for the design-system payload.
DESIGN_SETTER = "acervatorSetTokens"

#: The global whose ``forget`` drops the one ask a module caches, by method.
MODULE_FORGETS: dict[str, str] = {
    indicator_panel_surface.METHOD: "acervatorIndicatorPanel",
    venue_surface.METHOD: "acervatorExchangeTab",
}

#: The request fields a venue module names its exchange under.
VENUE_KEYS: tuple[str, ...] = (
    venue_surface.EXCHANGE_ID_PARAM,
    scrum_surface.EXCHANGE_ID_PARAM,
    extractor_surface.EXCHANGE_ID_PARAM,
)

#: The selector of each space a bot table draws its own rows into.
TABLE_SPACES: tuple[str, ...] = (
    '[data-part="scrum-table"]',
    '[data-part="extractor-table"]',
)

#: The console line the page writes a privacy toggle on.
ACTION_PREFIX = "acervator-live:"

#: The JS expression naming every module whose global reached the page.
LOADED_MODULES_JS = "window.acervatorTradingPage.modules().join(',')"

#: The JS expression naming each style sheet the page holds and its rule count.
LOADED_STYLES_JS = "JSON.stringify(window.acervatorTradingPage.styles())"

#: The JS expression counting the bot rows each table space really drew.
DRAWN_ROWS_JS = "JSON.stringify(window.acervatorTradingPage.rows())"

#: The JS expression naming the bot the voting panel is showing.
SHOWN_BOT_JS = 'window.acervatorIndicatorPanel.field("selected_bot_id")'

#: The scripts every page carries before the modules. Order is load order.
BASE_SCRIPT_ASSETS: tuple[str, ...] = (
    "vendor/react.production.min.js",
    "vendor/react-dom.production.min.js",
)

#: The panel host, read from ``desktop/renderer`` and inlined.
SHELL_SCRIPT = "panel_host.js"

#: The global a page carries the name of the module running now under.
NAME_GLOBAL = "acervatorInlinedModule"

#: The page ground. Every colour a part paints arrives on its own ``style``
#: attribute from the payload, so no rule here may set one on a part.
PAGE_STYLE = (
    "*{margin:0;padding:0;box-sizing:border-box}"
    "html,body{height:100%}"
    "body{background:var(--bg);color:var(--text);"
    'font:12px/1.4 "Segoe UI","Helvetica Neue",Arial,sans-serif}'
    f"#{PANEL_ROOT_ID}{{height:100%}}"
)

#: The JS expression naming every module that registered a panel.
DRAWN_MODULES_JS = "window.acervatorPanelHost.registered().join(',')"

#: The JS expression naming every panel the page refused to draw.
PANEL_FAULTS_JS = "JSON.stringify(window.acervatorPanelHost.faults())"

_NAMER_SOURCE = """(function (global) {
  "use strict";

  var host = global.acervatorPanelHost;
  var real = host.register;

  // Every module is inlined, so document.currentScript names no file.
  host.register = function (spec, called) {
    return real(spec, called || global.%(name_global)s || null);
  };
})(window);"""

_MARKER_SOURCE = "window.%(name_global)s = %(module)s;"

_HOST_SOURCE = """(function (global, doc) {
  "use strict";

  var MODELS = %(models)s;
  var IVP = %(ivp)s;
  var LOG = %(log)s;
  var TAB = %(tab)s;
  var TOGGLE = %(toggle)s;
  var SORT = %(sort)s;
  var PREFIX = %(prefix)s;
  var FORGETS = %(forgets)s;
  var VENUES = %(venues)s;
  var SETTERS = %(setters)s;
  var DESIGN = %(design)s;
  var KEYS = %(keys)s;
  var GLOBALS = %(globals)s;
  var NAME = %(name)s;
  var ROOT = %(root)s;
  var ASSET = %(asset)s;
  var ROW = %(row)s;
  var SPACES = %(spaces)s;
  var ACTION = %(action)s;
  var waiting = {};
  var nextAsk = 1;

  global.ACERVATOR_MODULES = %(roster)s;

  function owns(bag, name) {
    return Object.prototype.hasOwnProperty.call(bag, name);
  }

  // A venue module names its exchange under one of KEYS, so one page can
  // answer two layers without either reading the other's rows.
  function venueOf(params) {
    for (var at = 0; at < KEYS.length; at++) {
      if (params && owns(params, KEYS[at])) {
        return String(params[KEYS[at]]);
      }
    }
    return null;
  }

  function answer(method, params) {
    var id = venueOf(params);
    if (id !== null && owns(VENUES, id) && owns(VENUES[id], method)) {
      return VENUES[id][method];
    }
    return owns(MODELS, method) ? MODELS[method] : null;
  }

  // Hands each venue module the payload of its own method, then writes the
  // design tokens onto the document so a var(--TOKEN) rule resolves.
  function seat() {
    Object.keys(VENUES).forEach(function (id) {
      SETTERS.forEach(function (pair) {
        var setter = global[pair[1]];
        if (typeof setter === "function" && owns(VENUES[id], pair[0])) {
          setter(VENUES[id][pair[0]]);
        }
      });
    });
    var design = global[DESIGN[1]];
    if (typeof design === "function" && owns(MODELS, DESIGN[0])) {
      design(MODELS[DESIGN[0]]);
    }
    if (global.acervatorTokens && typeof global.acervatorTokens.apply === "function") {
      global.acervatorTokens.apply(doc.documentElement);
    }
  }

  function modules() {
    return GLOBALS.filter(function (pair) {
      return global[pair[1]] !== undefined;
    }).map(function (pair) {
      return pair[0];
    });
  }

  function styles() {
    var found = [];
    var tags = doc.querySelectorAll("style[" + ASSET + "]");
    for (var at = 0; at < tags.length; at++) {
      var sheet = tags[at].sheet;
      found.push([
        tags[at].getAttribute(ASSET),
        sheet === null ? 0 : sheet.cssRules.length
      ]);
    }
    return found;
  }

  function rows() {
    var found = {};
    SPACES.forEach(function (part) {
      found[part] = doc.querySelectorAll(part + " " + ROW).length;
    });
    return found;
  }

  // exchange_tab.js answers a second ask from the first ask's payload, so
  // forget() runs before a fresh fleet is seated and drawn.
  function hold(venues) {
    VENUES = venues;
    var venue = global.acervatorExchangeTab;
    if (venue && typeof venue.forget === "function") {
      venue.forget();
    }
    seat();
    var tab = global.acervatorTrading;
    return tab && typeof tab.redraw === "function" ? tab.redraw() : 0;
  }

  // Three presses leave this page. A privacy toggle and a column sort go
  // out on PREFIX, because the register and the fleet that answer them
  // live in Python. An ask naming an ACTION changes what the window
  // holds, so it goes out on its own line and is answered by its own id.
  // Every other call is a read and is answered from the payload this page
  // is already holding.
  global.acervator = {
    call: function (method, params) {
      if (params && (owns(params, TOGGLE) || owns(params, SORT))) {
        global.console.log(
          PREFIX + JSON.stringify({ method: method, params: params })
        );
      }
      if (params && owns(params, ACTION)) {
        var id = nextAsk;
        nextAsk += 1;
        global.console.log(
          "%(ask)s" + JSON.stringify({ id: id, method: method, params: params })
        );
        return new Promise(function (resolve, reject) {
          waiting[id] = { resolve: resolve, reject: reject };
        });
      }
      return Promise.resolve(answer(method, params));
    }
  };

  global.acervatorTradingAnswer = function (id, model, refusal) {
    var held = waiting[id];
    delete waiting[id];
    if (!held) {
      return false;
    }
    if (refusal) {
      held.reject(new Error(refusal));
      return true;
    }
    held.resolve(model);
    return true;
  };

  // One fresh payload per bridge method. LOG appends its batch, TAB
  // replaces the tab's own model, and every other method drops the ask
  // its module caches so redraw() reads MODELS again.
  function holdModels(fresh) {
    Object.keys(fresh).forEach(function (method) {
      if (method === LOG) {
        var spool = global.acervatorLog;
        if (spool && typeof spool.take === "function") {
          spool.take(fresh[method]);
        }
        return;
      }
      MODELS[method] = fresh[method];
      if (method === TAB) {
        var setter = global.acervatorSetTrading;
        if (typeof setter === "function") {
          setter(fresh[method]);
        }
        return;
      }
      var owner = owns(FORGETS, method) ? global[FORGETS[method]] : null;
      if (owner && typeof owner.forget === "function") {
        owner.forget();
      }
    });
    var tab = global.acervatorTrading;
    return tab && typeof tab.redraw === "function" ? tab.redraw() : 0;
  }

  function votes(model) {
    var fresh = {};
    fresh[IVP] = model;
    return holdModels(fresh);
  }

  global.acervatorTradingPage = {
    modules: modules,
    styles: styles,
    rows: rows,
    hold: hold,
    votes: votes,
    holdModels: holdModels
  };

  seat();
  global.acervatorTradingTabDrawn = global.acervatorPanelHost.open(
    NAME,
    doc.getElementById(ROOT)
  );
})(window, document);"""


def module_name(asset: str = PANEL_MODULE) -> str:
    """``asset`` without its ``.js`` suffix, which is the panel's own name."""
    return asset.rsplit(".", 1)[0]


def roster() -> tuple[str, ...]:
    """Every module the page carries, in load order.

    ``STYLE_SOURCE_ASSETS`` leads: ``trading_tab.js`` parses every Qt style
    sheet in its payload with ``header_strip.styleOf``.
    """
    return STYLE_SOURCE_ASSETS + CHILD_MODULES + (PANEL_MODULE,)


def models(live: Any = None, asked: Any = None) -> dict:
    """The view model of every bridge method the page's modules ask for.

    ``live`` is a ``desktop_bridge.LiveSystem``, ``bind_live`` builds the tab
    from the exchanges the running program is configured for, and ``asked``
    carries the layer and the two pause states a built tab already held.
    """
    tab = (
        trading_tab_surface.bind_live(live)
        if live is not None
        else trading_tab_surface.view_model
    )
    return {
        token_surface.METHOD: token_surface.view_model({}),
        trading_tab_surface.METHOD: tab(dict(asked or {})),
        status_log_surface.METHOD: status_log_surface.view_model({"whole": True}),
        indicator_panel_surface.METHOD: indicator_panel_surface.view_model({}),
    }


def venue_models(venues: Any) -> dict:
    """Each venue page's own payloads, keyed by the exchange it draws.

    ``ExchangeTabReact.models`` already carries what ``update_bots`` last
    wrote, so the rows the Live page draws are the rows the window handed
    that venue.
    """
    found: dict = {}
    for exchange_id, venue in dict(venues or {}).items():
        read = getattr(venue, "models", None)
        if not callable(read):
            continue
        held = read()
        if held:
            found[str(exchange_id)] = held
    return found


def venue_setters() -> list:
    """Each venue bridge method beside the setter its own module publishes."""
    return [
        [method, VENUE_SETTERS[method]]
        for method in (
            scrum_surface.METHOD,
            extractor_surface.METHOD,
            ticker_surface.METHOD,
            venue_surface.METHOD,
        )
    ]


def module_globals() -> list:
    """Each module the page carries beside the global it defines when it runs."""
    return [[name, MODULE_GLOBALS[name]] for name in roster()]


def namer_script() -> str:
    """The shim that hands the panel host the name an inlined module lacks."""
    return _NAMER_SOURCE % {"name_global": NAME_GLOBAL}


def marker_script(asset: str) -> str:
    """The one statement naming the module whose script tag comes next."""
    return _MARKER_SOURCE % {
        "name_global": NAME_GLOBAL,
        "module": json.dumps(module_name(asset), ensure_ascii=True),
    }


def host_script(built: dict, venues: Optional[dict] = None) -> str:
    """The page's own glue: the models, the venues, and the panel to open."""
    return _HOST_SOURCE % {
        "models": json.dumps(built, ensure_ascii=True),
        "ask": ASK_PREFIX,
        "action": json.dumps(ACTION_PARAM, ensure_ascii=True),
        "ivp": json.dumps(indicator_panel_surface.METHOD, ensure_ascii=True),
        "log": json.dumps(status_log_surface.METHOD, ensure_ascii=True),
        "tab": json.dumps(trading_tab_surface.METHOD, ensure_ascii=True),
        "toggle": json.dumps(scrum_surface.PRIVACY_TOGGLE_PARAM, ensure_ascii=True),
        "sort": json.dumps(scrum_surface.SORT_COLUMN_PARAM, ensure_ascii=True),
        "prefix": json.dumps(ACTION_PREFIX, ensure_ascii=True),
        "forgets": json.dumps(MODULE_FORGETS, ensure_ascii=True),
        "venues": json.dumps(dict(venues or {}), ensure_ascii=True),
        "setters": json.dumps(venue_setters(), ensure_ascii=True),
        "design": json.dumps([token_surface.METHOD, DESIGN_SETTER], ensure_ascii=True),
        "keys": json.dumps(list(VENUE_KEYS), ensure_ascii=True),
        "globals": json.dumps(module_globals(), ensure_ascii=True),
        "name": json.dumps(module_name(), ensure_ascii=True),
        "roster": json.dumps(list(roster()), ensure_ascii=True),
        "root": json.dumps(PANEL_ROOT_ID, ensure_ascii=True),
        "asset": json.dumps("data-asset", ensure_ascii=True),
        "row": json.dumps('[data-part="row"]', ensure_ascii=True),
        "spaces": json.dumps(list(TABLE_SPACES), ensure_ascii=True),
    }


def settled_frames() -> int:
    """The `step_bars` frames `ConfidenceBarsModel` takes to reach a target from zero.

    Read off `BARS_LERP_FACTOR` and `BARS_SETTLE_DELTA`.
    """
    surface = indicator_panel_surface
    return math.ceil(
        math.log(surface.BARS_SETTLE_DELTA) / math.log(1.0 - surface.BARS_LERP_FACTOR)
    )


def votes_payload(bots: Any, reading: Any = None) -> dict:
    """The voting panel payload after the fleet and the panel's own reading.

    ``IndicatorVotingPanel.panel_reading`` names the selection, the cells, the
    stored banner, the mask and the rate line, and
    ``indicator_panel_surface.view_model`` is the handler the Electron renderer
    asks, so the window and the shell draw one panel.
    """
    surface = indicator_panel_surface
    read = dict(reading or {})
    surface.view_model({"action": "set_bots", "bots": list(bots or [])})
    selected = str(read.get("selected_bot_id") or "")
    if selected:
        surface.view_model({"action": "select_bot", "bot_id": selected})
    surface.view_model({"action": "set_masked", "masked": bool(read.get("masked"))})
    if "rates" in read:
        surface.view_model({"action": "set_rates", "snapshot": read.get("rates")})
    stored = read.get("stored")
    if stored:
        surface.view_model(
            {
                "action": "show_stored",
                "stored": stored,
                "when": read.get("when", ""),
                "age": read.get("age", ""),
                "message": read.get("message", ""),
            }
        )
        return surface.view_model({"action": "step_bars", "frames": settled_frames()})
    summary = read.get("summary")
    if summary:
        surface.view_model(
            {
                "action": "set_summary",
                "summary": summary,
                "symbol": read.get("symbol", ""),
            }
        )
        return surface.view_model({"action": "step_bars", "frames": settled_frames()})
    return surface.view_model(
        {
            "action": "show_no_data",
            "message": read.get("message", ""),
            "cause": read.get("cause", ""),
        }
    )


def log_request(action: str, message: str = "", level: Any = None) -> Optional[dict]:
    """The ``status_log.lines`` request one ``StatusLog`` call makes."""
    if action == "log":
        return {"messages": [{"message": message, "level": level}]}
    if action == "force_log":
        return {"messages": [{"message": message, "level": level, "force": True}]}
    if action == "notice":
        return {"notices": [message]}
    if action == "pause":
        return {"paused": True}
    if action == "resume":
        return {"paused": False}
    return None


def votes_script(payload: dict) -> str:
    """The one JS statement handing the page a fresh voting-panel payload."""
    return (
        "window.acervatorTradingPage.votes("
        + json.dumps(dict(payload or {}), ensure_ascii=True)
        + ");"
    )


def models_script(fresh: dict) -> str:
    """The one JS statement handing the page a fresh payload per method."""
    return (
        "window.acervatorTradingPage.holdModels("
        + json.dumps(dict(fresh or {}), ensure_ascii=True)
        + ");"
    )


def push_script(venues: dict) -> str:
    """The one JS statement handing the page a fresh payload for each venue.

    ``ensure_ascii=True`` escapes U+2028 and U+2029, which are legal inside a
    JSON string and are JavaScript line terminators.
    """
    return (
        "window.acervatorTradingPage.hold("
        + json.dumps(dict(venues or {}), ensure_ascii=True)
        + ");"
    )


def _tag(source: str) -> str:
    """``source`` wrapped in a script tag of its own."""
    return "<script>" + source + "</script>"


def answer_script(ask_id: Any, model: Any) -> str:
    """The statement that settles the ask ``ask_id`` with ``model``."""
    return (
        "window.acervatorTradingAnswer("
        + json.dumps(ask_id, ensure_ascii=True)
        + ","
        + json.dumps(model, ensure_ascii=True, default=str)
        + ",null);"
    )


def refusal_script(ask_id: Any, reason: str) -> str:
    """The statement that refuses the ask ``ask_id`` with ``reason``."""
    return (
        "window.acervatorTradingAnswer("
        + json.dumps(ask_id, ensure_ascii=True)
        + ",null,"
        + json.dumps(str(reason), ensure_ascii=True)
        + ");"
    )


def page_body() -> str:
    """The page's body: the root, the panel host, React, then every module.

    ``namer_script`` runs before any module, so a ``register`` call is given
    the name the module cannot read off its own inlined script tag.
    """
    parts = [
        "<style>" + PAGE_STYLE + "</style>",
        f'<div id="{PANEL_ROOT_ID}"></div>',
        _tag(read_renderer_asset(SHELL_SCRIPT)),
        _tag(namer_script()),
    ]
    for name in BASE_SCRIPT_ASSETS:
        parts.append(_tag(read_asset(name)))
    for name in roster():
        parts.append(_tag(marker_script(name)))
        parts.append(_tag(read_asset(name)))
    return "".join(parts)


def panel_html(built: dict, venues: Optional[dict] = None, theme: object = None) -> str:
    """The whole Live page as one string, with no network fetch.

    ``STYLE_ASSETS`` is inlined into the page head, so the tab's chrome
    reaches the browser without a stylesheet request.
    """
    return page_html(
        STYLE_ASSETS, (), page_body(), theme, (host_script(built, venues),)
    )


if _HAS_WEBENGINE:

    class LivePage(QWebEnginePage):
        """Routes the page's ``acervator-live:`` and ``acervator-ask:`` lines."""

        def __init__(self, owner) -> None:
            """Hold ``owner`` as the widget that answers the page."""
            super().__init__(owner)
            self._owner = owner

        def javaScriptConsoleMessage(self, level, message, line, source) -> None:
            """Hand a privacy toggle or a bridge ask on, and drop every other line."""
            del level, line, source
            if message.startswith(ACTION_PREFIX):
                self._owner.run_action(message[len(ACTION_PREFIX) :])
            elif message.startswith(ASK_PREFIX):
                self._owner.run_ask(message[len(ASK_PREFIX) :])

    class TradingTabReact(QWidget):
        """The Live tab, drawn by ``trading_tab.js`` and its child modules.

        ``build_panel`` loads the page once, on the first show, so a window
        that never opens the tab pays for no web view. ``hold_venue`` takes
        one venue page, whose ``published`` signal pushes each fresh fleet.
        """

        def __init__(
            self,
            live: Any = None,
            parent: Optional[QWidget] = None,
            theme: object = None,
        ) -> None:
            """Hold ``live`` as the source the tab's view models are built from."""
            super().__init__(parent)
            self.setAccessibleName(ACCESSIBLE_NAME)
            self._live = live
            self._theme = theme
            self._models: dict = {}
            self._votes: dict = {}
            self._venues: dict = {}
            self._venue_models: dict = {}
            self._tab_request: dict = {}
            self._waiting: dict = {}
            self._votes_handler: Any = None
            self._page_ready = False
            self._web: Any = None
            self._layout = QVBoxLayout(self)
            self._layout.setContentsMargins(0, 0, 0, 0)
            self._layout.setSpacing(0)

        @property
        def page_ready(self) -> bool:
            """True once ``_on_load_finished`` has seen a successful load."""
            return self._page_ready

        def panel_view(self):
            """The web view the tab draws in, or None before the first show."""
            return self._web

        def models(self) -> dict:
            """A copy of the models the page was built from, empty before that."""
            return dict(self._models)

        def venue_payloads(self) -> dict:
            """A copy of the payload each venue page last published."""
            return dict(self._venue_models)

        def show_models(self, fresh: Any) -> bool:
            """Hold one payload per bridge method and draw them on the page.

            Every feed the window pushes into the Live tab arrives here, so a
            page built later still opens on what the window last held.
            """
            held = {str(name): body for name, body in dict(fresh or {}).items() if body}
            if not held:
                return False
            self._models.update(held)
            if not (self._page_ready and self._web is not None):
                self._waiting.update(held)
                return True
            self._web.page().runJavaScript(models_script(held))
            return True

        def set_votes_handler(self, handler: Any) -> None:
            """Take the callable that answers a voting-panel ask from the page.

            ``MainWindow._answer_votes`` is what the running window binds
            here; it applies the ask to the Qt panel and answers the payload
            the page then draws.
            """
            self._votes_handler = handler

        def run_ask(self, payload: str) -> None:
            """Answer one bridge ask the page reported and hand it back by id."""
            try:
                ask = json.loads(payload)
            except ValueError:
                logger.warning("The React Live page sent an ask that is not JSON")
                return
            ask_id = ask.get("id")
            try:
                answered = self._answer_ask(
                    str(ask.get("method") or ""), ask.get("params")
                )
            except Exception as exc:
                logger.warning("The React Live page ask was refused: %s", exc)
                self._run(refusal_script(ask_id, f"{type(exc).__name__}: {exc}"))
                return
            self._run(answer_script(ask_id, answered))

        def _answer_ask(self, method: str, params: Any) -> Any:
            """Apply one ask that names an action and answer the fresh payload.

            Only the voting panel's method carries an action today; any
            other method answers the payload the page was built with.
            """
            asked = params if isinstance(params, dict) else {}
            if method != indicator_panel_surface.METHOD:
                return self._models.get(method)
            if not callable(self._votes_handler):
                return self._votes
            payload = self._votes_handler(asked)
            if isinstance(payload, dict) and payload:
                self._votes = dict(payload)
                self._models[method] = self._votes
            return self._votes

        def _run(self, script: str) -> bool:
            """Run one statement on the page, or answer False before it loads."""
            if not (self._page_ready and self._web is not None):
                return False
            self._web.page().runJavaScript(script)
            return True

        def show_votes(self, payload: Any) -> bool:
            """Hold one voting-panel payload and draw it on the page.

            ``MainWindow._publish_votes`` calls this with the payload
            ``votes_payload`` builds from the reading the Qt panel holds.
            """
            held = dict(payload or {})
            if not held:
                return False
            self._votes = held
            return self.show_models({indicator_panel_surface.METHOD: held})

        def show_log_call(self, action: str, message: str = "", level: Any = None):
            """Apply one ``StatusLog`` call to the surface and draw its lines.

            ``StatusLog.set_relay`` reports ``log``, ``force_log``, ``notice``,
            ``pause`` and ``resume`` here as the Qt pane paints them.
            """
            asked = log_request(action, message, level)
            if asked is None:
                return False
            payload = status_log_surface.view_model(asked)
            return self.show_models({status_log_surface.METHOD: payload})

        def show_tab(self, asked: Any = None) -> bool:
            """Rebuild the tab payload from ``asked`` and draw it on the page.

            ``layer``, ``activity_paused`` and ``api_paused`` persist in
            ``_tab_request``; ``api_lines`` is spent on the call that carries it.
            """
            request = dict(asked or {})
            lines = request.pop("api_lines", None)
            self._tab_request.update(request)
            built = dict(self._tab_request)
            if lines:
                built["api_lines"] = list(lines)
            handler = (
                trading_tab_surface.bind_live(self._live)
                if self._live is not None
                else trading_tab_surface.view_model
            )
            return self.show_models({trading_tab_surface.METHOD: handler(built)})

        # The two presses the venue answers, each naming the column it is on.
        VENUE_PRESSES = (
            (scrum_surface.PRIVACY_TOGGLE_PARAM, "toggle_privacy"),
            (scrum_surface.SORT_COLUMN_PARAM, "sort_by"),
        )

        def run_action(self, payload: str) -> bool:
            """Answer one bot-table press the page sent, and push the fleet back.

            ``VENUE_PRESSES`` names the two this tab answers; every other
            press on this page stays with the page, which owns it.
            """
            try:
                asked = json.loads(payload)
            except ValueError:
                logger.warning("The Live page sent a line that is not JSON")
                return False
            params = asked.get("params")
            if not isinstance(params, dict):
                return False
            venue = self._venues.get(
                str(params.get(scrum_surface.EXCHANGE_ID_PARAM, "") or "")
            )
            answered = False
            for name, method_name in self.VENUE_PRESSES:
                column = params.get(name)
                if column is None:
                    continue
                method = getattr(venue, method_name, None)
                if not callable(method):
                    continue
                method(column)
                answered = True
            return answered

        def hold_venue(self, venue: Any) -> bool:
            """Draw ``venue`` in this tab and follow every payload it publishes.

            ``MainWindow.add_exchange_tab`` offers each venue page it builds;
            a page carrying no ``published`` signal is refused and not held.
            """
            exchange_id = str(getattr(venue, "exchange_id", "") or "")
            published = getattr(venue, "published", None)
            if not exchange_id or published is None:
                return False
            self._venues[exchange_id] = venue
            published.connect(self._venue_published)
            self._venue_published()
            return True

        def showEvent(self, event) -> None:  # noqa: N802
            """Build the web view the first time the tab is shown."""
            super().showEvent(event)
            self.build_panel()

        def build_panel(self) -> None:
            """Create the tab's web view and load its page, once."""
            if self._web is not None:
                return
            self._models = models(self._live, self._tab_request)
            if self._votes:
                self._models[indicator_panel_surface.METHOD] = self._votes
            self._waiting = {}
            self._venue_models = venue_models(self._venues)
            self._web = QWebEngineView(self)
            self._web.setAccessibleName(ACCESSIBLE_NAME)
            self._web.setPage(LivePage(self))
            self._web.loadFinished.connect(self._on_load_finished)
            self._web.setHtml(panel_html(self._models, self._venue_models, self._theme))
            self._layout.addWidget(self._web, 1)

        def _venue_published(self) -> None:
            """Re-read every held venue and push the fleet to the page."""
            self._venue_models = venue_models(self._venues)
            if self._page_ready and self._web is not None:
                self._web.page().runJavaScript(push_script(self._venue_models))

        def _on_load_finished(self, ok: bool) -> None:
            self._page_ready = bool(ok)
            if not ok:
                logger.warning("The React Live tab page failed to load")
                return
            self._venue_published()
            waited = dict(self._waiting)
            self._waiting = {}
            if waited:
                self._web.page().runJavaScript(models_script(waited))
            elif self._votes:
                self._web.page().runJavaScript(votes_script(self._votes))
