# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
"""The Charts tab drawn by React inside ``QWebEngineView``.

``ChartsTabReact`` holds one ``trade_charts_tab_surface.TradeChartsTabModel``
and draws ``src/gui/web/trade_charts_tab.js`` through ``panel_host.js``, which
mounts ``native_chart.js`` into the chart slot that module keeps. The tab
answers ``update_charts``, ``fetch_chart_data`` and ``set_ata_source``, and
``ChartsTabPage`` carries the page's own bridge asks back to ``run_ask``.
``page_html`` inlines ``trade_charts_tab.css`` and every script, so the page
fetches nothing.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from .main_tabs import design_system_surface, native_chart_surface
from .main_tabs import trade_charts_tab_surface as surface
from .react_history_panel import STYLE_SOURCE_ASSETS, page_html, read_asset
from .react_main_window import read_renderer_asset

#: How long the tab waits after the last resize step before it redraws.
RESIZE_SETTLE_MS = 120

try:
    from PySide6.QtCore import QTimer
    from PySide6.QtWebEngineCore import QWebEnginePage
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWidgets import QVBoxLayout, QWidget

    _HAS_WEBENGINE = True
except ImportError:
    # Without WebEngine, ChartsTabReact is never defined and its import
    # fails by name.
    _HAS_WEBENGINE = False

logger = logging.getLogger("acervator.gui.react_charts_tab")

ACCESSIBLE_NAME = "React Charts Tab"

#: The console-line prefix every bridge ask the page makes carries.
ASK_PREFIX = "acervator-ask:"

#: The element ``trade_charts_tab.js`` draws the tab into.
PANEL_ROOT_ID = "panel-root"

#: The renderer module the page draws.
PANEL_MODULE = "trade_charts_tab.js"

#: The module ``trade_charts_tab.js`` mounts into its own chart slot.
CHILD_MODULES: tuple[str, ...] = ("native_chart.js",)

#: The style sheet the page carries.
STYLE_ASSETS: tuple[str, ...] = ("trade_charts_tab.css",)

#: The scripts every page carries before the modules. Order is load order.
BASE_SCRIPT_ASSETS: tuple[str, ...] = (
    "vendor/react.production.min.js",
    "vendor/react-dom.production.min.js",
)

#: The panel host, read from ``desktop/renderer`` and inlined.
SHELL_SCRIPT = "panel_host.js"

#: The global a page carries the name of the module running now under.
NAME_GLOBAL = "acervatorInlinedModule"

#: The page ground. Every colour a chart mark paints arrives from the payload
#: skin, so no rule here may set one on a mark.
PAGE_STYLE = (
    "*{margin:0;padding:0;box-sizing:border-box}"
    "html,body{height:100%}"
    "body{background:var(--bg);color:var(--text);overflow:hidden;"
    'font:12px/1.4 "Segoe UI","Helvetica Neue",Arial,sans-serif}'
    f"#{PANEL_ROOT_ID}{{height:100%}}"
)

#: The JS expression naming every module that registered a panel.
DRAWN_MODULES_JS = "window.acervatorPanelHost.registered().join(',')"

#: The JS expression naming every panel the page refused to draw.
PANEL_FAULTS_JS = "JSON.stringify(window.acervatorPanelHost.faults())"

#: The JS expression naming each style sheet the page holds and its rule count.
LOADED_STYLES_JS = "JSON.stringify(window.acervatorChartsPage.styles())"

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

_HOST_SOURCE = """(function (global) {
  "use strict";

  var NAME = %(name)s;
  var ROOT = "%(root)s";
  var waiting = {};
  var next = 1;

  global.ACERVATOR_MODULES = %(roster)s;
  global.acervatorSetTokens(%(tokens)s);
  global.acervatorTokens.apply(document.documentElement);

  // An ask goes out as one console line and is answered by its own id, so
  // an arrow, the ticker and the chart slot all reach the same model.
  global.acervator = {
    call: function (method, params) {
      var id = next;
      next += 1;
      console.log(
        "%(ask)s" +
          JSON.stringify({ id: id, method: method, params: params || {} })
      );
      return new Promise(function (resolve, reject) {
        waiting[id] = { resolve: resolve, reject: reject };
      });
    }
  };

  global.acervatorChartsAnswer = function (id, model, refusal) {
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

  function root() {
    return document.getElementById(ROOT);
  }

  global.acervatorChartsMount = function (model) {
    global.acervatorSetCharts(model);
    return global.acervatorPanelHost.mount(NAME, root(), model);
  };

  global.acervatorChartsPush = function (model) {
    global.acervatorSetCharts(model);
    global.acervatorCharts.renderTab(root(), model);
    return true;
  };

  global.acervatorChartsPage = {
    styles: function () {
      var found = [];
      var tags = document.querySelectorAll("style[data-asset]");
      for (var at = 0; at < tags.length; at++) {
        var sheet = tags[at].sheet;
        found.push([
          tags[at].getAttribute("data-asset"),
          sheet === null ? 0 : sheet.cssRules.length
        ]);
      }
      return found;
    }
  };
})(window);"""


def module_name(asset: str = PANEL_MODULE) -> str:
    """``asset`` without its ``.js`` suffix, which is the panel's own name."""
    return asset.rsplit(".", 1)[0]


def roster() -> tuple[str, ...]:
    """Every module the page carries, in load order.

    ``STYLE_SOURCE_ASSETS`` leads: ``trade_charts_tab.js`` reads a payload
    colour back to its token through ``shared_widgets.variableFor``.
    """
    return STYLE_SOURCE_ASSETS + CHILD_MODULES + (PANEL_MODULE,)


def namer_script() -> str:
    """The shim that hands the panel host the name an inlined module lacks."""
    return _NAMER_SOURCE % {"name_global": NAME_GLOBAL}


def marker_script(asset: str) -> str:
    """The one statement naming the module whose script tag comes next."""
    return _MARKER_SOURCE % {
        "name_global": NAME_GLOBAL,
        "module": json.dumps(module_name(asset), ensure_ascii=True),
    }


def host_script() -> str:
    """The page's own glue: the design tokens, the roster and the ask channel."""
    return _HOST_SOURCE % {
        "ask": ASK_PREFIX,
        "name": json.dumps(module_name(), ensure_ascii=True),
        "roster": json.dumps(list(roster()), ensure_ascii=True),
        "root": PANEL_ROOT_ID,
        "tokens": json.dumps(design_system_surface.view_model({}), ensure_ascii=True),
    }


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


def panel_html(theme: object = None) -> str:
    """The whole Charts page as one string, with no network fetch.

    ``STYLE_ASSETS`` is inlined into the page head, so the tab's chrome
    reaches the browser without a stylesheet request.
    """
    return page_html(STYLE_ASSETS, (), page_body(), theme, (host_script(),))


def _payload_json(model: Any) -> str:
    """``model`` as JSON, with U+2028 and U+2029 escaped out of the page."""
    return json.dumps(model, ensure_ascii=True)


def mount_script(model: dict) -> str:
    """The statement that draws ``model`` into the page for the first time."""
    return "window.acervatorChartsMount(" + _payload_json(model) + ");"


def push_script(model: dict) -> str:
    """The statement that hands ``model`` to a drawn page and redraws it."""
    return "window.acervatorChartsPush(" + _payload_json(model) + ");"


def answer_script(ask_id: Any, model: Any) -> str:
    """The statement that settles the ask ``ask_id`` with ``model``."""
    return (
        "window.acervatorChartsAnswer("
        + json.dumps(ask_id, ensure_ascii=True)
        + ","
        + _payload_json(model)
        + ",null);"
    )


def refusal_script(ask_id: Any, reason: str) -> str:
    """The statement that refuses the ask ``ask_id`` with ``reason``."""
    return (
        "window.acervatorChartsAnswer("
        + json.dumps(ask_id, ensure_ascii=True)
        + ",null,"
        + json.dumps(str(reason), ensure_ascii=True)
        + ");"
    )


if _HAS_WEBENGINE:

    class ChartsTabPage(QWebEnginePage):
        """Routes the page's ``acervator-ask:`` console lines to its owner."""

        def __init__(self, owner) -> None:
            """Hold ``owner`` as the widget that answers the page."""
            super().__init__(owner)
            self._owner = owner

        def javaScriptConsoleMessage(self, level, message, line, source) -> None:
            """Hand a bridge ask to the owner and drop every other line."""
            del level, line, source
            if message.startswith(ASK_PREFIX):
                self._owner.run_ask(message[len(ASK_PREFIX) :])

    class ChartsTabReact(QWidget):
        """The Charts tab, drawn by ``trade_charts_tab.js`` and its chart module.

        ``build_panel`` loads the page once, on the first show, so a window
        that never opens the tab pays for no web view.
        """

        def __init__(self, parent: Optional[QWidget] = None, theme: object = None):
            """Start a tab holding no asset, with a fetcher the window drives."""
            super().__init__(parent)
            self.setAccessibleName(ACCESSIBLE_NAME)
            self._theme = theme
            self._model = surface.TradeChartsTabModel()
            self._payload: dict = {}
            self._page_ready = False
            self._drawn = False
            self._web: Any = None
            self._web_page: Any = None
            self._layout = QVBoxLayout(self)
            self._layout.setContentsMargins(0, 0, 0, 0)
            self._layout.setSpacing(0)
            self._resize_settle = QTimer(self)
            self._resize_settle.setSingleShot(True)
            self._resize_settle.setInterval(RESIZE_SETTLE_MS)
            self._resize_settle.timeout.connect(self._draw_again)

            from src.exchange.chart_data import ChartDataFetcher

            self._model.fetcher = ChartDataFetcher()

        # -- what the page is built from ---------------------------------

        @property
        def page_ready(self) -> bool:
            """True once ``_on_load_finished`` has seen a successful load."""
            return self._page_ready

        def panel_view(self):
            """The web view the tab draws in, or None before the first show."""
            return self._web

        def model(self) -> dict:
            """A copy of the last payload drawn, empty before the first draw."""
            return dict(self._payload)

        def showEvent(self, event) -> None:  # noqa: N802
            """Build the web view the first time the tab is shown."""
            super().showEvent(event)
            self.build_panel()

        def resizeEvent(self, event) -> None:  # noqa: N802
            """Re-arm the redraw, so the chart takes the width the tab now has."""
            super().resizeEvent(event)
            if self._drawn:
                self._resize_settle.start()

        def build_panel(self) -> None:
            """Create the tab's web view and load its page, once."""
            if self._web is not None:
                return
            self._web = QWebEngineView(self)
            self._web.setAccessibleName(ACCESSIBLE_NAME)
            self._web_page = ChartsTabPage(self)
            self._web.setPage(self._web_page)
            self._web.loadFinished.connect(self._on_load_finished)
            self._web.setHtml(panel_html(self._theme))
            self._layout.addWidget(self._web, 1)

        def redraw(self) -> None:
            """Build the payload from the model and draw it in the page."""
            self._payload = surface.build_view_model(self._model)
            if not self._page_ready:
                return
            if self._drawn:
                self._run(push_script(self._payload))
                return
            self._run(mount_script(self._payload))
            self._drawn = True

        # -- the calls the main window makes on the tab ------------------

        @property
        def panel(self):
            """The one chart panel every asset is drawn in."""
            return self._model.panel

        @property
        def entries(self) -> list:
            """One record per chartable bot, in the order the list offers them."""
            return [
                {"bot_id": bot_id, **self._model.assets[bot_id]}
                for bot_id in self._model.order
            ]

        @property
        def ata_entries(self) -> list:
            """One record per market ATA-SMP has called, in call order."""
            return [
                {"bot_id": bot_id, **self._model.ata_assets[bot_id]}
                for bot_id in self._model.ata_order
            ]

        @property
        def list_mode(self) -> str:
            """Which of the two lists the arrows walk."""
            return self._model.list_mode

        @property
        def shown(self) -> int:
            """The index into the list on screen the panel is drawing."""
            return self._model.list_shown()

        def current_entry(self) -> dict:
            """The record the panel follows, or an empty one when none exists."""
            return self._model.current()

        def set_ata_source(self, source) -> None:
            """Take the callable answering the markets ATA-SMP has called."""
            self._model.set_ata_source(source)

        def toggle_list(self) -> str:
            """Move the arrows to the other list and answer the mode on screen."""
            mode = self._model.toggle_list()
            self.redraw()
            return mode

        def step(self, by: int) -> int:
            """Move the shown asset by ``by`` and answer the new index."""
            at = self._model.step(by)
            self.redraw()
            return at

        def update_charts(
            self,
            bot_statuses: list,
            bot_manager=None,
            exchange_connectors: Optional[dict] = None,
        ) -> None:
            """Rebuild the asset list for one pass of bot statuses and redraw."""
            self._model.update_charts(bot_statuses, bot_manager, exchange_connectors)
            self.redraw()

        async def fetch_chart_data(
            self, exchange_connectors: Optional[dict] = None
        ) -> None:
            """Fetch the asset on screen, at most every 30 seconds, and redraw."""
            await self._model.fetch_chart_data(exchange_connectors)
            self.redraw()

        def log_trade(self, trade_data: dict) -> None:
            """Record a trade for chart markup."""
            self._model.log_trade(trade_data)

        def push_synthetic_candles(
            self,
            bot_id: str,
            symbol: str,
            candles: list,
            scenario: str = "",
            last_price: float = 0.0,
        ) -> None:
            """Draw one Nuclear Mode scenario's candles without a fetch."""
            self._model.push_synthetic_candles(
                bot_id, symbol, candles, scenario, last_price
            )
            self.redraw()

        # -- what the page asks back -------------------------------------

        def run_ask(self, payload: str) -> None:
            """Answer one bridge ask the page reported and hand it back by id."""
            try:
                ask = json.loads(payload)
            except ValueError:
                logger.warning("The React Charts page sent an ask that is not JSON")
                return
            ask_id = ask.get("id")
            try:
                answered = self._answer(str(ask.get("method") or ""), ask.get("params"))
            except Exception as exc:
                logger.warning("The React Charts page ask was refused: %s", exc)
                self._run(refusal_script(ask_id, f"{type(exc).__name__}: {exc}"))
                return
            self._run(answer_script(ask_id, answered))

        # -- internals ----------------------------------------------------

        def _answer(self, method: str, params: Any) -> Any:
            asked = params if isinstance(params, dict) else {}
            if method == surface.METHOD:
                self._payload = surface.build_view_model(
                    self._model,
                    asked.get("statuses"),
                    asked.get("connectors"),
                    asked.get("timeframe_change"),
                    False,
                    asked.get("trades"),
                    asked.get("synthetic"),
                    asked.get("step_by"),
                    asked.get("pick_at"),
                    asked.get("toggle_list", False),
                )
                return self._payload
            if method == native_chart_surface.METHOD:
                return native_chart_surface.view_model(asked)
            if method == design_system_surface.METHOD:
                return design_system_surface.view_model(asked)
            return None

        def _draw_again(self) -> None:
            if self._drawn:
                self._run(push_script(self._payload))

        def _run(self, script: str) -> None:
            self._web.page().runJavaScript(script)

        def _on_load_finished(self, ok: bool) -> None:
            self._page_ready = bool(ok)
            if not ok:
                logger.warning("The React Charts tab page failed to load")
                return
            self.redraw()
