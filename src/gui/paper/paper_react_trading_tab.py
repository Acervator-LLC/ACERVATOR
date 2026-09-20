# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
"""The Paper tab drawn by React inside ``QWebEngineView``, forked from
``react_trading_tab``.

``PaperTradingTabReact`` is ``TradingTabReact`` under the Paper Trader's name:
it draws ``src/gui/web/paper_trading_tab.js`` through the Electron shell's
``panel_host.js``, holds ``PaperFleetSource``, ``PaperBotManager``,
``PaperLedger`` and its own ``APIInteractionLog`` as ``PaperTradingTab`` does,
and ``add_exchange_tab`` seats one ``PaperVenue`` per exchange
``PaperFleetSource.exchanges`` names through ``_sync_exchange_tabs``, at build
and on every ``fleet_changed``, which first writes the paper fleet file through
``PaperFleetSource.save``. ``PaperTradingPage`` reads the page's asks off the
console line the host script writes, and ``run_action`` answers the corner and
card way-ins through ``_way_in``, the two pause presses through
``set_activity_paused`` and ``set_api_paused``, a venue sub-tab press, the
panel's ``select_bot``, both bot tables' asks and the venue page's ``+ New Bot``
(``_create_bot``), Privacy Mode and command bar (``_on_bot_command`` over
``PaperBotManager``), a row's Fire (``_on_bot_fire``) and Detail
(``_on_bot_detail`` over ``surface_class(PAPER_BOT_DETAIL)``). ``_on_api_event``
pushes each entry of the host's own ``APIInteractionLog`` as one of
``api_lines`` through ``show_tab``, reached through ``_cross_api_event`` and
``apiEntryLogged`` so a read on a worker thread lands on the GUI thread, and
``aggregate`` is ``strip_aggregate`` over the held records and
``PaperLedger.figures``, what the header strip reads while Paper is in front.
``_start_paper_run`` is the Simulator's ``_start_run`` forked: Start Paper
Run opens ``paper_run.start`` over the held fleet under ``run_rule`` and
starts one ``PaperRunner`` on the ``RUN_THREAD_NAME`` thread, which ticks
every record whose state reads ``running`` over ``exchange()``; while it
runs the page's run button reads ``STOP_RUN_TEXT`` through ``show_tab``
and its press reaches ``_stop_paper_run``, the fork of ``_stop_run``, and
``_take_paper_run`` on ``run_finished`` writes ``run_ended_line`` and
redraws the button; each fill crosses on ``run_trade``, each runner line
on ``run_line`` and the ledger's figures on ``run_figures`` to
``_take_figures``, so ``aggregate`` reads a snapshot and never the runner's
balances.
The host holds one ``PaperExchange`` over that log, and ``_read_feed`` runs
``read_fleet`` over it on a worker thread after each Import Live Fleet, whose
summary ``feedRead`` carries to ``_on_feed_read`` and one ``feed_line``.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any, Optional

from ...core.sound_engine import get_sound_engine
from ...exchange.api_logger import APIInteractionLog
from ...paper import paper_run
from ...paper.fake_balance import PaperLedger
from ...paper.fleet_source import (
    PaperFleetSource,
    SendRefused,
    exchange_choice,
    strip_aggregate,
)
from ...paper.paper_bot_manager import PaperBotManager
from ...paper.paper_bot_view import PaperBotView
from ...paper.paper_exchange import PaperExchange, read_fleet
from ...paper.paper_run import PaperRun, PaperRunner, PaperTrade
from ..main_tabs import bot_status_table_surface as scrum_surface
from ..main_tabs import design_system_surface as token_surface
from ..main_tabs import extractor_bot_table_surface as extractor_surface
from ..main_tabs import indicator_panel_surface, status_log_surface
from ..main_tabs.trading_tab_surface import (
    EXCHANGE_PARAM,
    WATCHDOG_INTERVAL_MS,
    WATCHDOG_STAT_FAILURE_FORMAT,
    WatchdogState,
    exchange_display_name,
)
from ..react_history_panel import STYLE_SOURCE_ASSETS, page_html, read_asset
from ..react_main_window import read_renderer_asset
from ..react_trading_tab import settled_frames
from ..variant_surface import PAPER_BOT_DETAIL, surface_class
from . import paper_bot_status_table_surface as paper_scrum_surface
from . import paper_exchange_tab_surface as venue_surface
from . import paper_trading_tab_surface as tab_surface
from .paper_indicator_panel import describe_no_data_cause, rate_fields
from .paper_status_log import PaperStatusLogModel

try:
    from PySide6.QtCore import QTimer, Signal
    from PySide6.QtWebEngineCore import QWebEnginePage
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWidgets import QDialog, QMessageBox, QVBoxLayout, QWidget

    from .paper_exchange_choice import PaperExchangeChoiceDialog

    _HAS_WEBENGINE = True
except ImportError:
    # Without WebEngine, PaperTradingTabReact is never defined and its import
    # fails by name.
    _HAS_WEBENGINE = False

logger = logging.getLogger("acervator.gui.paper_react_trading_tab")

ACCESSIBLE_NAME = tab_surface.HEADING

#: The element ``paper_trading_tab.js`` draws the tab into.
PANEL_ROOT_ID = "panel-root"

#: The renderer module the page draws.
PANEL_MODULE = "paper_trading_tab.js"

#: The modules ``paper_trading_tab.js`` mounts into its own slots. Order is
#: load order. ``paper_exchange_tab.js`` mounts the three modules ahead of it.
CHILD_MODULES: tuple[str, ...] = (
    "paper_status_log.js",
    "paper_indicator_panel.js",
    "paper_table_cells.js",
    "paper_bot_status_table.js",
    "paper_extractor_bot_table.js",
    "paper_exchange_tab.js",
)

#: The style sheets the page carries: Live's own two.
STYLE_ASSETS: tuple[str, ...] = ("trading_tab.css", "exchange_tab.css")

#: The bridge method each forked module asks.
SCRUM_METHOD = "paper_bot_status_table.state"
EXTRACTOR_METHOD = "paper_extractor_bot_table.state"
PANEL_METHOD = "paper_indicator_panel.state"
LOG_METHOD = "paper_status_log.lines"

#: The log payload's document field and the list of lines under it, which the
#: page's own answer to a log ask carries as the document the page holds.
LOG_DOCUMENT_FIELD = "document"
LOG_LINES_FIELD = "lines"

#: The global each module defines once it has run to its end.
MODULE_GLOBALS: dict[str, str] = {
    "design_tokens.js": "acervatorTokens",
    "theme_engine.js": "acervatorThemes",
    "shared_widgets.js": "acervatorWidgets",
    "header_strip.js": "acervatorHeader",
    "paper_status_log.js": "acervatorPaperLog",
    "paper_indicator_panel.js": "acervatorPaperIndicatorPanel",
    "paper_table_cells.js": "acervatorPaperCells",
    "paper_bot_status_table.js": "acervatorPaperBotTable",
    "paper_extractor_bot_table.js": "acervatorPaperExtractorTable",
    "paper_exchange_tab.js": "acervatorPaperExchangeTab",
    PANEL_MODULE: "acervatorPaperTrading",
}

#: The setter each venue module publishes for the payload of its own method.
VENUE_SETTERS: dict[str, str] = {
    SCRUM_METHOD: "acervatorSetPaperBotTable",
    EXTRACTOR_METHOD: "acervatorSetPaperExtractorTable",
    venue_surface.METHOD: "acervatorSetPaperExchangeTab",
}

#: The setter ``design_tokens.js`` publishes for the design-system payload.
DESIGN_SETTER = "acervatorSetTokens"

#: The global whose ``forget`` drops the one ask a module caches, by method.
MODULE_FORGETS: dict[str, str] = {
    PANEL_METHOD: "acervatorPaperIndicatorPanel",
    venue_surface.METHOD: "acervatorPaperExchangeTab",
}

#: The request fields that carry a press on the bot table.
TABLE_PRESS_PARAMS: tuple[str, ...] = (
    scrum_surface.FIRE_PARAM,
    scrum_surface.DETAIL_PARAM,
    scrum_surface.HEADER_CLICK_PARAM,
    scrum_surface.CELL_CLICK_PARAM,
)

#: The request fields that carry the venue page's ``+ New Bot`` press, its
#: command-bar press and its Privacy Mode press.
VENUE_PRESS_PARAMS: tuple[str, ...] = (
    venue_surface.live.NEW_BOT_PARAM,
    venue_surface.live.COMMAND_PARAM,
    venue_surface.live.PRIVACY_PARAM,
)

#: The ``action`` values that carry a press on the Extractor table.
EXTRACTOR_PRESS_ACTIONS: tuple[str, ...] = (
    extractor_surface.DETAIL_ACTION,
    extractor_surface.SELECT_ACTION,
)

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
LOADED_MODULES_JS = "window.acervatorPaperTradingPage.modules().join(',')"

#: The JS expression naming each style sheet the page holds and its rule count.
LOADED_STYLES_JS = "JSON.stringify(window.acervatorPaperTradingPage.styles())"

#: The JS expression counting the bot rows each table space really drew.
DRAWN_ROWS_JS = "JSON.stringify(window.acervatorPaperTradingPage.rows())"

#: The JS expression naming the bot the voting panel is showing.
SHOWN_BOT_JS = 'window.acervatorPaperIndicatorPanel.field("selected_bot_id")'

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
ACTION_PREFIX = "acervator-paper:"

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
  var LOG_DOCUMENT = %(log_document)s;
  var LOG_LINES = %(log_lines)s;
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

  // paper_exchange_tab.js answers a second ask from the first ask's payload,
  // so forget() runs before a fresh fleet is seated and drawn.
  function hold(venues) {
    VENUES = venues;
    var venue = global.acervatorPaperExchangeTab;
    if (venue && typeof venue.forget === "function") {
      venue.forget();
    }
    seat();
    var tab = global.acervatorPaperTrading;
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

  // LOG appends its batch and keeps the whole held document in MODELS for
  // the page's own ask; TAB replaces the tab's model; the rest drop their cache.
  function holdModels(fresh) {
    Object.keys(fresh).forEach(function (method) {
      if (method === LOG) {
        var spool = global.acervatorPaperLog;
        if (spool && typeof spool.take === "function") {
          spool.take(fresh[method]);
          var whole = JSON.parse(JSON.stringify(fresh[method]));
          var carried = {};
          carried[LOG_LINES] = spool.lines();
          whole[LOG_DOCUMENT] = carried;
          MODELS[method] = whole;
        }
        return;
      }
      MODELS[method] = fresh[method];
      if (method === TAB) {
        var setter = global.acervatorSetPaperTrading;
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
    var tab = global.acervatorPaperTrading;
    return tab && typeof tab.redraw === "function" ? tab.redraw() : 0;
  }

  function votes(model) {
    var fresh = {};
    fresh[IVP] = model;
    return holdModels(fresh);
  }

  global.acervatorPaperTradingPage = {
    modules: modules,
    styles: styles,
    rows: rows,
    hold: hold,
    votes: votes,
    holdModels: holdModels
  };

  seat();
  global.acervatorPaperTradingTabDrawn = global.acervatorPanelHost.open(
    NAME,
    doc.getElementById(ROOT)
  );
})(window, document);"""


def module_name(asset: str = PANEL_MODULE) -> str:
    """``asset`` without its ``.js`` suffix, which is the panel's own name."""
    return asset.rsplit(".", 1)[0]


def roster() -> tuple[str, ...]:
    """Every module the page carries, in load order; ``STYLE_SOURCE_ASSETS``
    leads, as ``paper_trading_tab.js`` parses every Qt style sheet in its
    payload with ``header_strip.styleOf``."""
    return STYLE_SOURCE_ASSETS + CHILD_MODULES + (PANEL_MODULE,)


def panel_payload(panel: indicator_panel_surface.IndicatorPanelModel) -> dict:
    """The voting panel's payload under ``PANEL_METHOD``."""
    payload = dict(indicator_panel_surface.build_payload(panel))
    payload["method"] = PANEL_METHOD
    return payload


def log_payload(
    log: status_log_surface.StatusLogModel, asked: Optional[dict] = None
) -> dict:
    """The Activity Log's payload under ``LOG_METHOD`` after one request, the
    lines ``log_at`` painted since the last push ahead of this request's batch."""
    request = dict(asked or {})
    paused = request.get("paused")
    whole = bool(request.get("whole", False))
    pending = log.take_painted()
    payload = status_log_surface.build_view_model(
        log,
        request.get("messages") or [],
        paused=None if paused is None else bool(paused),
        toggle=bool(request.get("toggle", False)),
        notices=request.get("notices") or [],
        whole=whole,
    )
    if pending and not whole:
        payload["document"] = {"lines": pending + list(payload["document"]["lines"])}
    return payload


def models(
    state: tab_surface.PaperTradingTabState,
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


class PaperVenue:
    """One seated venue's three models, which the page draws from; ``update_bots``
    is ``ExchangeTabReact.update_bots`` forked, and ``answer`` applies one ask
    from either bot table so a Fire or a Detail on the page reaches its handler."""

    def __init__(
        self,
        exchange_id: str,
        exchange_name: str,
        status_log: Any = None,
        on_bot_clicked: Any = None,
        on_bot_fire: Any = None,
        on_new_bot: Any = None,
        on_bot_cmd: Any = None,
    ) -> None:
        self.exchange_id = exchange_id
        self.exchange_name = exchange_name
        self.screen = venue_surface.screen(
            exchange_id,
            exchange_name,
            status_log,
            on_bot_clicked=on_bot_clicked,
            on_bot_fire=on_bot_fire,
            on_new_bot=on_new_bot,
            on_bot_cmd=on_bot_cmd,
        )
        self.scrum = paper_scrum_surface.PaperBotStatusTableModel(
            on_bot_clicked=self._scrum_detail,
            on_fire_clicked=on_bot_fire,
        )
        self.scrum.exchange_id = exchange_id
        self.extractor = extractor_surface.ExtractorBotTableModel(
            on_bot_clicked=self._extractor_detail,
        )
        self.extractor.exchange_id = exchange_id

    def models(self) -> dict:
        """The payload of each venue method, under the Paper Trader's names."""
        extractor = dict(extractor_surface.build_payload(self.extractor))
        extractor["method"] = EXTRACTOR_METHOD
        return {
            venue_surface.METHOD: venue_surface.build_view_model(self.screen),
            SCRUM_METHOD: paper_scrum_surface.build_view_model(self.scrum),
            EXTRACTOR_METHOD: extractor,
        }

    def update_bots(self, statuses: list) -> None:
        """Route one fleet list to the screen and to both bot tables."""
        venue_surface.drive(self.screen, {venue_surface.live.STATUSES_PARAM: statuses})
        paper_scrum_surface.drive(
            self.scrum,
            {scrum_surface.STATUSES_PARAM: scrum_surface.scrumming_statuses(statuses)},
        )
        extractor_surface.drive(
            self.extractor,
            {
                extractor_surface.ACTION_PARAM: extractor_surface.UPDATE_ACTION,
                extractor_surface.BOT_STATUSES_PARAM: (
                    extractor_surface.extractor_statuses(statuses)
                ),
            },
        )

    def answer(self, method: str, params: dict) -> bool:
        """Apply one press the page made on this venue's bot tables, its
        ``+ New Bot``, its command bar or its Privacy Mode; a read ask carrying
        none of ``TABLE_PRESS_PARAMS``, ``EXTRACTOR_PRESS_ACTIONS`` or
        ``VENUE_PRESS_PARAMS`` changes nothing."""
        if method == venue_surface.METHOD:
            if not any(params.get(name) is not None for name in VENUE_PRESS_PARAMS):
                return False
            venue_surface.drive(self.screen, params)
            return True
        if method == EXTRACTOR_METHOD:
            if (
                params.get(extractor_surface.ACTION_PARAM)
                not in EXTRACTOR_PRESS_ACTIONS
            ):
                return False
            extractor_surface.drive(self.extractor, params)
            return True
        if method != SCRUM_METHOD:
            return False
        if not any(params.get(name) is not None for name in TABLE_PRESS_PARAMS):
            return False
        paper_scrum_surface.drive(self.scrum, params)
        return True

    def _row_of(self, table: Any, bot_id: str) -> int:
        ids = list(table.bot_ids)
        return (
            ids.index(bot_id) if bot_id in ids else venue_surface.live.NO_SELECTION_ROW
        )

    def _scrum_detail(self, bot_id: str) -> None:
        self.screen.select_scrum_row(self._row_of(self.scrum, bot_id))
        self.screen.scrum_clicked(bot_id)

    def _extractor_detail(self, bot_id: str) -> None:
        self.screen.select_extractor_row(self._row_of(self.extractor, bot_id))
        self.screen.extractor_clicked(bot_id)


def venue_of_ask(method: str, params: dict) -> str:
    """The exchange one ask names: the venue page keys it ``exchange_id``
    (``venue_surface.live.EXCHANGE_ID_PARAM``), the Extractor table
    ``extractor_surface.EXCHANGE_ID_PARAM``, the Scrumming table
    ``for_exchange`` (``paper_scrum_surface.venue_of``)."""
    if method == venue_surface.METHOD:
        return str(params.get(venue_surface.live.EXCHANGE_ID_PARAM) or "")
    if method == EXTRACTOR_METHOD:
        return str(params.get(extractor_surface.EXCHANGE_ID_PARAM) or "")
    return paper_scrum_surface.venue_of(params)


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
        "log_document": json.dumps(LOG_DOCUMENT_FIELD, ensure_ascii=True),
        "log_lines": json.dumps(LOG_LINES_FIELD, ensure_ascii=True),
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
    """The ``paper_status_log.lines`` request one ``PaperStatusLog`` call makes."""
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
        "window.acervatorPaperTradingPage.votes("
        + json.dumps(dict(payload or {}), ensure_ascii=True)
        + ");"
    )


def models_script(fresh: dict) -> str:
    """The one JS statement handing the page a fresh payload per method."""
    return (
        "window.acervatorPaperTradingPage.holdModels("
        + json.dumps(dict(fresh or {}), ensure_ascii=True)
        + ");"
    )


def push_script(venues: dict) -> str:
    """The one JS statement handing the page a fresh payload for each venue;
    ``ensure_ascii=True`` escapes U+2028 and U+2029, which are legal inside a
    JSON string and are JavaScript line terminators."""
    return (
        "window.acervatorPaperTradingPage.hold("
        + json.dumps(dict(venues or {}), ensure_ascii=True)
        + ");"
    )


def _tag(source: str) -> str:
    """``source`` wrapped in a script tag of its own."""
    return "<script>" + source + "</script>"


def page_body() -> str:
    """The page's body: the root, the panel host, React, then every module;
    ``namer_script`` runs before any module, so a ``register`` call is given
    the name the module cannot read off its own inlined script tag."""
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
    """The whole Paper page as one string, with no network fetch;
    ``STYLE_ASSETS`` is inlined into the page head."""
    return page_html(
        STYLE_ASSETS, (), page_body(), theme, (host_script(built, venues),)
    )


if _HAS_WEBENGINE:

    class PaperTradingPage(QWebEnginePage):
        """Routes the page's ``acervator-paper:`` console lines to its owner."""

        def __init__(self, owner) -> None:
            """Hold ``owner`` as the widget that answers the page."""
            super().__init__(owner)
            self._owner = owner

        def javaScriptConsoleMessage(self, level, message, line, source) -> None:
            """Hand a bridge ask to the owner and drop every other line."""
            del level, line, source
            if message.startswith(ACTION_PREFIX):
                self._owner.run_action(message[len(ACTION_PREFIX) :])

    class PaperTradingTabReact(QWidget):
        """The Paper tab, drawn by ``paper_trading_tab.js`` and its child
        modules; ``build_panel`` loads the page once, on the first show, and
        ``add_exchange_tab`` seats one venue whose payloads the page draws."""

        #: Fired by whatever loads a fleet; the venue sub-tabs re-seat on it.
        fleet_changed = Signal()
        #: One ``APIInteractionLog`` entry, queued onto the GUI thread for ``_on_api_event``.
        apiEntryLogged = Signal(object)  # noqa: N815 - Qt signal name
        #: One ``read_fleet`` summary, queued onto the GUI thread for ``_on_feed_read``.
        feedRead = Signal(object)  # noqa: N815 - Qt signal name
        #: One runner line and its level, queued onto the GUI thread.
        run_line = Signal(str, str)
        #: One ``PaperTrade``, queued onto the GUI thread for ``_take_trade``.
        run_trade = Signal(object)
        #: The ``PaperRun`` the runner ended with, queued for ``_take_paper_run``.
        run_finished = Signal(object)
        #: The ledger's figures after a worked pass, queued for ``_take_figures``.
        run_figures = Signal(object)

        def __init__(
            self,
            fleet_source: Optional[PaperFleetSource] = None,
            parent: Optional[QWidget] = None,
            theme: object = None,
            api_log: Optional[APIInteractionLog] = None,
            exchange: Optional[PaperExchange] = None,
        ) -> None:
            """Hold the fleet source the tab's view models are built from, the
            API log ``_on_api_event`` listens to, and the ``PaperExchange``
            recording on it."""
            super().__init__(parent)
            self.setObjectName(ACCESSIBLE_NAME)
            self.setAccessibleName(ACCESSIBLE_NAME)
            self._fleet_source = (
                fleet_source if fleet_source is not None else PaperFleetSource()
            )
            self._api_log = api_log if api_log is not None else APIInteractionLog()
            self._exchange = (
                exchange
                if exchange is not None
                else PaperExchange(api_log=self._api_log)
            )
            self._bot_manager = PaperBotManager(self._fleet_source)
            self._ledger = PaperLedger()
            self._figures: dict = {}
            self._states: dict = {}
            self._runner: Optional[PaperRunner] = None
            self._fills: list[PaperTrade] = []
            self._theme = theme
            self._state = tab_surface.PaperTradingTabState()
            self._log = PaperStatusLogModel()
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
            self.fleet_changed.connect(self._fleet_source.save)
            self.fleet_changed.connect(self._sync_exchange_tabs)
            self._sync_exchange_tabs()
            self.apiEntryLogged.connect(self._on_api_event)
            self._api_log.add_listener(self._cross_api_event)
            self.feedRead.connect(self._on_feed_read)
            self.run_line.connect(self.log)
            self.run_trade.connect(self._take_trade)
            self.run_finished.connect(self._take_paper_run)
            self.run_figures.connect(self._take_figures)
            # Polls StatusLogModel.health_stats() every 60s on the GUI thread.
            self._activity_log_watchdog_state = WatchdogState()
            self._activity_log_watchdog_timer = QTimer(self)
            self._activity_log_watchdog_timer.timeout.connect(
                self._activity_log_watchdog
            )
            self._activity_log_watchdog_timer.start(WATCHDOG_INTERVAL_MS)

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

        def fleet_source(self) -> PaperFleetSource:
            """The fleet reader the tables are fed from."""
            return self._fleet_source

        def bot_manager(self) -> PaperBotManager:
            """The forked bot manager the command bar moves records through."""
            return self._bot_manager

        def ledger(self) -> PaperLedger:
            """The paper ledger the strip's four money figures read."""
            return self._ledger

        def aggregate(self) -> dict:
            """The header strip's figures, ``strip_aggregate`` over the held
            fleet and the ledger figures the runner last posted through
            ``run_figures``."""
            return strip_aggregate(self._fleet_source.bots(), self._figures)

        def figures(self) -> dict:
            """The ledger figures the runner last posted, empty before a run."""
            return dict(self._figures)

        def runner(self) -> Optional[PaperRunner]:
            """The ``PaperRunner`` of the run in flight or last finished, or None."""
            return self._runner

        def run(self) -> Optional[PaperRun]:
            """The ``PaperRun`` in flight or last finished, or None before one."""
            return self._runner.run if self._runner is not None else None

        def run_running(self) -> bool:
            """True while the ``RUN_THREAD_NAME`` worker thread is alive."""
            return self._runner is not None and self._runner.running()

        def fills(self) -> list[PaperTrade]:
            """Every ``PaperTrade`` the run in flight or last finished handed
            ``run_trade``, in fill order; empty before the first run."""
            return list(self._fills)

        def api_log(self) -> APIInteractionLog:
            """The host's own API log; every entry it records reaches the pane."""
            return self._api_log

        def exchange(self) -> PaperExchange:
            """The host's ``PaperExchange``, recording every venue call on ``api_log``."""
            return self._exchange

        def exchange_count(self) -> int:
            """How many venues ``add_exchange_tab`` has seated; EXCH reads it."""
            return len(self._venues)

        # -- the ways in --------------------------------------------------

        def _way_in(self, action: str) -> None:
            """Run the corner or card press ``action``: ``_import_live_fleet``
            for Import Live Fleet, ``_start_paper_run`` for Start Paper Run with
            no run up, ``_stop_paper_run`` for the same seat while one is up."""
            if action == tab_surface.IMPORT_LIVE_FLEET_ACTION:
                self._import_live_fleet()
                return
            if action in (tab_surface.START_RUN_ACTION, tab_surface.STOP_RUN_ACTION):
                if self.run_running():
                    self._stop_paper_run()
                elif action == tab_surface.START_RUN_ACTION:
                    self._start_paper_run()
                return
            self.log(f"{action} is not a way in.", "error")

        def _start_paper_run(self) -> None:
            """Start Paper Run: ``paper_run.start`` over the held fleet under
            ``run_rule`` of ``exchange().venue()``, one ``PaperRunner`` on the
            ``RUN_THREAD_NAME`` thread reading ``_states``, the started line,
            and the page's run button redrawn Stop; a fleet holding no record
            or a venue with no cited rule writes one line and starts nothing."""
            bots = self._fleet_source.bots()
            if not bots:
                self.log(tab_surface.RUN_NO_BOT_TEXT, "warning")
                return
            venue = self._exchange.venue()
            rule = paper_run.run_rule(venue)
            if rule is None:
                self.log(tab_surface.run_no_rule_line(venue), "warning")
                return
            run = paper_run.start(bots, rule)
            self._ledger = run.ledger
            self._figures = run.figures()
            self._fills = []
            self._refresh_states()
            self._runner = PaperRunner(
                run,
                self._exchange,
                self._read_states,
                on_trade=self.run_trade.emit,
                on_figures=self.run_figures.emit,
                on_finished=self.run_finished.emit,
                say=lambda line: self.run_line.emit(line, "info"),
            )
            self._runner.start()
            self.log(
                tab_surface.run_started_line(
                    len(bots),
                    len(tab_surface.running_bot_ids(bots)),
                    run.ledger.fleet_target_usd,
                ),
                "success",
            )
            self._state.run_running = True
            self.show_tab({})

        def _stop_paper_run(self) -> None:
            """Stop Paper Run: ``RUN_STOPPING_TEXT`` and the event the runner
            reads before each tick; ``run_finished`` follows from the thread."""
            self.log(tab_surface.RUN_STOPPING_TEXT, "warning")
            if self._runner is not None:
                self._runner.stop()

        def _take_paper_run(self, run: PaperRun) -> None:
            """The runner's end on the GUI thread: the final figures held,
            ``run_ended_line`` written and the run button redrawn Start."""
            self._figures = run.figures()
            self.log(tab_surface.run_ended_line(run), "info")
            self._state.run_running = False
            self.show_tab({})

        def _take_figures(self, figures: dict) -> None:
            """Hold the ledger figures the runner posted, what ``aggregate`` reads."""
            self._figures = dict(figures or {})

        def _take_trade(self, trade: PaperTrade) -> None:
            """Hold one fill the runner posted, in fill order."""
            self._fills.append(trade)

        def _read_states(self) -> dict:
            """The state per held ``bot_id`` as of the last ``_refresh_states``,
            the map the runner reads on its own thread."""
            return self._states

        def _refresh_states(self) -> dict:
            """Rebuild ``_states`` from ``PaperBotManager.bots`` on the GUI thread."""
            self._states = {bot.bot_id: bot.state for bot in self._bot_manager.bots()}
            return self._states

        def _import_live_fleet(self) -> None:
            """Import Live Fleet: ``exchange_choice`` over the exchanges
            ``PaperFleetSource.stored_exchanges`` names, ``PaperExchangeChoiceDialog``
            when it prompts, then ``PaperFleetSource.import_live_fleet`` on the
            exchange chosen, one Activity Log line and ``fleet_changed``."""
            options = self._fleet_source.stored_exchanges()
            if not options:
                self.log(tab_surface.no_stored_bot_line(), "warning")
                return
            choice = exchange_choice(options)
            chosen = choice["chosen"]
            if choice["prompt"]:
                dialog = PaperExchangeChoiceDialog(options, self)
                if dialog.exec() != QDialog.Accepted:
                    self.log(tab_surface.IMPORT_CANCELLED_TEXT, "warning")
                    return
                chosen = dialog.chosen()
            imported = self._fleet_source.import_live_fleet(chosen)
            self.log(tab_surface.imported_line(len(imported), chosen), "success")
            self.fleet_changed.emit()
            self._read_feed([bot.symbol for bot in imported])

        def _read_feed(self, symbols: list) -> None:
            """Run ``read_fleet`` over ``exchange()`` for ``symbols`` on one
            ``FEED_THREAD_NAME`` worker thread; its summary crosses ``feedRead``."""
            if not symbols:
                return

            def run() -> None:
                summary = read_fleet(self._exchange, symbols)
                try:
                    self.feedRead.emit(summary)
                except RuntimeError:
                    # The host was deleted while the reads ran; nothing draws the line.
                    return

            threading.Thread(
                target=run, name=tab_surface.FEED_THREAD_NAME, daemon=True
            ).start()

        def _on_feed_read(self, summary: dict) -> None:
            """Write one ``feed_line`` for ``summary`` on the Activity Log."""
            text, level = tab_surface.feed_line(summary)
            self.log(text, level)

        # -- what the window pushes ---------------------------------------

        def show_models(self, fresh: Any) -> bool:
            """Hold one payload per bridge method and draw them on the page;
            a page built later still opens on what the tab last held."""
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
            self._votes = held
            return self.show_models({PANEL_METHOD: held})

        def show_log_call(self, action: str, message: str = "", level: Any = None):
            """Apply one ``PaperStatusLog`` call to the tab's log and draw its
            lines; ``log``, ``force_log``, ``notice``, ``pause`` and ``resume``
            are the calls ``set_relay`` reports."""
            asked = log_request(action, message, level)
            if asked is None:
                return False
            return self.show_models({LOG_METHOD: log_payload(self._log, asked)})

        def show_tab(self, asked: Any = None) -> bool:
            """Apply ``asked`` to the tab state and draw the tab on the page;
            ``layer``, ``activity_paused`` and ``api_paused`` persist in the
            state and ``api_lines`` is spent on the call that carries it."""
            return self.show_models({tab_surface.METHOD: self._state.view_model(asked)})

        def add_exchange_tab(self, exchange_id: str, display_name: str) -> None:
            """Seat one venue's models and draw its page in the layer stack."""
            if exchange_id in self._venues:
                return
            self._venues[exchange_id] = PaperVenue(
                exchange_id,
                display_name,
                self,
                on_bot_clicked=self._on_bot_detail,
                on_bot_fire=self._on_bot_fire,
                on_new_bot=self._create_bot,
                on_bot_cmd=self._on_bot_command,
            )
            self._state.seat(exchange_id, display_name)
            self._venue_published()
            self.show_tab({})

        def refresh_bots(self) -> int:
            """Hand every seated venue its rows from ``PaperFleetSource.statuses``
            and push the fleet to the page; answers how many rows were handed out."""
            handed = 0
            for eid, venue in list(self._venues.items()):
                statuses = self._fleet_source.statuses(eid)
                venue.update_bots(statuses)
                handed += len(statuses)
            self._venue_published()
            return handed

        def refresh_votes(self) -> dict:
            """Hand the panel model the fleet's statuses, the fleet's own rate
            snapshot and the selected bot's reading, then draw it on the page."""
            statuses = self._fleet_source.statuses()
            self._panel.set_bots(statuses)
            self._panel.set_rates(rate_fields(tab_surface.rate_snapshot(statuses)))
            return self._feed_votes(self._panel.selected_bot_id)

        def _feed_votes(self, bot_id: str = "") -> dict:
            """Apply ``ivp_feed`` for ``bot_id``, or the selected bot, to the panel
            model, step the bars ``settled_frames`` times as Live's push does,
            and push the payload through ``show_votes``."""
            chosen = str(bot_id or self._panel.selected_bot_id or "")
            feed = tab_surface.ivp_feed(
                self._fleet_source.bot_for(chosen) if chosen else None
            )
            cause = str(feed.get("cause") or "")
            message = (
                describe_no_data_cause(cause, feed.get("detail"))
                if cause
                else str(feed.get("reason") or "")
            )
            self._panel.show_no_data(message, cause)
            for _frame in range(settled_frames()):
                self._panel.bars_a.step()
                self._panel.bars_b.step()
            self.show_votes(panel_payload(self._panel))
            return feed

        # -- what the operator presses ------------------------------------

        def _create_bot(self, exchange_id: str = "") -> None:
            """A venue's ``+ New Bot`` press: one Activity Log line,
            ``new_bot_line``, naming Import Live Fleet as the fleet's way in."""
            self.log(tab_surface.new_bot_line(exchange_id), "warning")

        def _on_bot_fire(self, bot_id: str) -> None:
            """Manual Fire on a paper bot: ask ``PaperFleetSource`` to ``fire``
            and log the refusal, as the window logs a failed Fire."""
            try:
                self._fleet_source.fire(bot_id)
            except SendRefused as exc:
                self.show_log_call(
                    "log", f"Fire on {bot_id[:8]} failed: {exc}", "error"
                )

        def log(self, message: str, level: str = "info") -> None:
            """One Activity Log line through ``show_log_call``, the ``log`` a
            venue's ``ExchangeTabModel`` calls on its ``status_log``."""
            self.show_log_call("log", message, level)

        def _notify(self, message: str, level: str) -> None:
            """Write the window notification's line, ``notification_line``, into
            the Activity Log as a notice through ``show_log_call``."""
            self.show_log_call("notice", tab_surface.notification_line(message, level))

        def set_activity_paused(self, paused: bool) -> bool:
            """Pause or resume the tab's log and set the toggle's caption, as
            the Qt toggle's ``_on_activity_pause_toggled`` does; answers
            ``_log.paused``."""
            wanted = bool(paused)
            if wanted != self._log.paused:
                self.show_log_call("pause" if wanted else "resume")
            if wanted != self._state.activity_paused:
                self.show_tab({tab_surface.ACTIVITY_PAUSED_PARAM: wanted})
            return self._log.paused

        def set_api_paused(self, paused: bool) -> bool:
            """Pause or resume the state's ``ApiPauseBuffer`` and set the
            toggle's caption, as the Qt toggle's ``_on_api_pause_toggled``
            does; answers the buffer's ``paused``."""
            wanted = bool(paused)
            if wanted != self._state.api_buffer.paused:
                self.show_tab({tab_surface.API_PAUSED_PARAM: wanted})
            return self._state.api_buffer.paused

        def _cross_api_event(self, entry: dict) -> None:
            """The ``api_log()`` listener: emit ``apiEntryLogged``, which Qt
            queues onto the GUI thread for ``_on_api_event`` from any other thread."""
            self.apiEntryLogged.emit(entry)

        def _on_api_event(self, entry: dict) -> None:
            """Push one ``api_log()`` entry to the page as Live's block, refusing
            a call off the GUI thread; ``PaperTradingTabState`` appends it to
            the pane or holds it while paused."""
            current = threading.current_thread().name
            if tab_surface.api_event_off_thread(
                entry, "PaperTradingTabReact._on_api_event", current
            ):
                return
            self.show_tab({tab_surface.API_LINES_PARAM: [tab_surface.api_block(entry)]})

        def _activity_log_watchdog(self) -> None:
            """One tick of Live's Activity-Log watchdog over the tab's
            ``StatusLogModel`` and ``PaperBotManager.bots``: each line
            ``watchdog_lines`` answers is pushed as a ``force_log`` and written
            to the file logger."""
            try:
                stats = self._log.health_stats()
            except Exception as exc:  # noqa: BLE001 - Live's watchdog catches all
                logger.warning(WATCHDOG_STAT_FAILURE_FORMAT, exc)
                return
            lines = tab_surface.watchdog_lines(
                self._activity_log_watchdog_state,
                stats,
                self._bot_manager.bots(),
                time.time(),
            )
            for text, level in lines:
                self.show_log_call("force_log", text, level)
                logger.log(logging.ERROR if level == "error" else logging.WARNING, text)

        def _on_bot_command(self, bot_id: str, command: str) -> None:
            """One command-bar press on ``bot_id``: the window's
            ``_on_bot_command`` forked over ``PaperBotManager``, with no venue
            connect, Live's Activity Log lines, Live's sounds and Live's Delete
            box, and ``fleet_changed`` fired when the state moved or the record
            left."""
            bot = self._bot_manager.get_bot(bot_id)
            if not bot:
                self.log(f"Bot {bot_id} not found.", "error")
                return

            sound = get_sound_engine()
            moved = False

            if command == "start":
                try:
                    moved = self._bot_manager.start(bot_id) != bot.state
                    self.log(f"✓ Bot {bot_id} RUNNING.", "success")
                    self._notify(f"Bot {bot_id} RUNNING", "success")
                    sound.play_state_change()
                except Exception as exc:  # noqa: BLE001 - Live's handler catches all
                    self.log(f"Failed to start bot {bot_id}: {exc}", "error")
                    sound.play_error()

            elif command == "pause":
                self.log(f"Pausing bot {bot_id}...", "info")
                try:
                    moved = self._bot_manager.pause(bot_id) != bot.state
                    self.log(f"Bot {bot_id} paused.", "warning")
                    self._notify(f"Bot {bot_id} PAUSED", "warning")
                    sound.play_state_change()
                except Exception as exc:  # noqa: BLE001 - Live's handler catches all
                    self.log(f"Failed to pause bot {bot_id}: {exc}", "error")

            elif command == "stop":
                self.log(f"Stopping bot {bot_id}...", "info")
                try:
                    moved = self._bot_manager.stop(bot_id) != bot.state
                    self.log(f"Bot {bot_id} stopped.", "info")
                    self._notify(f"Bot {bot_id} STOPPED", "info")
                    sound.play_state_change()
                except Exception as exc:  # noqa: BLE001 - Live's handler catches all
                    self.log(f"Failed to stop bot {bot_id}: {exc}", "error")

            elif command == "restart":
                try:
                    self._bot_manager.restart(bot_id)
                    moved = True
                    self.log(f"✓ Bot {bot_id} restarted.", "success")
                    self._notify(f"Bot {bot_id} RESTARTED", "success")
                    sound.play_state_change()
                except Exception as exc:  # noqa: BLE001 - Live's handler catches all
                    self.log(f"Failed to restart bot {bot_id}: {exc}", "error")
                    sound.play_error()

            elif command == "delete":
                confirm = QMessageBox.question(
                    self,
                    "Delete Bot",
                    f"Delete bot {bot_id}? This cannot be undone.",
                    QMessageBox.Yes | QMessageBox.No,
                )
                if confirm == QMessageBox.Yes:
                    try:
                        self._bot_manager.stop(bot_id)
                    except (
                        Exception
                    ) as exc:  # noqa: BLE001 - Live's handler catches all
                        self.log(
                            f"Failed to stop bot {bot_id} before delete: {exc}.",
                            "error",
                        )
                    moved = self._bot_manager.unregister(bot_id)
                    self.log(f"Bot {bot_id} deleted.", "warning")
                    self._notify(f"Bot {bot_id} DELETED", "warning")
                    sound.play_state_change()

            if moved:
                self.fleet_changed.emit()

        def _on_bot_detail(self, bot_id: str) -> None:
            """Open ``_open_bot_detail`` on the next event-loop turn, after the
            page's console callback that carried the press has returned; a
            ``QWebEngineView`` opened inside another page's console callback
            never finishes loading."""
            QTimer.singleShot(0, lambda: self._open_bot_detail(bot_id))

        def _open_bot_detail(self, bot_id: str) -> None:
            """Open the Paper Trader's Bot Settings window,
            ``surface_class(PAPER_BOT_DETAIL)``, for ``bot_id`` over its
            ``PaperBotView`` and follow Prev and Next over the venue's paper
            fleet, keeping the geometry and the tab."""
            bot = self._fleet_source.bot_for(bot_id)
            if bot is None:
                return
            window_class = surface_class(PAPER_BOT_DETAIL)
            saved_geometry = None
            saved_tab_index = None
            while bot is not None:
                siblings = [
                    one.bot_id
                    for one in self._fleet_source.bots()
                    if one.exchange_id == bot.exchange_id
                ]
                rates = paper_scrum_surface.usd_rates(
                    self._fleet_source.statuses(bot.exchange_id)
                )
                view = PaperBotView(bot, self._fleet_source.record_for(bot.bot_id))
                dlg = window_class(view, siblings, self, rates)
                if saved_geometry is not None:
                    dlg.setGeometry(saved_geometry)
                if saved_tab_index is not None:
                    dlg._tabs.setCurrentIndex(int(saved_tab_index))
                dlg.exec()
                saved_geometry = dlg.geometry()
                saved_tab_index = dlg.active_tab_index()
                target_id = dlg._pending_navigate_to
                bot = self._fleet_source.bot_for(target_id) if target_id else None

        def _drop_unlisted_exchange_tabs(self, listed: list) -> int:
            """Take off every venue whose id is not in ``listed``; the page
            draws the Get Started card again once a layer holds none."""
            kept = set(listed)
            gone = [eid for eid in self._venues if eid not in kept]
            for eid in gone:
                del self._venues[eid]
                self._state.unseat(eid)
            if gone:
                self._venue_published()
                self.show_tab({})
            return len(gone)

        def _sync_exchange_tabs(self) -> None:
            """Seat a venue for each exchange the fleet names and drop the rest;
            the caption is ``exchange_display_name`` over the id, as Live
            captions an exchange saved with no name."""
            wanted = [str(eid) for eid in self._fleet_source.exchanges() if eid]
            for eid in wanted:
                self.add_exchange_tab(eid, exchange_display_name({"exchange_id": eid}))
            self._drop_unlisted_exchange_tabs(wanted)
            self._refresh_states()
            self.refresh_bots()
            self.refresh_votes()
            self.show_tab({})

        def run_action(self, payload: str) -> None:
            """Answer the corner and card way-ins, the Pause Console and Pause
            API Log presses, a venue sub-tab press, the panel's ``select_bot``,
            both bot tables' asks and the venue page's ``+ New Bot``, Privacy
            Mode and command bar; every other ask is held."""
            try:
                asked = json.loads(payload)
            except ValueError:
                logger.warning("The Paper page sent an ask that is not JSON")
                return
            method = str(asked.get("method") or "")
            params = asked.get("params")
            params = params if isinstance(params, dict) else {}
            if method == tab_surface.METHOD:
                wanted = params.get(tab_surface.ACTIVITY_PAUSED_PARAM)
                if wanted is not None:
                    self.set_activity_paused(bool(wanted))
                wanted = params.get(tab_surface.API_PAUSED_PARAM)
                if wanted is not None:
                    self.set_api_paused(bool(wanted))
                way_in = params.get(tab_surface.WAY_IN_PARAM)
                if way_in is not None:
                    self._way_in(str(way_in))
                shown = params.get(EXCHANGE_PARAM)
                if shown is not None:
                    self.show_tab({EXCHANGE_PARAM: str(shown)})
            elif method == LOG_METHOD:
                wanted = params.get(tab_surface.LOG_PAUSED_PARAM)
                if wanted is not None:
                    self.set_activity_paused(bool(wanted))
            elif (
                method == PANEL_METHOD
                and params.get("action") == tab_surface.SELECT_BOT_ACTION
            ):
                chosen = self._panel.select_bot(
                    str(params.get(tab_surface.BOT_ID_PARAM) or "")
                )
                self._feed_votes(chosen)
            elif method in (SCRUM_METHOD, EXTRACTOR_METHOD, venue_surface.METHOD):
                venue = self._venues.get(venue_of_ask(method, params))
                if venue is not None and venue.answer(method, params):
                    self._venue_published()

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
            self._web.setPage(PaperTradingPage(self))
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
                logger.warning("The React Paper tab page failed to load")
                return
            self._venue_published()
            waited = dict(self._waiting)
            self._waiting = {}
            if waited:
                self._web.page().runJavaScript(models_script(waited))
            elif self._votes:
                self._web.page().runJavaScript(votes_script(self._votes))
