# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
"""The Sim tab drawn by React inside ``QWebEngineView``, forked from
``react_trading_tab``.

``SimTradingTabReact`` is ``TradingTabReact`` under the Simulator's name: it
draws ``src/gui/web/sim_trading_tab.js`` through the Electron shell's
``panel_host.js``, and ``sim_trading_tab.js`` mounts ``sim_indicator_panel.js``,
``sim_status_log.js`` and ``sim_exchange_tab.js`` into slots it keeps. The host
holds ``TabletSource`` and ``FleetSource`` as ``SimTradingTab`` does, and no
bot manager; ``add_exchange_tab`` seats one venue's own models, the fork of
``hold_venue``. ``SimTradingPage`` reads the page's asks off the console line
the host script writes, and ``run_action`` answers the flip.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from ...simulator.fleet_source import FleetSource
from ...simulator.tablet_source import TabletSource
from ..main_tabs import bot_status_table_surface as scrum_surface
from ..main_tabs import design_system_surface as token_surface
from ..main_tabs import extractor_bot_table_surface as extractor_surface
from ..main_tabs import indicator_panel_surface, status_log_surface
from ..main_tabs import simulator_tab_surface as sim
from ..react_history_panel import STYLE_SOURCE_ASSETS, page_html, read_asset
from ..react_main_window import read_renderer_asset
from . import sim_exchange_tab_surface as venue_surface
from . import sim_trading_tab_surface as tab_surface

try:
    from PySide6.QtWebEngineCore import QWebEnginePage
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWidgets import QVBoxLayout, QWidget

    _HAS_WEBENGINE = True
except ImportError:
    # Without WebEngine, SimTradingTabReact is never defined and its import
    # fails by name.
    _HAS_WEBENGINE = False

logger = logging.getLogger("acervator.gui.sim_react_trading_tab")

ACCESSIBLE_NAME = sim.HEADING

#: The element ``sim_trading_tab.js`` draws the tab into.
PANEL_ROOT_ID = "panel-root"

#: The renderer module the page draws.
PANEL_MODULE = "sim_trading_tab.js"

#: The modules ``sim_trading_tab.js`` mounts into its own slots. Order is
#: load order. ``sim_exchange_tab.js`` mounts the three modules ahead of it.
CHILD_MODULES: tuple[str, ...] = (
    "sim_status_log.js",
    "sim_indicator_panel.js",
    "sim_table_cells.js",
    "sim_bot_status_table.js",
    "sim_extractor_bot_table.js",
    "sim_exchange_tab.js",
)

#: The style sheets the page carries: Live's own two, then the sheet holding
#: the parts the fork adds, in Live's chrome.
STYLE_ASSETS: tuple[str, ...] = (
    "trading_tab.css",
    "exchange_tab.css",
    "sim_trading_tab.css",
)

#: The bridge method each forked module asks.
SCRUM_METHOD = "sim_bot_status_table.state"
EXTRACTOR_METHOD = "sim_extractor_bot_table.state"
PANEL_METHOD = "sim_indicator_panel.state"
LOG_METHOD = "sim_status_log.lines"

#: The global each module defines once it has run to its end.
MODULE_GLOBALS: dict[str, str] = {
    "design_tokens.js": "acervatorTokens",
    "theme_engine.js": "acervatorThemes",
    "shared_widgets.js": "acervatorWidgets",
    "header_strip.js": "acervatorHeader",
    "sim_status_log.js": "acervatorSimLog",
    "sim_indicator_panel.js": "acervatorSimIndicatorPanel",
    "sim_table_cells.js": "acervatorSimCells",
    "sim_bot_status_table.js": "acervatorSimBotTable",
    "sim_extractor_bot_table.js": "acervatorSimExtractorTable",
    "sim_exchange_tab.js": "acervatorSimExchangeTab",
    PANEL_MODULE: "acervatorSimTrading",
}

#: The setter each venue module publishes for the payload of its own method.
VENUE_SETTERS: dict[str, str] = {
    SCRUM_METHOD: "acervatorSetSimBotTable",
    EXTRACTOR_METHOD: "acervatorSetSimExtractorTable",
    venue_surface.METHOD: "acervatorSetSimExchangeTab",
}

#: The setter ``design_tokens.js`` publishes for the design-system payload.
DESIGN_SETTER = "acervatorSetTokens"

#: The global whose ``forget`` drops the one ask a module caches, by method.
MODULE_FORGETS: dict[str, str] = {
    PANEL_METHOD: "acervatorSimIndicatorPanel",
    venue_surface.METHOD: "acervatorSimExchangeTab",
}

#: The request fields a venue module names its exchange under.
VENUE_KEYS: tuple[str, ...] = (
    "exchange_id",
    scrum_surface.EXCHANGE_ID_PARAM,
    extractor_surface.EXCHANGE_ID_PARAM,
)

#: The selector of each space a bot table draws its own rows into.
TABLE_SPACES: tuple[str, ...] = (
    '[data-part="scrum-table"]',
    '[data-part="extractor-table"]',
)

#: The JS expression naming every module whose global reached the page.
LOADED_MODULES_JS = "window.acervatorSimTradingPage.modules().join(',')"

#: The JS expression naming each style sheet the page holds and its rule count.
LOADED_STYLES_JS = "JSON.stringify(window.acervatorSimTradingPage.styles())"

#: The JS expression counting the bot rows each table space really drew.
DRAWN_ROWS_JS = "JSON.stringify(window.acervatorSimTradingPage.rows())"

#: The JS expression naming the bot the voting panel is showing.
SHOWN_BOT_JS = 'window.acervatorSimIndicatorPanel.field("selected_bot_id")'

#: The JS expression naming the layer the page shows behind the panel.
SHOWN_LAYER_JS = "window.acervatorSimTrading.replayLayer()"

#: The scripts every page carries before the modules. Order is load order.
BASE_SCRIPT_ASSETS: tuple[str, ...] = (
    "vendor/react.production.min.js",
    "vendor/react-dom.production.min.js",
)

#: The panel host, read from ``desktop/renderer`` and inlined.
SHELL_SCRIPT = "panel_host.js"

#: The global a page carries the name of the module running now under.
NAME_GLOBAL = "acervatorInlinedModule"

#: The console line the page writes a bridge ask on.
ACTION_PREFIX = "acervator-sim:"

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
  var PREFIX = %(prefix)s;

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

  // sim_exchange_tab.js answers a second ask from the first ask's payload,
  // so forget() runs before a fresh fleet is seated and drawn.
  function hold(venues) {
    VENUES = venues;
    var venue = global.acervatorSimExchangeTab;
    if (venue && typeof venue.forget === "function") {
      venue.forget();
    }
    seat();
    var tab = global.acervatorSimTrading;
    return tab && typeof tab.redraw === "function" ? tab.redraw() : 0;
  }

  // Every ask is written to the console for the host to read, then
  // answered from the payloads held here; nothing is sent anywhere else.
  global.acervator = {
    call: function (method, params) {
      global.console.log(
        PREFIX + JSON.stringify({ method: method, params: params || {} })
      );
      return Promise.resolve(answer(method, params));
    }
  };

  // One fresh payload per bridge method. LOG appends its batch, TAB
  // replaces the tab's own model, and every other method drops the ask
  // its module caches so redraw() reads MODELS again.
  function holdModels(fresh) {
    Object.keys(fresh).forEach(function (method) {
      if (method === LOG) {
        var spool = global.acervatorSimLog;
        if (spool && typeof spool.take === "function") {
          spool.take(fresh[method]);
        }
        return;
      }
      MODELS[method] = fresh[method];
      if (method === TAB) {
        var setter = global.acervatorSetSimTrading;
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
    var tab = global.acervatorSimTrading;
    return tab && typeof tab.redraw === "function" ? tab.redraw() : 0;
  }

  function votes(model) {
    var fresh = {};
    fresh[IVP] = model;
    return holdModels(fresh);
  }

  global.acervatorSimTradingPage = {
    modules: modules,
    styles: styles,
    rows: rows,
    hold: hold,
    votes: votes,
    holdModels: holdModels
  };

  seat();
  global.acervatorSimTradingTabDrawn = global.acervatorPanelHost.open(
    NAME,
    doc.getElementById(ROOT)
  );
})(window, document);"""


def module_name(asset: str = PANEL_MODULE) -> str:
    """``asset`` without its ``.js`` suffix, which is the panel's own name."""
    return asset.rsplit(".", 1)[0]


def roster() -> tuple[str, ...]:
    """Every module the page carries, in load order.

    ``STYLE_SOURCE_ASSETS`` leads: ``sim_trading_tab.js`` parses every Qt
    style sheet in its payload with ``header_strip.styleOf``.
    """
    return STYLE_SOURCE_ASSETS + CHILD_MODULES + (PANEL_MODULE,)


def panel_payload(panel: indicator_panel_surface.IndicatorPanelModel) -> dict:
    """The voting panel's payload under ``PANEL_METHOD``, with the flip button."""
    payload = dict(indicator_panel_surface.build_payload(panel))
    payload["method"] = PANEL_METHOD
    payload["flip_button"] = tab_surface.flip_button(sim.LAYER_INDICATORS)
    return payload


def log_payload(
    log: status_log_surface.StatusLogModel, asked: Optional[dict] = None
) -> dict:
    """The Activity Log's payload under ``LOG_METHOD`` after one request."""
    request = dict(asked or {})
    paused = request.get("paused")
    return status_log_surface.build_view_model(
        log,
        request.get("messages") or [],
        paused=None if paused is None else bool(paused),
        toggle=bool(request.get("toggle", False)),
        notices=request.get("notices") or [],
        whole=bool(request.get("whole", False)),
    )


def models(
    state: tab_surface.SimTradingTabState,
    log: status_log_surface.StatusLogModel,
    panel: indicator_panel_surface.IndicatorPanelModel,
) -> dict:
    """The view model of every bridge method the page's modules ask for."""
    return {
        token_surface.METHOD: token_surface.view_model({}),
        tab_surface.METHOD: state.view_model({}),
        LOG_METHOD: log_payload(log, {"whole": True}),
        PANEL_METHOD: panel_payload(panel),
    }


class SimVenue:
    """One seated venue's three models, which the page draws from."""

    def __init__(
        self, exchange_id: str, exchange_name: str, status_log: Any = None
    ) -> None:
        self.exchange_id = exchange_id
        self.exchange_name = exchange_name
        self.screen = venue_surface.screen(exchange_id, exchange_name, status_log)
        self.scrum = scrum_surface.BotStatusTableModel()
        self.scrum.exchange_id = exchange_id
        self.extractor = extractor_surface.ExtractorBotTableModel()
        self.extractor.exchange_id = exchange_id

    def models(self) -> dict:
        """The payload of each venue method, under the Simulator's names."""
        scrum = dict(scrum_surface.build_view_model(self.scrum))
        scrum["method"] = SCRUM_METHOD
        extractor = dict(extractor_surface.build_payload(self.extractor))
        extractor["method"] = EXTRACTOR_METHOD
        return {
            venue_surface.METHOD: venue_surface.build_view_model(self.screen),
            SCRUM_METHOD: scrum,
            EXTRACTOR_METHOD: extractor,
        }


def venue_models(venues: Any) -> dict:
    """Each venue page's own payloads, keyed by the exchange it draws."""
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
        for method in (SCRUM_METHOD, EXTRACTOR_METHOD, venue_surface.METHOD)
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
        "ivp": json.dumps(PANEL_METHOD, ensure_ascii=True),
        "log": json.dumps(LOG_METHOD, ensure_ascii=True),
        "tab": json.dumps(tab_surface.METHOD, ensure_ascii=True),
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
        "prefix": json.dumps(ACTION_PREFIX, ensure_ascii=True),
    }


def log_request(action: str, message: str = "", level: Any = None) -> Optional[dict]:
    """The ``sim_status_log.lines`` request one ``SimStatusLog`` call makes."""
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
        "window.acervatorSimTradingPage.votes("
        + json.dumps(dict(payload or {}), ensure_ascii=True)
        + ");"
    )


def models_script(fresh: dict) -> str:
    """The one JS statement handing the page a fresh payload per method."""
    return (
        "window.acervatorSimTradingPage.holdModels("
        + json.dumps(dict(fresh or {}), ensure_ascii=True)
        + ");"
    )


def push_script(venues: dict) -> str:
    """The one JS statement handing the page a fresh payload for each venue.

    ``ensure_ascii=True`` escapes U+2028 and U+2029, which are legal inside a
    JSON string and are JavaScript line terminators.
    """
    return (
        "window.acervatorSimTradingPage.hold("
        + json.dumps(dict(venues or {}), ensure_ascii=True)
        + ");"
    )


def _tag(source: str) -> str:
    """``source`` wrapped in a script tag of its own."""
    return "<script>" + source + "</script>"


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
    """The whole Sim page as one string, with no network fetch.

    ``STYLE_ASSETS`` is inlined into the page head, so the tab's chrome
    reaches the browser without a stylesheet request.
    """
    return page_html(
        STYLE_ASSETS, (), page_body(), theme, (host_script(built, venues),)
    )


if _HAS_WEBENGINE:

    class SimTradingPage(QWebEnginePage):
        """Routes the page's ``acervator-sim:`` console lines to its owner."""

        def __init__(self, owner) -> None:
            """Hold ``owner`` as the widget that answers the page."""
            super().__init__(owner)
            self._owner = owner

        def javaScriptConsoleMessage(self, level, message, line, source) -> None:
            """Hand a bridge ask to the owner and drop every other line."""
            del level, line, source
            if message.startswith(ACTION_PREFIX):
                self._owner.run_action(message[len(ACTION_PREFIX) :])

    class SimTradingTabReact(QWidget):
        """The Sim tab, drawn by ``sim_trading_tab.js`` and its child modules.

        ``build_panel`` loads the page once, on the first show, and
        ``add_exchange_tab`` seats one venue whose payloads the page draws.
        """

        def __init__(
            self,
            tablet_source: Optional[TabletSource] = None,
            fleet_source: Optional[FleetSource] = None,
            parent: Optional[QWidget] = None,
            theme: object = None,
        ) -> None:
            """Hold the two sources the tab's view models are built from."""
            super().__init__(parent)
            self.setObjectName(ACCESSIBLE_NAME)
            self.setAccessibleName(ACCESSIBLE_NAME)
            self._tablet_source = (
                tablet_source
                if tablet_source is not None
                else TabletSource(sim.TABLET_ROOT)
            )
            self._fleet_source = (
                fleet_source if fleet_source is not None else FleetSource()
            )
            self._theme = theme
            self._state = tab_surface.SimTradingTabState()
            self._log = status_log_surface.StatusLogModel()
            self._panel = indicator_panel_surface.IndicatorPanelModel()
            self._models: dict = {}
            self._votes: dict = {}
            self._venues: dict = {}
            self._venue_models: dict = {}
            self._waiting: dict = {}
            self._page_ready = False
            self._web: Any = None
            self._layout = QVBoxLayout(self)
            self._layout.setContentsMargins(0, 0, 0, 0)
            self._layout.setSpacing(0)

        # -- what the window reads ----------------------------------------

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
            """A copy of the payload each venue last published."""
            return dict(self._venue_models)

        def tablet_source(self) -> TabletSource:
            """The tablet reader the panel is fed from."""
            return self._tablet_source

        def fleet_source(self) -> FleetSource:
            """The fleet reader the tables are fed from."""
            return self._fleet_source

        def exchange_count(self) -> int:
            """How many venues ``add_exchange_tab`` has seated; EXCH reads it."""
            return len(self._venues)

        def layer(self) -> str:
            """The layer the page shows behind the panel slot."""
            return self._state.replay_layer

        # -- what the window pushes ---------------------------------------

        def show_models(self, fresh: Any) -> bool:
            """Hold one payload per bridge method and draw them on the page.

            Every feed pushed into the Sim tab arrives here, so a page built
            later still opens on what the tab last held.
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

        def show_votes(self, payload: Any) -> bool:
            """Hold one voting-panel payload and draw it on the page."""
            held = dict(payload or {})
            if not held:
                return False
            held["method"] = PANEL_METHOD
            held.setdefault(
                "flip_button", tab_surface.flip_button(sim.LAYER_INDICATORS)
            )
            self._votes = held
            return self.show_models({PANEL_METHOD: held})

        def show_log_call(self, action: str, message: str = "", level: Any = None):
            """Apply one ``SimStatusLog`` call to the tab's log and draw its lines.

            ``log``, ``force_log``, ``notice``, ``pause`` and ``resume`` are
            the calls ``set_relay`` reports.
            """
            asked = log_request(action, message, level)
            if asked is None:
                return False
            return self.show_models({LOG_METHOD: log_payload(self._log, asked)})

        def show_tab(self, asked: Any = None) -> bool:
            """Apply ``asked`` to the tab state and draw the tab on the page.

            ``layer``, ``replay_layer``, ``activity_paused`` and ``api_paused``
            persist in the state; ``api_lines`` is spent on the call that
            carries it.
            """
            return self.show_models({tab_surface.METHOD: self._state.view_model(asked)})

        def add_exchange_tab(self, exchange_id: str, display_name: str) -> None:
            """Seat one venue's models and draw its page in the layer stack."""
            if exchange_id in self._venues:
                return
            self._venues[exchange_id] = SimVenue(exchange_id, display_name, self._log)
            self._state.seat(exchange_id, display_name)
            self._venue_published()
            self.show_tab({})

        # -- what the operator presses ------------------------------------

        def show_layer(self, layer: str) -> str:
            """Show ``layer`` behind the panel slot and redraw the tab."""
            if layer in sim.LAYERS:
                self.show_tab({tab_surface.REPLAY_LAYER_PARAM: layer})
            return self._state.replay_layer

        def flip_layer(self) -> str:
            """Swap the page between the panel layer and the replay layer."""
            other = (
                sim.LAYER_PLAYBACK
                if self._state.replay_layer == sim.LAYER_INDICATORS
                else sim.LAYER_INDICATORS
            )
            return self.show_layer(other)

        def run_action(self, payload: str) -> None:
            """Answer the flip the page asked for; every other ask is held."""
            try:
                asked = json.loads(payload)
            except ValueError:
                logger.warning("The Sim page sent an ask that is not JSON")
                return
            method = str(asked.get("method") or "")
            params = asked.get("params")
            params = params if isinstance(params, dict) else {}
            if method == tab_surface.METHOD:
                layer = params.get(tab_surface.REPLAY_LAYER_PARAM)
                if layer in sim.LAYERS:
                    self.show_layer(str(layer))
            elif method == PANEL_METHOD and params.get("action") == "flip_layer":
                self.flip_layer()

        # -- construction -------------------------------------------------

        def showEvent(self, event) -> None:  # noqa: N802
            """Build the web view the first time the tab is shown."""
            super().showEvent(event)
            self.build_panel()

        def build_panel(self) -> None:
            """Create the tab's web view and load its page, once."""
            if self._web is not None:
                return
            self._models = models(self._state, self._log, self._panel)
            if self._votes:
                self._models[PANEL_METHOD] = self._votes
            self._waiting = {}
            self._venue_models = venue_models(self._venues)
            self._web = QWebEngineView(self)
            self._web.setAccessibleName(ACCESSIBLE_NAME)
            self._web.setPage(SimTradingPage(self))
            self._web.loadFinished.connect(self._on_load_finished)
            self._web.setHtml(panel_html(self._models, self._venue_models, self._theme))
            self._layout.addWidget(self._web, 1)

        def _venue_published(self) -> None:
            """Re-read every seated venue and push the fleet to the page."""
            self._venue_models = venue_models(self._venues)
            if self._page_ready and self._web is not None:
                self._web.page().runJavaScript(push_script(self._venue_models))

        def _on_load_finished(self, ok: bool) -> None:
            self._page_ready = bool(ok)
            if not ok:
                logger.warning("The React Sim tab page failed to load")
                return
            self._venue_published()
            waited = dict(self._waiting)
            self._waiting = {}
            if waited:
                self._web.page().runJavaScript(models_script(waited))
            elif self._votes:
                self._web.page().runJavaScript(votes_script(self._votes))
