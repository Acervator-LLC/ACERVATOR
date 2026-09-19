# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
"""The Sim tab drawn by React inside ``QWebEngineView``, forked from
``react_trading_tab``.

``SimTradingTabReact`` is ``TradingTabReact`` under the Simulator's name: it
draws ``src/gui/web/sim_trading_tab.js`` through the Electron shell's
``panel_host.js``, and ``sim_trading_tab.js`` mounts ``sim_indicator_panel.js``,
``sim_status_log.js`` and ``sim_exchange_tab.js`` into slots it keeps. The host
holds ``TabletSource`` and ``FleetSource`` as ``SimTradingTab`` does, and no
bot manager; ``add_exchange_tab`` seats one venue's own models, the fork of
``hold_venue``, ``_sync_exchange_tabs`` seats one per exchange
``FleetSource.exchanges`` names, at build and on every ``fleet_changed``, and
``refresh_bots`` hands each ``SimVenue`` its rows from ``FleetSource.statuses``
and ``refresh_votes`` hands the panel model the fleet, its own rates and the
selected bot's ``ivp_feed`` over ``TabletSource``, drawn through ``show_votes``;
every ``fleet_changed`` first writes the sim fleet file through
``FleetSource.save``. ``SimTradingPage`` reads the page's asks off the console line the host script
writes; ``run_action`` answers the flip, the Pause Console press through
``set_activity_paused``, the panel's ``select_bot``, both bot
tables' own asks and the venue page's ``+ New Bot`` and command bar, so a row's Fire reaches
``_on_bot_fire``, a row's Detail on either table reaches ``_on_bot_detail``,
which opens the Simulator's Bot Settings window through
``surface_class(SIM_BOT_DETAIL)`` over a ``SimBotView``, ``+ New Bot`` reaches
``_create_bot``, which opens ``SimBotWizardReactDialog`` and hands its config
to ``FleetSource.create``, and Start, Pause, Stop, Restart and Delete reach
``_on_bot_command``, the window's handler forked over ``SimBotManager`` with
no venue connect, which fires ``fleet_changed`` on every state move. The API
Interaction Log is written by ``_on_api_event``, the window's writer forked
over the host's own ``SimApiLog``, never the process-wide
``get_api_log``: each entry recorded on ``api_log()`` is pushed as one of
``api_lines`` through ``show_tab``, and ``SimTradingTabState`` draws it or
holds it while Pause API Log is down; that log accepts ``ALLOWED_ACTIONS``
only, the ``FETCH_TABLET`` entries ``_record_venue_call`` records and the
``FETCH_YTD`` entry ``_generate_from_ytd`` records, and raises ``SendRefused``
for any other action before anything is pushed; ``run_action`` answers the
page's Pause API Log press through ``set_api_paused``. The run mode is held once, on
``FleetSource.mode``, and names which of the source's three fleets the page
draws; a venue page's mode press or the card's reaches ``set_mode``, which
moves ``FleetSource.set_mode`` and fires ``fleet_changed``, so the venues
re-seat from that mode's fleet with the active sheet on their headers and the
tab redraws: the way-in row above each layer's exchange tab bar
offers Clear Fleet then that mode's two ways in then Start Run while a fleet
is held and nothing otherwise, the corner holding nothing, and the card the
three mode buttons and the mode's two, with Clear Fleet above them while a
fleet is held;
``show_tab`` reads ``held`` and ``mode`` off ``FleetSource`` on every call; a
row or card press reaches ``_way_in``, which runs ``_clear_fleet`` for
Clear Fleet, runs ``_start_run_pressed`` for Start Run, opens the wizard for
Create New Bots, runs
``_import_live_fleet`` for Import Live Fleet, runs
``_generate_from_ytd`` for Generate From YTD, and logs the ``SendRefused``
``FleetSource`` raises for every other action. ``_clear_fleet`` refuses with
the in-flight line while a run or a Battery is in flight, says so with no
record held, otherwise opens Live's Delete box shape naming the count and on
Yes drops every held record through ``FleetSource.clear`` and fires
``fleet_changed``, so every venue unseats, the card returns and the sim fleet
file is written empty; each press emits ``CLEAR_PRESSED_SIGNAL`` and a clear
emits ``CLEARED_SIGNAL`` through ``signal_contract``. ``_import_live_fleet`` puts
``exchange_choice`` over ``FleetSource.stored_exchanges``, opens
``SimExchangeChoiceDialog`` when it prompts, copies the chosen exchange's
records through ``FleetSource.import_live_fleet`` and fires ``fleet_changed``,
so the venue seats and its rows draw; ``_generate_from_ytd`` reads
``YtdTradeSource.root_state`` and writes one line for a directory that is
missing, empty or without a manifest, puts ``exchange_choice`` over the
exchanges the manifest names, opens the same chooser under Generate From
YTD's title, holds one record per traded pair through
``FleetSource.generate_from_ytd``, writes one line per manifest row whose
file is missing, the generation line and the no-target line, and fires
``fleet_changed``; ``_run_battery`` opens ``SimPortfolioChoiceDialog``, holds
the ``plan_run`` bots through ``FleetSource.hold_battery_fleet`` under Run
Portfolio and none under Run Every Portfolio, fires
``fleet_changed`` and runs ``_compute_battery`` on a daemon thread, whose
``battery_line``, ``battery_trade`` and ``battery_finished`` signals reach
``log``, ``log_trade`` and ``_take_battery`` on the GUI thread; the thread
walks one portfolio at a time, ``battery_portfolio_started`` reaching
``_battery_portfolio_started``, which holds that portfolio's bots through
``FleetSource.hold_battery_fleet`` and fires ``fleet_changed``, and
``battery_portfolio_finished`` reaching ``_battery_portfolio_finished``, which
writes the portfolio's report line and, under Run Every Portfolio, holds an
empty fleet and fires ``fleet_changed`` so every venue unseats before the
next; Stop on a Battery row reaches ``_stop_battery``, which sets the event
the walk reads before each tick; Start Run at
the corner reaches ``_start_run_pressed``, which refuses with the in-flight
line while a run or a Battery is in flight, runs ``_run_battery`` under Run
Portfolio's chooser in Portfolio Battery mode, and in Validation or Back Test
mode reaches ``_start_run`` over the venue on show, which moves every
scrumming bot on that exchange to ``running``
through ``SimBotManager.start``, fires ``fleet_changed``, writes the started
line and runs ``_compute_run`` on a daemon thread, ``validation.run`` or
``back_test.run`` over the tab's sources, each fill crossing on ``run_trade``
to ``log_trade`` and the outcome on ``run_finished`` to ``_take_run``, which
moves the run's bots to ``stopped`` and writes the run's lines and the report
line, and Stop on a run row reaches ``_stop_run``, which sets the event the
runner reads, each Start Run press emitting ``START_PRESSED_SIGNAL`` through
``signal_contract``; a venue sub-tab press reaches
``run_action`` as the ``exchange`` ask and ``show_tab`` makes that venue
current. A flip ask from either page module carries the pressed button's
rect under ``FLIP_RECT_PARAM``, and ``show_layer`` emits
``LAYER_FLIPPED_SIGNAL`` with it against the previous press's rect. The
replay layer behind the panel is pushed as the tab's ``replay``:
``_refresh_replay`` builds the chooser's items from ``tablet_choices`` and
``_feed_replay`` pushes ``replay_model`` over ``replay_feed`` through
``show_tab``, at build, on every ``fleet_changed``, on the flip, on the
chooser's ``tablet`` ask, on ``select_bot`` and after a retrieval; the
``retrieve_tablet`` ask reaches ``_retrieve_tablet``, which runs
``tablet_retrieval.retrieve`` on a daemon thread over the host's
``ReadOnlyConnector``, the one venue path, whose every call crosses on
``retrieval_call`` to ``_record_venue_call`` and the host's ``api_log``, and
whose end crosses on ``retrieval_finished`` to ``_take_retrieval``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any, Optional

from ...core.signal_contract import emit as _pin_emit
from ...core.signal_contract import get_sink as _pin_sink
from ...core.sound_engine import get_sound_engine
from ...simulator import back_test, portfolio_battery, tablet_retrieval, validation
from ...simulator.back_test import SimTrade
from ...simulator.fleet_source import (
    EXTRACTOR_MODE,
    SCRUMMING_MODE,
    FleetSource,
    SendRefused,
    SimBot,
    exchange_choice,
)
from ...simulator.gate_log_source import GateLogSource
from ...simulator.parity_report import ParityReport, report_line
from ...simulator.portfolios import PORTFOLIOS
from ...simulator.read_only_connector import ReadOnlyConnector, VenueCall
from ...simulator.sim_api_log import SimApiLog
from ...simulator.sim_bus import new_sim_bus, sim_log_manager
from ...simulator.sim_bot_manager import SimBotManager
from ...simulator.sim_bot_view import SimBotView
from ...simulator.tablet_source import TabletSource, tablet_key
from ...simulator.ytd_trade_source import ROOT_READY, YtdTradeSource
from ...trading.stone_tablets.storage import tablet_filename
from ..main_tabs import bot_status_table_surface as scrum_surface
from ..main_tabs import design_system_surface as token_surface
from ..main_tabs import extractor_bot_table_surface as extractor_surface
from ..main_tabs import indicator_panel_surface, status_log_surface
from ..main_tabs import simulator_tab_surface as sim
from ..main_tabs.main_window_surface import DASHBOARD_TICK_MS
from ..main_tabs.trading_tab_surface import (
    ALIAS_LAYER,
    EXCHANGE_PARAM,
    WATCHDOG_INTERVAL_MS,
    WATCHDOG_STAT_FAILURE_FORMAT,
    WatchdogState,
    exchange_display_name,
    layer_exchanges,
)
from ..react_history_panel import STYLE_SOURCE_ASSETS, page_html, read_asset
from ..react_main_window import read_renderer_asset
from ..react_trading_tab import settled_frames
from ..theme_engine import NIGREDO, NIGREDO_FRACTION, TONE_PROPERTY, toward_black
from ..variant_surface import SIM_BOT_DETAIL, SIM_BOT_WIZARD, surface_class
from . import sim_bot_status_table_surface as sim_scrum_surface
from . import sim_bot_wizard_surface as wizard_surface
from . import sim_exchange_tab_surface as venue_surface
from . import sim_trading_tab_surface as tab_surface
from .sim_indicator_panel import describe_no_data_cause, rate_fields
from .sim_status_log import SimStatusLogModel

try:
    from PySide6.QtCore import Qt, QTimer, Signal
    from PySide6.QtWebEngineCore import QWebEnginePage
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWidgets import QDialog, QMessageBox, QVBoxLayout, QWidget

    from .sim_exchange_choice import SimExchangeChoiceDialog, SimPortfolioChoiceDialog

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

#: The request fields that carry a press on the bot table.
TABLE_PRESS_PARAMS: tuple[str, ...] = (
    scrum_surface.FIRE_PARAM,
    scrum_surface.DETAIL_PARAM,
    scrum_surface.HEADER_CLICK_PARAM,
    scrum_surface.CELL_CLICK_PARAM,
)

#: The request fields that carry the venue page's ``+ New Bot`` press and its
#: command-bar press.
VENUE_PRESS_PARAMS: tuple[str, ...] = (
    venue_surface.live.NEW_BOT_PARAM,
    venue_surface.live.COMMAND_PARAM,
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

  // LOG appends its batch and keeps the whole held document in MODELS for
  // the page's own ask; TAB replaces the tab's model; the rest drop their cache.
  function holdModels(fresh) {
    Object.keys(fresh).forEach(function (method) {
      if (method === LOG) {
        var spool = global.acervatorSimLog;
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


#: One push per strip tick carries every trade line ``log_trade`` painted since the
#: last push, so a walk of thousands of fills does not push thousands of scripts.
TRADE_PUSH_INTERVAL_MS = DASHBOARD_TICK_MS


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


#: Every design token whose name, or whose alias target, starts with this is a
#: ground the page paints, and ``nigredo_design`` moves it toward black.
GROUND_NAME_PREFIX = "SURFACE_"


def nigredo_design(model: dict) -> dict:
    """``model`` from ``token_surface.view_model`` with every ground token in
    ``tokens`` and ``groups`` through ``toward_black`` at ``NIGREDO_FRACTION``;
    a token is a ground when its name or its ``alias_targets`` entry starts
    with ``GROUND_NAME_PREFIX``."""
    aliases = model.get("alias_targets", {})

    def is_ground(name: str) -> bool:
        return name.startswith(GROUND_NAME_PREFIX) or str(
            aliases.get(name, "")
        ).startswith(GROUND_NAME_PREFIX)

    tokens = {
        name: toward_black(value, NIGREDO_FRACTION) if is_ground(name) else value
        for name, value in model["tokens"].items()
    }
    groups = {
        group: {name: tokens.get(name, value) for name, value in members.items()}
        for group, members in model.get("groups", {}).items()
    }
    return {**model, "tokens": tokens, "groups": groups}


def models(
    state: tab_surface.SimTradingTabState,
    log: status_log_surface.StatusLogModel,
    panel: indicator_panel_surface.IndicatorPanelModel,
) -> dict:
    """The view model of every bridge method the page's modules ask for, the
    design tokens through ``nigredo_design``."""
    return {
        token_surface.METHOD: nigredo_design(token_surface.view_model({})),
        tab_surface.METHOD: state.view_model({}),
        LOG_METHOD: log_payload(log, {"whole": True}),
        PANEL_METHOD: panel_payload(panel),
    }


class SimVenue:
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
        self.scrum = sim_scrum_surface.SimBotStatusTableModel(
            on_bot_clicked=self._scrum_detail,
            on_fire_clicked=on_bot_fire,
        )
        self.scrum.exchange_id = exchange_id
        self.extractor = extractor_surface.ExtractorBotTableModel(
            on_bot_clicked=self._extractor_detail,
        )
        self.extractor.exchange_id = exchange_id

    def models(self, mode: str = sim.MODES[0]) -> dict:
        """The payload of each venue method, under the Simulator's names, the
        venue page's mode buttons drawn for the run mode ``mode``."""
        extractor = dict(extractor_surface.build_payload(self.extractor))
        extractor["method"] = EXTRACTOR_METHOD
        return {
            venue_surface.METHOD: venue_surface.build_view_model(self.screen, mode),
            SCRUM_METHOD: sim_scrum_surface.build_view_model(self.scrum),
            EXTRACTOR_METHOD: extractor,
        }

    def update_bots(self, statuses: list) -> None:
        """Route one fleet list to the screen and to both bot tables."""
        venue_surface.drive(self.screen, {venue_surface.live.STATUSES_PARAM: statuses})
        sim_scrum_surface.drive(
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
        ``+ New Bot`` or its command bar; a read ask carrying none of
        ``TABLE_PRESS_PARAMS``, ``EXTRACTOR_PRESS_ACTIONS`` or
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
        sim_scrum_surface.drive(self.scrum, params)
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
    ``for_exchange`` (``sim_scrum_surface.venue_of``)."""
    if method == venue_surface.METHOD:
        return str(params.get(venue_surface.live.EXCHANGE_ID_PARAM) or "")
    if method == EXTRACTOR_METHOD:
        return str(params.get(extractor_surface.EXCHANGE_ID_PARAM) or "")
    return sim_scrum_surface.venue_of(params)


def venue_models(venues: Any, mode: str = sim.MODES[0]) -> dict:
    """Each venue page's own payloads, keyed by the exchange it draws, each
    header drawn for the run mode ``mode``."""
    found: dict = {}
    for exchange_id, venue in dict(venues or {}).items():
        read = getattr(venue, "models", None)
        if not callable(read):
            continue
        held = read(mode)
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
    """The whole Sim page as one string, with no network fetch, its chrome in
    the ``NIGREDO`` tone.

    ``STYLE_ASSETS`` is inlined into the page head, so the tab's chrome
    reaches the browser without a stylesheet request.
    """
    return page_html(
        STYLE_ASSETS, (), page_body(), theme, (host_script(built, venues),), NIGREDO
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

        #: Fired by whatever loads a fleet; the venue sub-tabs re-seat on it.
        fleet_changed = Signal()
        #: One Activity Log line and its level from the Battery's worker thread.
        battery_line = Signal(str, str)
        #: One ``SimTrade`` the Battery's walk filled on the worker thread.
        battery_trade = Signal(object)
        #: The ``BatteryRun`` the Battery's worker thread finished with.
        battery_finished = Signal(object)
        #: One portfolio's name and its ``SimBot`` list, as the Battery's
        #: worker thread reaches it; the slot holds them as the fleet.
        battery_portfolio_started = Signal(str, object)
        #: One portfolio's name and its own ``BatteryRun``, its report
        #: written, as the worker thread leaves it; the slot writes the report
        #: line and clears.
        battery_portfolio_finished = Signal(str, object)
        #: One Activity Log line and its level from a Validation or Back Test
        #: run's worker thread.
        run_line = Signal(str, str)
        #: One ``SimTrade`` a Validation or Back Test run filled on its worker
        #: thread.
        run_trade = Signal(object)
        #: The ``ValidationRun`` or ``BackTestRun`` the worker thread finished
        #: with, or None when it raised.
        run_finished = Signal(object)
        #: One ``BotStatsSnapshot`` a walk emitted on the tab's bus under
        #: ``STATS_TOPIC``, re-emitted off the worker thread so the record is
        #: written on the GUI thread.
        bot_stats = Signal(object)
        #: One Activity Log line and its level from a retrieval's worker thread.
        retrieval_line = Signal(str, str)
        #: One ``VenueCall`` the read-only connector made on the worker thread.
        retrieval_call = Signal(object)
        #: The ``RetrievalOutcome`` a retrieval's worker thread finished with.
        retrieval_finished = Signal(object)

        def __init__(
            self,
            tablet_source: Optional[TabletSource] = None,
            fleet_source: Optional[FleetSource] = None,
            parent: Optional[QWidget] = None,
            theme: object = None,
            api_log: Optional[SimApiLog] = None,
            battery_tablet_source: Optional[TabletSource] = None,
            connector: Optional[ReadOnlyConnector] = None,
        ) -> None:
            """Hold the two sources the tab's view models are built from, the
            RA-StoneTablet source the Battery runs over, the API log
            ``_on_api_event`` listens to and the read-only connector a
            retrieval reads through."""
            super().__init__(parent)
            self.setObjectName(ACCESSIBLE_NAME)
            self.setAccessibleName(ACCESSIBLE_NAME)
            # The theme's nigredo_qss paints the Qt windows this host parents.
            self.setProperty(TONE_PROPERTY, NIGREDO)
            self.setAttribute(Qt.WA_StyledBackground, True)
            self._tablet_source = (
                tablet_source
                if tablet_source is not None
                else TabletSource(sim.TABLET_ROOT)
            )
            self._battery_tablet_source = (
                battery_tablet_source
                if battery_tablet_source is not None
                else TabletSource(sim.BATTERY_TABLET_ROOT)
            )
            self._battery_thread: Optional[threading.Thread] = None
            self._battery_stop = threading.Event()
            self._battery: dict = {}
            self._run_thread: Optional[threading.Thread] = None
            self._run_stop = threading.Event()
            self._run: dict = {}
            self._fleet_source = (
                fleet_source if fleet_source is not None else FleetSource()
            )
            self._api_log = api_log if api_log is not None else SimApiLog()
            self._connector = (
                connector
                if connector is not None
                else ReadOnlyConnector(on_call=self._on_venue_call)
            )
            # The Simulator's own bus, not the process-wide one; every run emits on it.
            self._bus = new_sim_bus()
            self._log_manager = sim_log_manager(self._bus, self._symbol_of)
            self._retrieval_thread: Optional[threading.Thread] = None
            self._retrieval: dict = {}
            self._tablet_key: str = ""
            self._replay: dict = {}
            self._choices: list = []
            self._fills: list[SimTrade] = []
            self._battery_outcome: Any = None
            self._bot_manager = SimBotManager(self._fleet_source)
            self._theme = theme
            self._state = tab_surface.SimTradingTabState()
            self._log = SimStatusLogModel()
            self._panel = indicator_panel_surface.IndicatorPanelModel()
            self._models: dict = {}
            self._votes: dict = {}
            self._venues: dict = {}
            self._venue_models: dict = {}
            self._waiting: dict = {}
            self._page_ready = False
            self._web: Any = None
            # The rect the last flip press carried, in the layer stack's coordinates.
            self._last_flip_rect: Optional[dict] = None
            self._layout = QVBoxLayout(self)
            self._layout.setContentsMargins(0, 0, 0, 0)
            self._layout.setSpacing(0)
            self.fleet_changed.connect(self._fleet_source.save)
            self.fleet_changed.connect(self._sync_exchange_tabs)
            self.battery_line.connect(self.log)
            self.battery_trade.connect(self.log_trade)
            self.battery_finished.connect(self._take_battery)
            self.battery_portfolio_started.connect(self._battery_portfolio_started)
            self.battery_portfolio_finished.connect(self._battery_portfolio_finished)
            self.run_line.connect(self.log)
            self.run_trade.connect(self.log_trade)
            self.run_finished.connect(self._take_run)
            self.bot_stats.connect(self._take_bot_stats)
            self._bus.subscribe(back_test.STATS_TOPIC, self._on_bus_stats)
            self._stats_dirty = False
            self._stats_redraw_timer = QTimer(self)
            self._stats_redraw_timer.setSingleShot(True)
            self._stats_redraw_timer.setInterval(tab_surface.STATS_REDRAW_MS)
            self._stats_redraw_timer.timeout.connect(self._redraw_stats)
            self.retrieval_line.connect(self.log)
            self.retrieval_call.connect(self._record_venue_call)
            self.retrieval_finished.connect(self._take_retrieval)
            self._sync_exchange_tabs()
            self._api_log.add_listener(self._on_api_event)
            # Polls StatusLogModel.health_stats() every 60s on the GUI thread.
            self._activity_log_watchdog_state = WatchdogState()
            self._activity_log_watchdog_timer = QTimer(self)
            self._activity_log_watchdog_timer.timeout.connect(
                self._activity_log_watchdog
            )
            self._activity_log_watchdog_timer.start(WATCHDOG_INTERVAL_MS)
            self._trade_push_timer = QTimer(self)
            self._trade_push_timer.setSingleShot(True)
            self._trade_push_timer.setInterval(TRADE_PUSH_INTERVAL_MS)
            self._trade_push_timer.timeout.connect(self._push_pending_log)

        # -- what the window reads ----------------------------------------

        @property
        def page_ready(self) -> bool:
            """True once ``_on_load_finished`` has seen a successful load."""
            return self._page_ready

        def panel_view(self):
            """The web view the tab draws in, or None before the first show."""
            return self._web

        def connector(self) -> ReadOnlyConnector:
            """The read-only connector a retrieval reads candles through."""
            return self._connector

        def retrieval_running(self) -> bool:
            """True while a retrieval worker thread is alive."""
            thread = self._retrieval_thread
            return thread is not None and thread.is_alive()

        def tablet_key(self) -> str:
            """The chooser's chosen key, the item the two windows draw."""
            return self._tablet_key

        def replay(self) -> dict:
            """The ``replay_feed`` the two windows last drew."""
            return dict(self._replay)

        def fills(self) -> list[SimTrade]:
            """Every ``SimTrade`` the run in flight or last finished handed
            ``log_trade``, in fill order; empty before the first run."""
            return list(self._fills)

        def battery_outcome(self) -> Any:
            """The ``BatteryRun`` the last Battery finished with, or None."""
            return self._battery_outcome

        def replay_source(self) -> TabletSource:
            """The tablet reader the replay layer lists and draws from:
            ``battery_tablet_source`` under ``MODE_PORTFOLIO_BATTERY``,
            ``tablet_source`` otherwise."""
            if self.mode() == sim.MODE_PORTFOLIO_BATTERY:
                return self._battery_tablet_source
            return self._tablet_source

        def models(self) -> dict:
            """A copy of the models the page was built from, empty before that."""
            return dict(self._models)

        def venue_payloads(self) -> dict:
            """A copy of the payload each venue last published."""
            return dict(self._venue_models)

        def bus(self) -> Any:
            """The tab's private bus from ``new_sim_bus``; every run's rows
            are emitted on it."""
            return self._bus

        def log_manager(self) -> Any:
            """Live's ``LogManager`` over the sim bucket from
            ``sim_log_manager``, attached to ``bus``."""
            return self._log_manager

        def _symbol_of(self, bot_id: str) -> str:
            """The symbol ``FleetSource.bot_for`` holds for ``bot_id``, or empty."""
            bot = self._fleet_source.bot_for(bot_id)
            return bot.symbol if bot is not None else ""

        def tablet_source(self) -> TabletSource:
            """The tablet reader the panel is fed from."""
            return self._tablet_source

        def battery_tablet_source(self) -> TabletSource:
            """The RA-StoneTablet reader the Portfolio Battery runs over."""
            return self._battery_tablet_source

        def battery_running(self) -> bool:
            """True while a Battery worker thread is alive."""
            thread = self._battery_thread
            return thread is not None and thread.is_alive()

        def run_running(self) -> bool:
            """True while a Validation or Back Test worker thread is alive."""
            thread = self._run_thread
            return thread is not None and thread.is_alive()

        def run_state(self) -> dict:
            """The run in flight or last finished: ``mode``, ``exchange_id``,
            ``bot_ids`` and ``stopper``, the bot Stop was pressed on."""
            return dict(self._run)

        def fleet_source(self) -> FleetSource:
            """The fleet reader the tables are fed from."""
            return self._fleet_source

        def aggregate(self) -> dict:
            """The header strip's figures, ``fleet_aggregate`` over the held
            fleet in the tab's ``mode``."""
            return sim.fleet_aggregate(self._fleet_source, self.mode())

        def api_log(self) -> SimApiLog:
            """The tab's own API log; every entry it accepts reaches the pane,
            and it accepts ``ALLOWED_ACTIONS`` only."""
            return self._api_log

        def exchange_count(self) -> int:
            """How many venue sub-tabs the alias layer holds; EXCH reads it.

            The alias layer is the one ``len(self._exchange_tabs)`` counts on
            Live and on the Qt fork.
            """
            return len(layer_exchanges(self._state.exchanges)[ALIAS_LAYER])

        def mode(self) -> str:
            """The run mode in force, one of ``MODES``, ``FleetSource.mode``."""
            return self._fleet_source.mode()

        def set_mode(self, mode: str) -> str:
            """Make ``mode`` the run mode through ``FleetSource.set_mode``, so
            its fleet is the one the page's tables, the strip, the venue
            stack and the way-in row draw, then ``fleet_changed``, which
            re-seats the venues with the active sheet and redraws the card's
            mode row. A name outside ``MODES`` changes nothing; a press while
            ``battery_running`` or ``run_running`` writes the in-flight line
            and changes nothing. Each press emits ``MODE_SHOWN_SIGNAL`` with
            its outcome; answers the mode in force."""
            left = self.mode()
            expected = tab_surface.mode_shown_expected(
                mode, self._fleet_source.held_by_mode()
            )

            def shown(outcome: str) -> None:
                _pin_emit(
                    tab_surface.MODE_SHOWN_SIGNAL,
                    actual={
                        "mode": self.mode(),
                        "held": len(self._fleet_source.bots()),
                        "venues": list(self._fleet_source.exchanges()),
                    },
                    expected=expected,
                    context={
                        "outcome": outcome,
                        "from": left,
                        "held_by_mode": self._fleet_source.held_by_mode(),
                    },
                )
                sink = _pin_sink()
                if sink is not None:
                    sink.flush()

            if mode not in sim.MODES:
                shown(tab_surface.MODE_OUTCOME_UNKNOWN)
                return self.mode()
            if self.battery_running():
                self.log(tab_surface.BATTERY_RUNNING_TEXT, "warning")
                shown(tab_surface.MODE_OUTCOME_IN_FLIGHT)
                return self.mode()
            if self.run_running():
                self.log(
                    tab_surface.run_in_flight_line(
                        self._run.get("mode", ""),
                        len(self._run.get("bot_ids", [])),
                        sim.MODE_TEXT.get(mode, mode),
                    ),
                    "warning",
                )
                shown(tab_surface.MODE_OUTCOME_IN_FLIGHT)
                return self.mode()
            self._fleet_source.set_mode(mode)
            self._state.set_mode(self.mode())
            self.fleet_changed.emit()
            self.log(
                tab_surface.mode_shown_line(
                    mode, len(self._fleet_source.bots()), self._fleet_source.exchanges()
                ),
                "info",
            )
            shown(tab_surface.MODE_OUTCOME_SHOWN)
            return self.mode()

        def _current_venue_id(self) -> str:
            """The exchange of the venue on show, or ``""`` with none seated."""
            return str(self._state.current_exchange or next(iter(self._venues), ""))

        def _way_in(self, action: str) -> None:
            """One button pressed on the way-in row or on the card: Clear Fleet
            runs ``_clear_fleet``, Start Run runs ``_start_run_pressed``,
            Create New Bots opens the wizard through ``_create_bot``, Import
            Live Fleet runs ``_import_live_fleet``, Generate From YTD runs
            ``_generate_from_ytd``, Run Portfolio and Run Every Portfolio run
            ``_run_battery``; every other action asks ``FleetSource`` for it
            by name, which raises ``SendRefused``, and the refusal is logged
            to the Activity Log."""
            if action == sim.CLEAR_FLEET_ACTION:
                self._clear_fleet()
                return
            if action == sim.START_RUN_ACTION:
                self._start_run_pressed()
                return
            if action == sim.CREATE_NEW_BOTS_ACTION:
                self._create_bot(self._current_venue_id())
                return
            if action == sim.IMPORT_LIVE_FLEET_ACTION:
                self._import_live_fleet()
                return
            if action == sim.GENERATE_FROM_YTD_ACTION:
                self._generate_from_ytd()
                return
            if action in (sim.RUN_PORTFOLIO_ACTION, sim.RUN_EVERY_PORTFOLIO_ACTION):
                self._run_battery(action)
                return
            try:
                getattr(self._fleet_source, action)
            except SendRefused as exc:
                self.log(tab_surface.way_in_refused_line(action, exc), "error")

        def _clear_fleet(self) -> None:
            """Clear Fleet: the in-flight line and nothing removed while
            ``battery_running`` or ``run_running``; the nothing-held line with
            no record held; otherwise Live's Delete box shape under
            ``CLEAR_FLEET_BOX_TITLE`` naming the run mode and the count, and
            on Yes ``FleetSource.clear`` on that mode's fleet, the cleared
            line, the notification, the sound and ``fleet_changed``, so every
            venue unseats, the card returns and the sim fleet file is written
            with that fleet empty and the other two kept; each press emits
            ``CLEAR_PRESSED_SIGNAL`` with its outcome and a clear emits
            ``CLEARED_SIGNAL`` with what left."""
            held = self._fleet_source.bots()
            venues = self._fleet_source.exchanges()
            context = {"held": len(held), "venues": list(venues), "mode": self.mode()}

            def pressed(outcome: str) -> None:
                kept = 0 if outcome == tab_surface.CLEAR_OUTCOME_CLEARED else len(held)
                _pin_emit(
                    tab_surface.CLEAR_PRESSED_SIGNAL,
                    actual={
                        "outcome": outcome,
                        "held_after": len(self._fleet_source.bots()),
                    },
                    expected={"outcome": outcome, "held_after": kept},
                    context=context,
                )
                sink = _pin_sink()
                if sink is not None:
                    sink.flush()

            if self.battery_running():
                self.log(tab_surface.BATTERY_RUNNING_TEXT, "warning")
                pressed(tab_surface.CLEAR_OUTCOME_IN_FLIGHT)
                return
            if self.run_running():
                self.log(
                    tab_surface.run_in_flight_line(
                        self._run.get("mode", ""),
                        len(self._run.get("bot_ids", [])),
                        sim.CLEAR_FLEET_TEXT,
                    ),
                    "warning",
                )
                pressed(tab_surface.CLEAR_OUTCOME_IN_FLIGHT)
                return
            if not held:
                self.log(tab_surface.NOTHING_HELD_TEXT, "warning")
                pressed(tab_surface.CLEAR_OUTCOME_NOTHING_HELD)
                return
            confirm = QMessageBox.question(
                self,
                tab_surface.CLEAR_FLEET_BOX_TITLE,
                tab_surface.clear_fleet_question(len(held), venues, self.mode()),
                QMessageBox.Yes | QMessageBox.No,
            )
            if confirm != QMessageBox.Yes:
                self.log(tab_surface.CLEAR_CANCELLED_TEXT, "warning")
                pressed(tab_surface.CLEAR_OUTCOME_CANCELLED)
                return
            removed = self._fleet_source.clear()
            self.log(tab_surface.cleared_line(removed, venues, self.mode()), "warning")
            self._notify(tab_surface.FLEET_CLEARED_NOTICE, "warning")
            get_sound_engine().play_state_change()
            self.fleet_changed.emit()
            pressed(tab_surface.CLEAR_OUTCOME_CLEARED)
            _pin_emit(
                tab_surface.CLEARED_SIGNAL,
                actual={
                    "held_after": len(self._fleet_source.bots()),
                    "venues_after": self.exchange_count(),
                },
                expected={"held_after": 0, "venues_after": 0},
                context={
                    "removed": removed,
                    "venues_unseated": list(venues),
                    "mode": self.mode(),
                },
            )
            sink = _pin_sink()
            if sink is not None:
                sink.flush()

        def _run_battery(self, action: str) -> str:
            """Run Portfolio or Run Every Portfolio: one line and nothing
            started while ``battery_running``; ``SimPortfolioChoiceDialog``
            over ``PORTFOLIOS`` and ``BATTERY_SPANS``, the portfolio row left
            out for ``RUN_EVERY_PORTFOLIO_ACTION``; then ``plan_run`` over the
            held fleet, ``FleetSource.hold_battery_fleet`` on the plan's bots
            under Run Portfolio and on nothing under Run Every Portfolio,
            whose fleets ``_battery_portfolio_started`` holds one at a time,
            ``fleet_changed``, the started line, and ``_compute_battery`` on a
            daemon thread; a cancelled chooser writes one line and moves
            nothing. Answers the outcome: ``START_OUTCOME_IN_FLIGHT``,
            ``START_OUTCOME_CANCELLED`` or ``START_OUTCOME_STARTED``."""
            if self.battery_running():
                self.log(tab_surface.BATTERY_RUNNING_TEXT, "warning")
                return tab_surface.START_OUTCOME_IN_FLIGHT
            every = action == sim.RUN_EVERY_PORTFOLIO_ACTION
            dialog = SimPortfolioChoiceDialog(
                PORTFOLIOS, sim.BATTERY_SPANS, self, every=every
            )
            if dialog.exec() != QDialog.Accepted:
                self.log(tab_surface.BATTERY_CANCELLED_TEXT, "warning")
                return tab_surface.START_OUTCOME_CANCELLED
            names = () if every else (dialog.chosen_portfolio(),)
            span = dialog.chosen_span() or sim.DEFAULT_SPAN
            plan = portfolio_battery.plan_run(
                names, self._battery_tablet_source, self._fleet_source.bots()
            )
            self._begin_fills()
            # Run Every Portfolio loads each portfolio's fleet in turn through
            # _battery_portfolio_started, so the press itself holds none.
            self._fleet_source.hold_battery_fleet(() if every else plan.bots)
            self.fleet_changed.emit()
            subject = tab_surface.EVERY_PORTFOLIO_SUBJECT if every else names[0]
            self.log(
                tab_surface.battery_started_line(
                    subject, span, len(plan.bots), plan.plan_origins, plan.budget_usd
                ),
                "success",
            )
            self._battery_thread = threading.Thread(
                target=self._compute_battery,
                args=(plan, span),
                name="sim-portfolio-battery",
                daemon=True,
            )
            self._battery_thread.start()
            return tab_surface.START_OUTCOME_STARTED

        def _compute_battery(self, plan, span: str) -> None:
            """Run ``portfolio_battery.run_battery`` over
            ``battery_tablet_source`` on ``plan``, its retrieval through the
            tab's own ``connector`` so each venue call reaches
            ``_record_venue_call``, one portfolio at a time through
            ``battery_portfolio_started`` and ``battery_portfolio_finished``,
            ``stop`` the event ``_stop_battery`` sets, and hand the
            ``BatteryRun`` to the GUI thread through ``battery_finished``, each
            walk's and each portfolio's line through ``battery_line`` and each
            ``SimTrade`` through ``battery_trade``; a run that raises writes
            one failed line instead."""
            self._battery_stop.clear()
            self._battery = {
                "bot_ids": [bot.bot_id for bot in plan.bots],
                "every": len(plan.names) > 1,
                "stopper": "",
            }
            try:
                outcome = portfolio_battery.run_battery(
                    self._battery_tablet_source,
                    names=plan.names,
                    span=span,
                    plan=plan,
                    progress=lambda line: self.battery_line.emit(line, "info"),
                    on_trade=self.battery_trade.emit,
                    bus=self._bus,
                    connector=self._connector,
                    stop=self._battery_stop.is_set,
                    on_portfolio_started=self.battery_portfolio_started.emit,
                    on_portfolio_finished=self.battery_portfolio_finished.emit,
                )
            except Exception as exc:  # noqa: BLE001 - the run runs off-thread
                logger.exception("Portfolio Battery failed: %s", exc)
                self.battery_line.emit(tab_surface.battery_failed_line(exc), "error")
                return
            self.battery_finished.emit(outcome)

        def _battery_portfolio_started(self, name: str, bots) -> None:
            """Empty the held fills through ``_begin_fills`` so the replay
            layer marks this portfolio's alone, hold ``bots``, one
            portfolio's, as the fleet through ``FleetSource.hold_battery_fleet``,
            fire ``fleet_changed`` so the venues seat and the page's rows and
            the strip draw them, and write ``battery_loaded_line`` with their
            budget."""
            self._begin_fills()
            self._fleet_source.hold_battery_fleet(list(bots))
            self.fleet_changed.emit()
            self.log(
                tab_surface.battery_loaded_line(
                    name, bots, back_test.run_budget_usd(list(bots))
                ),
                "info",
            )

        def _battery_portfolio_finished(self, name: str, run) -> None:
            """Write ``run``'s report line through ``log_report``; when the
            press names more than one portfolio, hold an empty fleet through
            ``FleetSource.hold_battery_fleet``, fire ``fleet_changed`` so
            every venue unseats, and write ``battery_cleared_line``."""
            if run.report is not None:
                self.log_report(run.report)
            if not self._battery.get("every"):
                return
            self._fleet_source.hold_battery_fleet(())
            self.fleet_changed.emit()
            self.log(tab_surface.battery_cleared_line(name), "info")

        def _stop_battery(self, bot_id: str) -> None:
            """Stop on ``bot_id``, a row of the Battery in flight: Live's
            stopping line, ``battery_stopping_line``, and the event the walk
            reads before each tick."""
            self.log(f"Stopping bot {bot_id}...", "info")
            self._battery["stopper"] = bot_id
            self.log(tab_surface.battery_stopping_line(bot_id), "warning")
            self._battery_stop.set()

        def _take_battery(self, outcome) -> None:
            """Write Live's stopped line for the bot Stop was pressed on, the
            finished run's ``lines`` and, when a summary was written, its report
            line through ``log_report`` on the GUI thread; hold ``outcome`` for the
            replay layer's improvement figure and redraw the layer on the run's
            last bot through ``_refresh_replay``."""
            stopper = self._battery.get("stopper")
            if stopper:
                self.log(f"Bot {stopper} stopped.", "info")
                self._notify(f"Bot {stopper} STOPPED", "info")
                get_sound_engine().play_state_change()
            self._battery_outcome = outcome
            for line in outcome.lines:
                self.log(line, "info")
            if outcome.report is not None:
                self.log_report(outcome.report)
            self._refresh_replay(follow_run=True)

        def _generate_from_ytd(self) -> None:
            """Generate From YTD: one line and nothing held unless
            ``YtdTradeSource.root_state`` is ``ROOT_READY`` and the manifest
            names a pair; ``exchange_choice`` over the exchanges it names,
            ``SimExchangeChoiceDialog`` under ``GENERATE_FROM_YTD_TEXT`` when it
            prompts, then ``FleetSource.generate_from_ytd`` on the exchange
            chosen, one ``ytd_api_entry`` recorded on ``api_log`` for that
            read, one line per manifest row whose file is missing, the
            generation line, the no-target line and ``fleet_changed``; a
            cancelled chooser writes one line and moves nothing."""
            source = YtdTradeSource()
            state = source.root_state()
            if state != ROOT_READY:
                self.log(tab_surface.ytd_root_line(state, source.root()), "warning")
                return
            options = sorted({entry.exchange_id for entry in source.entries()})
            if not options:
                self.log(tab_surface.ytd_no_pair_line(source.root()), "warning")
                return
            choice = exchange_choice(options)
            chosen = choice["chosen"]
            if choice["prompt"]:
                dialog = SimExchangeChoiceDialog(
                    options, self, title=sim.GENERATE_FROM_YTD_TEXT
                )
                if dialog.exec() != QDialog.Accepted:
                    self.log(tab_surface.GENERATE_CANCELLED_TEXT, "warning")
                    return
                chosen = dialog.chosen()
            started = time.perf_counter()
            made = self._fleet_source.generate_from_ytd(source, chosen)
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            self._api_log.record(
                **tab_surface.ytd_api_entry(made, chosen, source.root(), elapsed_ms)
            )
            for entry in made.missing:
                self.log(tab_surface.ytd_file_missing_line(entry), "warning")
            if not made.bots:
                return
            self.log(
                tab_surface.generated_line(len(made.bots), made.files_read, chosen),
                "success",
            )
            without_target = sum(1 for bot in made.bots if bot.target_usd is None)
            if without_target:
                self.log(tab_surface.no_target_line(without_target), "warning")
            self.fleet_changed.emit()

        def _import_live_fleet(self) -> None:
            """Import Live Fleet: ``exchange_choice`` over the exchanges
            ``FleetSource.stored_exchanges`` names, ``SimExchangeChoiceDialog``
            when it prompts, then ``FleetSource.import_live_fleet`` on the
            exchange chosen, one Activity Log line and ``fleet_changed``; a file
            naming no bot and a cancelled chooser each write one line and move
            nothing."""
            options = self._fleet_source.stored_exchanges()
            if not options:
                self.log(tab_surface.no_stored_bot_line(), "warning")
                return
            choice = exchange_choice(options)
            chosen = choice["chosen"]
            if choice["prompt"]:
                dialog = SimExchangeChoiceDialog(options, self)
                if dialog.exec() != QDialog.Accepted:
                    self.log(tab_surface.IMPORT_CANCELLED_TEXT, "warning")
                    return
                chosen = dialog.chosen()
            imported = self._fleet_source.import_live_fleet(chosen)
            self.log(tab_surface.imported_line(len(imported), chosen), "success")
            self.fleet_changed.emit()

        def log_report(self, report: ParityReport) -> None:
            """One Activity Log line, ``report_line`` over ``report``, through
            ``log`` at the ``success`` level ``_import_live_fleet`` uses."""
            self.log(report_line(report), "success")

        # -- the Validation and Back Test runs ----------------------------

        def _run_bots(self, exchange_id: str) -> list[SimBot]:
            """Every held scrumming bot on ``exchange_id``, the fleet a run
            covers."""
            return [
                one
                for one in self._fleet_source.bots()
                if one.exchange_id == exchange_id and one.mode == SCRUMMING_MODE
            ]

        def _start_run_pressed(self) -> None:
            """Start Run on the way-in row: the in-flight line and nothing started
            while ``battery_running`` or ``run_running``; otherwise the run
            the tab's ``mode`` names over the venue on show, ``_start_run``
            for Validation and Back Test, ``_run_battery`` under Run
            Portfolio's chooser for Portfolio Battery; each press emits
            ``START_PRESSED_SIGNAL`` with its outcome and the venue's
            scrumming rows reading ``running`` after it, every run bot under
            a started Validation and the count before the press otherwise, a
            Back Test row moving when its own walk starts."""
            venue = self._current_venue_id()
            mode = self.mode()
            run_bots = self._run_bots(venue)
            running_before = tab_surface.rows_running(run_bots)
            context = {
                "mode": mode,
                "venue": venue,
                "held": len(self._fleet_source.bots()),
                "bots": len(run_bots),
            }
            if self.battery_running():
                self.log(tab_surface.BATTERY_RUNNING_TEXT, "warning")
                outcome = tab_surface.START_OUTCOME_IN_FLIGHT
            elif self.run_running():
                self.log(
                    tab_surface.run_in_flight_line(
                        self._run.get("mode", ""),
                        len(self._run.get("bot_ids", [])),
                        sim.START_RUN_TEXT,
                    ),
                    "warning",
                )
                outcome = tab_surface.START_OUTCOME_IN_FLIGHT
            elif mode in tab_surface.RUN_MODES:
                outcome = self._start_run(venue, mode)
            else:
                outcome = self._run_battery(sim.RUN_PORTFOLIO_ACTION)
            expected_running = running_before
            if (
                outcome == tab_surface.START_OUTCOME_STARTED
                and mode == sim.MODE_VALIDATION
            ):
                expected_running = len(run_bots)
            running_after = tab_surface.rows_running(self._run_bots(venue))
            _pin_emit(
                tab_surface.START_PRESSED_SIGNAL,
                actual={"outcome": outcome, "rows_running": running_after},
                expected={"outcome": outcome, "rows_running": expected_running},
                context=context,
            )
            sink = _pin_sink()
            if sink is not None:
                sink.flush()

        def _start_run(self, exchange_id: str, mode: str) -> str:
            """Start the run ``mode`` names over ``_run_bots`` of
            ``exchange_id``: under Validation each bot to ``running`` through
            ``SimBotManager.start`` and ``fleet_changed`` at the press, the
            rerun being one pass over the fleet; under Back Test nothing
            moves at the press, each row reading ``running`` when its own
            walk's opening snapshot reaches ``_take_bot_stats``; then the YTD
            root line when Validation's YTD directory is not ready, the
            started line and ``_compute_run`` on a daemon thread; a venue
            holding no scrumming bot writes one line and starts nothing.
            Answers ``START_OUTCOME_NO_BOT`` or ``START_OUTCOME_STARTED``."""
            bots = self._run_bots(exchange_id)
            if not bots:
                self.log(tab_surface.run_no_bot_line(mode, exchange_id), "warning")
                return tab_surface.START_OUTCOME_NO_BOT
            self._run_stop.clear()
            self._run = {
                "mode": mode,
                "exchange_id": exchange_id,
                "bot_ids": [one.bot_id for one in bots],
                "stopper": "",
            }
            self._begin_fills()
            if mode == sim.MODE_VALIDATION:
                for one in bots:
                    self._bot_manager.start(one.bot_id)
                self.fleet_changed.emit()
            if mode == sim.MODE_VALIDATION:
                source = YtdTradeSource()
                state = source.root_state()
                if state != ROOT_READY:
                    self.log(tab_surface.ytd_root_line(state, source.root()), "warning")
            self.log(
                tab_surface.run_started_line(
                    mode, exchange_id, len(bots), back_test.run_budget_usd(bots)
                ),
                "success",
            )
            self._run_thread = threading.Thread(
                target=self._compute_run,
                args=(mode, bots, exchange_id),
                name=tab_surface.RUN_THREAD_NAME,
                daemon=True,
            )
            self._run_thread.start()
            return tab_surface.START_OUTCOME_STARTED

        def _compute_run(self, mode: str, bots: list, exchange_id: str) -> None:
            """Run ``validation.run`` or ``back_test.run`` over ``bots`` and
            the tab's sources on the worker thread, each fill through
            ``run_trade`` and the outcome through ``run_finished``; a run that
            raises writes the failed line and hands None to ``run_finished``."""
            try:
                if mode == sim.MODE_VALIDATION:
                    outcome = validation.run(
                        bots,
                        self._tablet_source,
                        YtdTradeSource(),
                        GateLogSource(),
                        exchange_id=exchange_id,
                        limit=sim.VALIDATION_RERUN_LIMIT,
                        on_trade=self.run_trade.emit,
                        stop=self._run_stop.is_set,
                        bus=self._bus,
                    )
                else:
                    outcome = back_test.run(
                        bots,
                        self._tablet_source,
                        exchange_id=exchange_id,
                        ticks_per_bot=sim.BACK_TEST_TICKS_PER_BOT,
                        funding=sim.funding_for(mode),
                        on_trade=self.run_trade.emit,
                        stop=self._run_stop.is_set,
                        bus=self._bus,
                    )
            except Exception as exc:
                logger.exception("%s run failed: %s", mode, exc)
                self.run_line.emit(tab_surface.run_failed_line(mode, exc), "error")
                self.run_finished.emit(None)
                return
            self.run_finished.emit(outcome)

        def _stop_run(self, bot_id: str) -> None:
            """Stop on ``bot_id``, a row of the run in flight: Live's stopping
            line, the run's stopping line, and the event the runner reads."""
            self.log(f"Stopping bot {bot_id}...", "info")
            self._run["stopper"] = bot_id
            self.log(
                tab_surface.run_stopping_line(self._run.get("mode", ""), bot_id),
                "warning",
            )
            self._run_stop.set()

        def _take_run(self, outcome) -> None:
            """Move every run bot to ``stopped`` through ``SimBotManager.stop``
            and fire ``fleet_changed``; write Live's stopped line for the bot
            Stop was pressed on, the finished run's ``lines`` and its report
            line through ``log_report`` on the GUI thread."""
            for bot_id in self._run.get("bot_ids", []):
                try:
                    self._bot_manager.stop(bot_id)
                except KeyError:
                    continue
            self.fleet_changed.emit()
            stopper = self._run.get("stopper")
            if stopper:
                self.log(f"Bot {stopper} stopped.", "info")
                self._notify(f"Bot {stopper} STOPPED", "info")
                get_sound_engine().play_state_change()
            if outcome is None:
                self._refresh_replay(follow_run=True)
                return
            for line in outcome.lines:
                self.log(line, "info")
            if outcome.report is not None:
                self.log_report(outcome.report)
            self._refresh_replay(follow_run=True)

        def _begin_fills(self) -> None:
            """Empty ``_fills`` and drop ``_battery_outcome`` as a run starts,
            so the replay layer marks that run alone."""
            self._fills = []
            self._battery_outcome = None

        def log_trade(self, trade: SimTrade) -> None:
            """One Activity Log line per ``SimTrade``: ``trade_line`` under
            ``trade_stamp`` through ``SimStatusLogModel.log_at`` at
            ``TRADE_LINE_LEVEL``, pushed by ``_push_pending_log`` one
            ``TRADE_PUSH_INTERVAL_MS`` later, and the trade appended to
            ``_fills`` for the replay layer's marks."""
            self._fills.append(trade)
            self._log.log_at(
                tab_surface.trade_stamp(trade),
                tab_surface.trade_line(trade),
                tab_surface.TRADE_LINE_LEVEL,
            )
            if not self._trade_push_timer.isActive():
                self._trade_push_timer.start()

        # -- the walk's stats on the record ---------------------------------

        def _on_bus_stats(self, event: Any) -> None:
            """The bus subscriber for ``STATS_TOPIC``, called on the walk's
            thread: re-emit the event's ``snapshot`` through ``bot_stats`` so
            ``_take_bot_stats`` runs on the GUI thread."""
            snapshot = (getattr(event, "data", None) or {}).get("snapshot")
            if snapshot is not None:
                self.bot_stats.emit(snapshot)

        def _take_bot_stats(self, snapshot: Any) -> None:
            """Write one ``BotStatsSnapshot`` into the held record through
            ``FleetSource.write_stats`` on the GUI thread; a ``running`` mark
            moves the bot through ``SimBotManager.start`` with Live's
            ``✓ Bot <id> RUNNING.`` line and pushes the rows at once, a
            ``stopped`` mark moves it through ``SimBotManager.stop`` with the
            walk's ended line, and every other snapshot arms
            ``_stats_redraw_timer`` so the rows push once per
            ``STATS_REDRAW_MS``. A snapshot for a record no longer held is
            dropped."""
            bot_id = str(getattr(snapshot, "bot_id", ""))
            try:
                self._fleet_source.write_stats(
                    bot_id, snapshot.stats, snapshot.scrumming_state
                )
                if snapshot.state == back_test.RUNNING_STATE:
                    self._bot_manager.start(bot_id)
                    self.log(f"✓ Bot {bot_id} RUNNING.", "success")
                    self.log(tab_surface.walk_started_line(snapshot), "info")
                    self._redraw_stats()
                    return
                if snapshot.state == back_test.STOPPED_STATE:
                    self._bot_manager.stop(bot_id)
                    self.log(tab_surface.walk_ended_line(snapshot), "info")
                    self._redraw_stats()
                    return
            except KeyError:
                logger.debug("stats for %s dropped: no record held", bot_id)
                return
            self._stats_dirty = True
            if not self._stats_redraw_timer.isActive():
                self._stats_redraw_timer.start()

        def _redraw_stats(self) -> None:
            """Push every venue's rows to the page through ``refresh_bots``
            and clear the dirty mark; the strip reads the same records on the
            window's tick."""
            self._stats_dirty = False
            self._stats_redraw_timer.stop()
            self.refresh_bots()

        def _push_pending_log(self) -> bool:
            """Push every line painted since the last push through ``log_payload``."""
            if not self._log.painted:
                return False
            return self.show_models({LOG_METHOD: log_payload(self._log)})

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
            carries it; ``held`` and ``mode`` are read off ``FleetSource`` on
            every call, so the card's Clear Fleet and its mode row follow the
            fleet.
            """
            self._state.held = len(self._fleet_source.bots())
            self._state.set_mode(self._fleet_source.mode())
            return self.show_models({tab_surface.METHOD: self._state.view_model(asked)})

        def add_exchange_tab(self, exchange_id: str, display_name: str) -> None:
            """Seat one venue's models and draw its page in the layer stack."""
            if exchange_id in self._venues:
                return
            self._venues[exchange_id] = SimVenue(
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
            """Hand every seated venue its rows from ``FleetSource.statuses`` and
            push the fleet to the page; answers how many rows were handed out."""
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
            if not chosen:
                feed = {"cause": "no_selection", "detail": {}, "reason": ""}
            else:
                feed = tab_surface.ivp_feed(
                    self._tablet_source, self._fleet_source.bot_for(chosen)
                )
            if feed.get("summary"):
                self._panel.no_data_cause = ""
                self._panel.show_stored(
                    feed["stored"], feed["when"], feed["age"], feed["message"]
                )
            else:
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

        def _create_bot(
            self,
            exchange_id: str = "",
            defaults_override: Optional[dict] = None,
        ) -> None:
            """Open ``_open_bot_wizard`` on the next event-loop turn, after the
            page's console callback that carried the press has returned.

            A ``QWebEngineView`` opened inside another page's console callback
            never finishes loading; one turn later it loads.
            """
            QTimer.singleShot(
                0, lambda: self._open_bot_wizard(exchange_id, defaults_override)
            )

        def _open_bot_wizard(
            self,
            exchange_id: str = "",
            defaults_override: Optional[dict] = None,
        ) -> None:
            """Open the Simulator's Bot Creation Wizard over ``wizard_exchanges``,
            the stored defaults, the tablet market table and each venue's
            ``venue_timeframes``; on Finish hand its config to
            ``FleetSource.create`` and fire ``fleet_changed``.

            The window's ``_create_bot``, forked, with no pre-flight, no
            ``ScrummingBot`` and no bot manager; ``defaults_override`` merges over
            the stored defaults.
            """
            self.show_log_call(
                "log", wizard_surface.OPENING_FORMAT.format(exchange_id=exchange_id)
            )
            wizard_class = surface_class(SIM_BOT_WIZARD)
            exchanges = wizard_surface.wizard_exchanges(
                layer_exchanges(self._state.exchanges)[ALIAS_LAYER],
                self._tablet_source,
            )
            defaults = wizard_surface.stored_defaults()
            if defaults_override:
                defaults = {**defaults, **defaults_override}
            markets = wizard_surface.tablet_markets(self._tablet_source)
            wizard = wizard_class(
                exchanges,
                defaults,
                self,
                theme=self._theme,
                markets=markets,
                timeframes=wizard_surface.venue_timeframes(exchanges),
            )
            try:
                accepted = wizard.exec() == wizard.DialogCode.Accepted
                config = wizard.get_bot_config() if accepted else {}
            finally:
                # The dialog's QWebEngineView is deleted on this thread by the
                # event loop; a worker thread's garbage collection would abort.
                wizard.deleteLater()
            if not accepted:
                self.show_log_call("log", wizard_surface.CANCELLED_TEXT, "warning")
                return
            logger.info("Sim bot creation config: %s", config)
            if config.get("mode") == EXTRACTOR_MODE:
                reason = wizard_surface.extractor_parent_refusal(
                    self._fleet_source.bots(),
                    str(config.get("base_currency") or ""),
                    str(config.get("exchange_id") or exchange_id),
                )
                if reason is not None:
                    QMessageBox.critical(
                        self,
                        wizard_surface.REFUSAL_TITLE,
                        wizard_surface.REFUSAL_BOX_FORMAT.format(reason=reason),
                    )
                    self.show_log_call(
                        "log",
                        wizard_surface.REFUSED_FORMAT.format(reason=reason),
                        "error",
                    )
                    return
            try:
                bot = self._fleet_source.create(config)
            except (ValueError, TypeError) as exc:
                self.show_log_call(
                    "log", wizard_surface.REJECTED_FORMAT.format(error=exc), "error"
                )
                logger.error("Sim bot creation rejected: %s", exc)
                return
            self.show_log_call("log", wizard_surface.created_line(bot), "success")
            self.fleet_changed.emit()

        def _on_bot_fire(self, bot_id: str) -> None:
            """Manual Fire on a sim bot: ask ``FleetSource`` to ``fire`` and log the
            refusal to the Activity Log, as the window logs a failed Fire."""
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
            the Qt toggle's ``_on_activity_pause_toggled`` does; a second ask
            for the state already held changes nothing. Answers ``_log.paused``.
            """
            wanted = bool(paused)
            if wanted != self._log.paused:
                self.show_log_call("pause" if wanted else "resume")
            if wanted != self._state.activity_paused:
                self.show_tab({tab_surface.ACTIVITY_PAUSED_PARAM: wanted})
            return self._log.paused

        def set_api_paused(self, paused: bool) -> bool:
            """Pause or resume the state's ``ApiPauseBuffer`` and set the
            toggle's caption, as the Qt toggle's ``_on_api_pause_toggled``
            does: a resume flushes the held blocks in order under the marker.
            A second ask for the state already held changes nothing. Answers
            the buffer's ``paused``."""
            wanted = bool(paused)
            if wanted != self._state.api_buffer.paused:
                self.show_tab({tab_surface.API_PAUSED_PARAM: wanted})
            return self._state.api_buffer.paused

        def _on_api_event(self, entry: dict) -> None:
            """Push one ``api_log()`` entry to the page as Live's block, refusing
            a call off the GUI thread; ``SimTradingTabState`` appends it to the
            pane or holds it while paused."""
            current = threading.current_thread().name
            if tab_surface.api_event_off_thread(
                entry, "SimTradingTabReact._on_api_event", current
            ):
                return
            self.show_tab({tab_surface.API_LINES_PARAM: [tab_surface.api_block(entry)]})

        def _activity_log_watchdog(self) -> None:
            """One tick of Live's Activity-Log watchdog over the tab's
            ``StatusLogModel`` and ``SimBotManager.bots``: each line
            ``watchdog_lines`` answers is pushed as a ``force_log`` and written
            to the file logger."""
            try:
                stats = self._log.health_stats()
            except Exception as exc:
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
            ``_on_bot_command`` forked over ``SimBotManager``, with no venue
            connect, Live's Activity Log lines, Live's sounds and Live's Delete
            box, and ``fleet_changed`` fired when the state moved or the record
            left."""
            bot = self._bot_manager.get_bot(bot_id)
            if not bot:
                self.log(f"Bot {bot_id} not found.", "error")
                return

            if (
                self.battery_running()
                and command == "stop"
                and bot_id in self._battery.get("bot_ids", [])
            ):
                self._stop_battery(bot_id)
                return

            if self.run_running():
                if command == "stop" and bot_id in self._run.get("bot_ids", []):
                    self._stop_run(bot_id)
                    return
                self.log(
                    tab_surface.run_in_flight_line(
                        self._run.get("mode", ""),
                        len(self._run.get("bot_ids", [])),
                        command,
                    ),
                    "warning",
                )
                return

            sound = get_sound_engine()
            moved = False

            if command == "start":
                try:
                    moved = self._bot_manager.start(bot_id) != bot.state
                    self.log(f"✓ Bot {bot_id} RUNNING.", "success")
                    self._notify(f"Bot {bot_id} RUNNING", "success")
                    sound.play_state_change()
                except Exception as exc:
                    self.log(f"Failed to start bot {bot_id}: {exc}", "error")
                    sound.play_error()

            elif command == "pause":
                self.log(f"Pausing bot {bot_id}...", "info")
                try:
                    moved = self._bot_manager.pause(bot_id) != bot.state
                    self.log(f"Bot {bot_id} paused.", "warning")
                    self._notify(f"Bot {bot_id} PAUSED", "warning")
                    sound.play_state_change()
                except Exception as exc:
                    self.log(f"Failed to pause bot {bot_id}: {exc}", "error")

            elif command == "stop":
                self.log(f"Stopping bot {bot_id}...", "info")
                try:
                    moved = self._bot_manager.stop(bot_id) != bot.state
                    self.log(f"Bot {bot_id} stopped.", "info")
                    self._notify(f"Bot {bot_id} STOPPED", "info")
                    sound.play_state_change()
                except Exception as exc:
                    self.log(f"Failed to stop bot {bot_id}: {exc}", "error")

            elif command == "restart":
                try:
                    self._bot_manager.restart(bot_id)
                    moved = True
                    self.log(f"✓ Bot {bot_id} restarted.", "success")
                    self._notify(f"Bot {bot_id} RESTARTED", "success")
                    sound.play_state_change()
                except Exception as exc:
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
                    except Exception as exc:
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
            page's console callback that carried the press has returned.

            A ``QWebEngineView`` opened inside another page's console callback
            never finishes loading; one turn later it loads.
            """
            QTimer.singleShot(0, lambda: self._open_bot_detail(bot_id))

        def _open_bot_detail(self, bot_id: str) -> None:
            """Open the Simulator's Bot Settings window,
            ``surface_class(SIM_BOT_DETAIL)``, for ``bot_id`` over its
            ``SimBotView`` and follow Prev and Next over the venue's sim fleet,
            keeping the geometry and the tab."""
            bot = self._fleet_source.bot_for(bot_id)
            if bot is None:
                return
            window_class = surface_class(SIM_BOT_DETAIL)
            saved_geometry = None
            saved_tab_index = None
            while bot is not None:
                siblings = [
                    one.bot_id
                    for one in self._fleet_source.bots()
                    if one.exchange_id == bot.exchange_id
                ]
                rates = sim_scrum_surface.usd_rates(
                    self._fleet_source.statuses(bot.exchange_id)
                )
                view = SimBotView(bot, self._fleet_source.record_for(bot.bot_id))
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
            """Take off every venue whose id is not in ``listed``.

            The page draws the Get Started card again once a layer holds none.
            """
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
            """Seat a venue for each exchange the fleet names and drop the rest.

            The caption is ``exchange_display_name`` over the id, as Live
            captions an exchange saved with no name.
            """
            wanted = [str(eid) for eid in self._fleet_source.exchanges() if eid]
            for eid in wanted:
                self.add_exchange_tab(eid, exchange_display_name({"exchange_id": eid}))
            self._drop_unlisted_exchange_tabs(wanted)
            self.refresh_bots()
            self.refresh_votes()
            self._refresh_replay()
            self.show_tab({})

        # -- the replay layer ---------------------------------------------

        def _selected_bot(self):
            chosen = str(self._panel.selected_bot_id or "")
            return self._fleet_source.bot_for(chosen) if chosen else None

        def _last_fill_bot(self):
            last = self._fills[-1].bot_id if self._fills else ""
            return self._fleet_source.bot_for(last) if last else None

        def _refresh_replay(
            self, follow_bot: bool = False, follow_run: bool = False
        ) -> dict:
            """Rebuild the chooser's items from ``tablet_choices`` over
            ``replay_source`` and the held fleet, keep the chosen key when it is
            still listed or take ``default_tablet_key`` for the run's last bot
            under ``follow_run`` and for the selected bot otherwise, then
            ``_feed_replay``."""
            source = self.replay_source()
            choices = sim.tablet_choices(source, self._fleet_source.bots())
            keys = [str(one["key"]) for one in choices]
            if follow_run or follow_bot or self._tablet_key not in keys:
                bot = self._last_fill_bot() if follow_run else None
                wanted = sim.default_tablet_key(
                    source, bot if bot is not None else self._selected_bot()
                )
                self._tablet_key = (
                    wanted if wanted in keys else (keys[0] if keys else "")
                )
            self._choices = choices
            return self._feed_replay()

        def _feed_replay(self) -> dict:
            """Build ``replay_feed`` for the chosen key, the run's fills marked
            on the playback and the figures beside it, push it as the tab's
            ``replay`` through ``show_tab``, so the page redraws the chooser, the
            button, the figures and the two windows, and emit
            ``MARKS_DRAWN_SIGNAL`` with the pushed state against the feed."""
            last = self._fills[-1].bot_id if self._fills else ""
            feed = sim.replay_feed(
                self.replay_source(),
                self._tablet_key,
                bots=self._fleet_source.bots(),
                fills=self._fills,
                outcome=self._battery_outcome,
                last_bot_id=last,
                selected_bot_id=str(self._panel.selected_bot_id or ""),
            )
            self._replay = feed
            self.show_tab(
                {
                    tab_surface.REPLAY_PARAM: tab_surface.replay_model(
                        feed, self._choices, self.retrieval_running()
                    )
                }
            )
            pushed = dict(self._state.replay or {})
            _pin_emit(
                tab_surface.MARKS_DRAWN_SIGNAL,
                actual=tab_surface.marks_reading(
                    self._tablet_key, pushed.get("playback"), pushed.get("figures")
                ),
                expected=tab_surface.marks_reading(
                    self._tablet_key, feed["playback"], feed["figures"]
                ),
                context={"layer": self._state.replay_layer, "mode": self.mode()},
            )
            sink = _pin_sink()
            if sink is not None:
                sink.flush()
            return feed

        def _choose_tablet(self, key: str) -> dict:
            """The page's chooser moved: draw the item ``key`` names."""
            self._tablet_key = str(key or "")
            return self._feed_replay()

        def _follow_bot_tablet(self) -> None:
            """The panel's bot changed: the chooser takes that bot's tablet."""
            self._refresh_replay(follow_bot=True)

        def _retrieve_tablet(self) -> None:
            """Retrieve Tablet or Update Tablet: one line and nothing started
            while ``retrieval_running`` or with no item chosen; else
            ``retrieval_span`` over the chosen item, the started line, and
            ``_compute_retrieval`` on a daemon thread over the read-only
            connector."""
            if self.retrieval_running():
                self.log(tab_surface.RETRIEVAL_RUNNING_TEXT, "warning")
                return
            choice = next(
                (
                    one
                    for one in sim.tablet_choices(
                        self.replay_source(), self._fleet_source.bots()
                    )
                    if str(one["key"]) == self._tablet_key
                ),
                None,
            )
            if choice is None:
                self.log(tab_surface.RETRIEVAL_NO_CHOICE_TEXT, "warning")
                return
            entry = self.replay_source().entry_for(self._tablet_key)
            since_ms, until_ms = tablet_retrieval.retrieval_span(entry)
            if since_ms > until_ms:
                self.log(
                    tab_surface.retrieval_current_line(self._tablet_key, until_ms),
                    "info",
                )
                return
            asset = str(choice["asset"])
            exchange_id = str(choice["exchange_id"])
            year = datetime.fromtimestamp(until_ms / 1000.0, tz=timezone.utc).year
            self._retrieval = {
                "key": self._tablet_key,
                "asset": asset,
                "exchange_id": exchange_id,
                "on_disk": entry is not None,
                "file": tablet_filename(
                    asset, tablet_retrieval.TIMEFRAME, year, exchange_id=exchange_id
                ),
                "root": self.replay_source().root(),
            }
            self.log(
                tab_surface.retrieval_started_line(
                    self._tablet_key,
                    asset,
                    exchange_id,
                    entry is not None,
                    since_ms,
                    until_ms,
                ),
                "success",
            )
            self._retrieval_thread = threading.Thread(
                target=self._compute_retrieval,
                args=(
                    asset,
                    exchange_id,
                    since_ms,
                    until_ms,
                    self._retrieval["root"],
                ),
                name="sim-tablet-retrieval",
                daemon=True,
            )
            self._retrieval_thread.start()
            self._feed_replay()

        def _compute_retrieval(
            self,
            asset: str,
            exchange_id: str,
            since_ms: int,
            until_ms: int,
            root: Any,
        ) -> None:
            """Run ``tablet_retrieval.retrieve`` over ``root``, the replay
            layer's tablet root at the press, and the connector and hand the
            ``RetrievalOutcome`` to the GUI thread through
            ``retrieval_finished``; a walk that raises hands one carrying the
            error."""
            try:
                outcome = asyncio.run(
                    tablet_retrieval.retrieve(
                        root,
                        self._connector,
                        asset,
                        exchange_id,
                        since_ms,
                        until_ms,
                    )
                )
            except Exception as exc:  # noqa: BLE001 - the walk runs off-thread
                logger.exception("Stone Tablet retrieval failed: %s", exc)
                outcome = tablet_retrieval.RetrievalOutcome(
                    asset=asset,
                    exchange_id=exchange_id,
                    since_ms=since_ms,
                    until_ms=until_ms,
                    error=f"{type(exc).__name__}: {exc}",
                )
            self.retrieval_finished.emit(outcome)

        def _on_venue_call(self, call: VenueCall) -> None:
            """The connector's report, on the worker thread: cross to the GUI
            thread."""
            self.retrieval_call.emit(call)

        def _record_venue_call(self, call: VenueCall) -> None:
            """Record one venue call on ``api_log`` as ``retrieval_api_entry``,
            on the GUI thread: the tablet key and file come from
            ``call_tablet`` over the call itself, the root is the replay
            layer's held press while ``retrieval_running`` and
            ``battery_tablet_source`` otherwise, and the progress line is
            written for the replay layer's press alone, the Battery writing
            its own line per asset."""
            replay = self.retrieval_running()
            key, file = tablet_retrieval.call_tablet(call)
            root = (
                self._retrieval.get("root", "")
                if replay
                else self._battery_tablet_source.root()
            )
            self._api_log.record(
                **tab_surface.retrieval_api_entry(
                    call, key, file, root, tablet_retrieval.tablet_on_disk(root, file)
                )
            )
            if replay and not call.error:
                self.log(tab_surface.retrieval_progress_line(key, call), "info")

        def _take_retrieval(self, outcome) -> None:
            """Write the finished or refused line, point the chooser at the
            tablet now on disk, redraw the two windows and re-read the panel."""
            held = self._retrieval
            key = str(held.get("key") or "")
            self.log(
                tab_surface.retrieval_finished_line(
                    key, outcome, str(held.get("file") or ""), held.get("root", "")
                ),
                "error" if outcome.refused else "success",
            )
            written = sim.tablet_for(
                self.replay_source(),
                outcome.exchange_id,
                outcome.asset,
                tablet_retrieval.TIMEFRAME,
            )
            if written is not None:
                self._tablet_key = tablet_key(written)
            self._refresh_replay()
            self._feed_votes()

        # -- what the operator presses ------------------------------------

        def show_layer(self, layer: str, pressed: Optional[dict] = None) -> str:
            """Show ``layer`` behind the panel slot and redraw the tab; a change
            of layer emits ``LAYER_FLIPPED_SIGNAL`` with ``pressed``, the flip
            button's rect the page read at the press, against the previous
            press's rect."""
            leaving = self._state.replay_layer
            if layer in sim.LAYERS:
                self.show_tab({tab_surface.REPLAY_LAYER_PARAM: layer})
            shown = self._state.replay_layer
            if shown != leaving:
                _pin_emit(
                    tab_surface.LAYER_FLIPPED_SIGNAL,
                    **tab_surface.flipped_pin(
                        leaving, shown, pressed, self._last_flip_rect
                    ),
                )
                self._last_flip_rect = pressed
                sink = _pin_sink()
                if sink is not None:
                    sink.flush()
            return shown

        def flip_layer(self, pressed: Optional[dict] = None) -> str:
            """Swap the page between the panel layer and the replay layer; a
            flip to the replay layer re-reads the chooser off the disk."""
            other = (
                sim.LAYER_PLAYBACK
                if self._state.replay_layer == sim.LAYER_INDICATORS
                else sim.LAYER_INDICATORS
            )
            shown = self.show_layer(other, pressed)
            if shown == sim.LAYER_PLAYBACK:
                self._refresh_replay()
            return shown

        def run_action(self, payload: str) -> None:
            """Answer the flip, the Pause Console and Pause API Log presses,
            a corner or card way-in, the card's mode buttons, the replay
            layer's chooser and retrieval press, a venue sub-tab press, the
            panel's ``select_bot``, both bot tables' asks and the venue page's
            mode buttons, ``+ New Bot`` and command bar; every other ask is
            held."""
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
                    self.show_layer(
                        str(layer),
                        tab_surface.flip_rect(params.get(tab_surface.FLIP_RECT_PARAM)),
                    )
                wanted = params.get(tab_surface.ACTIVITY_PAUSED_PARAM)
                if wanted is not None:
                    self.set_activity_paused(bool(wanted))
                wanted = params.get(tab_surface.API_PAUSED_PARAM)
                if wanted is not None:
                    self.set_api_paused(bool(wanted))
                way_in = params.get(tab_surface.WAY_IN_PARAM)
                if way_in is not None:
                    self._way_in(str(way_in))
                chosen_tablet = params.get(tab_surface.TABLET_PARAM)
                if chosen_tablet is not None:
                    self._choose_tablet(str(chosen_tablet))
                if params.get(tab_surface.RETRIEVE_PARAM):
                    self._retrieve_tablet()
                shown = params.get(EXCHANGE_PARAM)
                if shown is not None:
                    self.show_tab({EXCHANGE_PARAM: str(shown)})
                card_mode = params.get(tab_surface.MODE_PARAM)
                if card_mode is not None:
                    self.set_mode(str(card_mode))
            elif (
                method == venue_surface.METHOD
                and params.get(venue_surface.MODE_PARAM) is not None
            ):
                self.set_mode(str(params.get(venue_surface.MODE_PARAM)))
            elif method == LOG_METHOD:
                wanted = params.get(tab_surface.LOG_PAUSED_PARAM)
                if wanted is not None:
                    self.set_activity_paused(bool(wanted))
            elif method == PANEL_METHOD and params.get("action") == "flip_layer":
                self.flip_layer(
                    tab_surface.flip_rect(params.get(tab_surface.FLIP_RECT_PARAM))
                )
            elif (
                method == PANEL_METHOD
                and params.get("action") == tab_surface.SELECT_BOT_ACTION
            ):
                chosen = self._panel.select_bot(
                    str(params.get(tab_surface.BOT_ID_PARAM) or "")
                )
                self._feed_votes(chosen)
                self._follow_bot_tablet()
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
            self._venue_models = venue_models(self._venues, self.mode())
            self._web = QWebEngineView(self)
            self._web.setAccessibleName(ACCESSIBLE_NAME)
            # repaint_pages reads the tone off the view on every theme switch.
            self._web.setProperty(TONE_PROPERTY, NIGREDO)
            self._web.setPage(SimTradingPage(self))
            self._web.loadFinished.connect(self._on_load_finished)
            self._web.setHtml(panel_html(self._models, self._venue_models, self._theme))
            self._layout.addWidget(self._web, 1)

        def _venue_published(self) -> None:
            """Re-read every seated venue, its header drawn for the run mode in
            force, and push the fleet to the page."""
            self._venue_models = venue_models(self._venues, self.mode())
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
