# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
"""The whole Bot Swarm tab drawn by React inside ``QWebEngineView``.

``BotSwarmReactTab`` replaces every Qt control ``BotVisualizationTab``
builds and answers the same public calls, dispatching each one through
``bot_visualizer_surface.apply_action``. ``BotSwarmTabPage`` carries the
page's own calls back to ``answer_call``.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Optional

from .main_tabs import bot_visualizer_surface as surface
from .react_history_panel import page_html

try:
    from PySide6.QtWebEngineCore import QWebEnginePage
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWidgets import QVBoxLayout, QWidget

    _HAS_WEBENGINE = True
except ImportError:
    # Without WebEngine, BotSwarmReactTab is never defined and its import fails by name.
    _HAS_WEBENGINE = False

logger = logging.getLogger("acervator.gui.react_bot_swarm_tab")

CALL_PREFIX = "acervator-call:"

#: The element ``bot_visualizer.js`` draws the tab into.
TAB_ROOT_ID = "tab-root"

ACCESSIBLE_NAME = "React Bot Swarm Tab"

#: The style sheet the page carries.
TAB_STYLE_ASSETS: tuple[str, ...] = ("bot_swarm_tab.css",)

#: The scripts the page carries. Order is load order.
TAB_SCRIPT_ASSETS: tuple[str, ...] = (
    "vendor/react.production.min.js",
    "vendor/react-dom.production.min.js",
    "design_tokens.js",
    "shared_widgets.js",
    "header_strip.js",
    "visualizer_themes.js",
    "bot_node.js",
    "wire_canvas.js",
    "quick_routing.js",
    "bot_visualizer.js",
)

TAB_BODY = f'<div id="{TAB_ROOT_ID}"></div>'

#: The count of swarm rows the browser drew, over all three layers.
ROW_COUNT_JS = "document.querySelectorAll('[data-part=\"swarm-row\"]').length"

#: The bridge this host answers. The Electron shell binds ``window.acervator``
#: in its own preload, so this source is never a file under ``src/gui/web``.
HOST_SCRIPT = """(function (global) {
  "use strict";

  var pending = {};
  var lastId = 0;

  global.acervator = {
    call: function (method, params) {
      lastId += 1;
      var id = lastId;
      return new Promise(function (resolve) {
        pending[id] = resolve;
        console.log(
          "%(call)s" +
            JSON.stringify({ id: id, method: method, params: params || {} })
        );
      });
    }
  };

  global.acervatorResolve = function (id, answer) {
    var resolve = pending[id];
    delete pending[id];
    if (typeof resolve === "function") {
      resolve(answer);
    }
    return id;
  };

  global.acervatorBotSwarmDrawn = function () {
    return document.getElementById("%(tab)s") !== null;
  };

  global.acervatorBotSwarmHelpers = function () {
    var loaders = [
      global.acervatorLoadVisualizerThemes,
      global.acervatorLoadTokens,
      global.acervatorLoadWidgets,
      global.acervatorLoadHeader
    ];
    var asked = loaders.map(function (one) {
      return typeof one === "function" ? one({}) : Promise.resolve(null);
    });
    return Promise.all(asked).then(function () {
      var root = document.getElementById("%(tab)s");
      if (root !== null && global.acervatorBotSwarm) {
        global.acervatorBotSwarm.renderTab(root, undefined);
      }
      return true;
    });
  };
})(window);""" % {
    "call": CALL_PREFIX,
    "tab": TAB_ROOT_ID,
}

HELPERS_SCRIPT = "window.acervatorBotSwarmHelpers();"


def tab_html(theme: str = "cyberpunk_dark") -> str:
    """The whole tab page as one string, with no network fetch."""
    return page_html(
        TAB_STYLE_ASSETS, TAB_SCRIPT_ASSETS, TAB_BODY, theme, (HOST_SCRIPT,)
    )


def resolve_script(call_id: Any, payload: dict) -> str:
    """The one JS statement that settles the page's promise ``call_id``."""
    return (
        "window.acervatorResolve("
        + json.dumps(call_id)
        + ", "
        + json.dumps(payload, ensure_ascii=True)
        + ");"
    )


def push_script(model: dict) -> str:
    """The one JS statement that hands ``model`` to the page and redraws it.

    ``ensure_ascii=True`` escapes U+2028 and U+2029, which are legal inside
    a JSON string and are JavaScript line terminators.
    """
    body = json.dumps(model, ensure_ascii=True)
    return (
        "window.acervatorSetBotSwarm("
        + body
        + ");window.acervatorBotSwarm.renderTab("
        + 'document.getElementById("'
        + TAB_ROOT_ID
        + '"), '
        + body
        + ");"
    )


if _HAS_WEBENGINE:

    class BotSwarmTabPage(QWebEnginePage):
        """Routes the page's ``acervator-call:`` console lines to its owner."""

        def __init__(self, owner) -> None:
            """Hold ``owner`` as the widget that answers the page."""
            super().__init__(owner)
            self._owner = owner

        def javaScriptConsoleMessage(self, level, message, line, source) -> None:
            """Hand a call to the owner and drop every other line."""
            del level, line, source
            if message.startswith(CALL_PREFIX):
                self._owner.answer_call(message[len(CALL_PREFIX) :])

    class BotSwarmReactTab(QWidget):
        """The Bot Swarm tab with its header, wires and rows drawn by React.

        ``model`` returns the last payload pushed, ``page_ready`` reports
        the document state, and ``row_count`` counts the rows the DOM drew.
        """

        def __init__(self, parent=None, theme: str = "cyberpunk_dark") -> None:
            super().__init__(parent)
            self.setAccessibleName(ACCESSIBLE_NAME)
            self._state = surface.BotVisualizerModel()
            self._page_ready = False
            self._last_model: dict = {}
            self._methods: Optional[dict] = None
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)
            self._web = QWebEngineView(self)
            self._web_page = BotSwarmTabPage(self)
            self._web.setPage(self._web_page)
            self._web.loadFinished.connect(self._on_load_finished)
            self._web.setHtml(tab_html(theme))
            layout.addWidget(self._web, 1)

        # -- what the render path pushes through -------------------------

        @property
        def page_ready(self) -> bool:
            """True once ``_on_load_finished`` has seen a successful load."""
            return self._page_ready

        def model(self) -> dict:
            """A copy of the last payload pushed, empty before the first push."""
            return dict(self._last_model)

        def row_count(self, callback: Callable[[Any], None]) -> bool:
            """Run ``ROW_COUNT_JS`` and hand the count to ``callback``.

            Returns False and calls nothing while the page is not ready.
            """
            if not self._page_ready:
                return False
            self._web.page().runJavaScript(ROW_COUNT_JS, callback)
            return True

        # -- what the page reports back ----------------------------------

        def answer_call(self, payload: str) -> None:
            """Apply one action from the page and settle its promise."""
            try:
                request = json.loads(payload)
            except ValueError:
                logger.warning("Bot Swarm page sent a call that is not JSON")
                return
            method = str(request.get("method") or "")
            params = request.get("params") or {}
            if method == surface.METHOD:
                answer = self.take(params)
            else:
                answer = self._other_surface(method, params)
            self._run(resolve_script(request.get("id"), answer))

        def _other_surface(self, method: str, params: dict) -> Any:
            """Answer a method the page asks for that is not this tab's own.

            The Electron shell answers the same names through the same
            ``desktop_bridge`` registry, so the page reads one set of values.
            """
            handler = self._registry().get(method)
            if handler is None:
                logger.warning("Bot Swarm page asked for %s, which is unknown", method)
                return None
            try:
                return handler(params)
            except Exception as exc:
                logger.warning("Bot Swarm page call to %s failed: %s", method, exc)
                return None

        def _registry(self) -> dict:
            if self._methods is None:
                from src.core.desktop_bridge import build_registry

                self._methods = build_registry()
            return self._methods

        # -- the state the Qt controls used to hold ----------------------

        def take(self, params: dict) -> dict:
            """Apply one action to the model, push the payload and return it."""
            answer = surface.apply_action(self._state, params)
            self._last_model = answer
            if self._page_ready:
                self._run(push_script(answer))
            return answer

        def update_bots(self, bot_statuses: list) -> None:
            """Redraw the fleet from one status list."""
            self.take({"action": "update_bots", "bot_statuses": bot_statuses})

        def set_app_theme(self, theme_name: str) -> None:
            """Read every locust's growth-stage colours from theme_name."""
            self.take({"action": "set_app_theme", "name": theme_name})

        def register_sim_run(self, sim_id: str, label: str, cfg: dict) -> None:
            """Add one Simulator Swarm row."""
            self._register(surface.SIM_KIND, sim_id, label, cfg)

        def update_sim_run(
            self, sim_id: str, pnl: float, trades: int, candle_idx: int = 0
        ) -> None:
            """Update one Simulator Swarm row from a sim tick."""
            self.take(
                {
                    "action": "update_sim",
                    "run_id": sim_id,
                    "pnl": pnl,
                    "trades": trades,
                    "candle_idx": candle_idx,
                }
            )

        def stop_sim_run(self, sim_id: str, pnl: float = 0.0, trades: int = 0) -> None:
            """Mark one Simulator Swarm row stopped."""
            self._stop("stop_sim", sim_id, pnl, trades)

        def register_paper_run(self, paper_id: str, label: str, cfg: dict) -> None:
            """Add one Paper Swarm row."""
            self._register(surface.PAPER_KIND, paper_id, label, cfg)

        def update_paper_run(
            self, paper_id: str, price: float, pnl: float, trades: int
        ) -> None:
            """Update one Paper Swarm row from a paper tick."""
            self.take(
                {
                    "action": "update_paper",
                    "run_id": paper_id,
                    "price": price,
                    "pnl": pnl,
                    "trades": trades,
                }
            )

        def stop_paper_run(
            self, paper_id: str, pnl: float = 0.0, trades: int = 0
        ) -> None:
            """Mark one Paper Swarm row stopped."""
            self._stop("stop_paper", paper_id, pnl, trades)

        def register_live_run(self, bot_id: str, label: str, cfg: dict) -> None:
            """Add one live swarm row."""
            self._register(surface.LIVE_KIND, bot_id, label, cfg)

        def update_live_run(
            self,
            bot_id: str,
            price: float = 0.0,
            pnl: float = 0.0,
            trades: int = 0,
            status: str = None,
        ) -> None:
            """Update one live swarm row from a bot tick."""
            self.take(
                {
                    "action": "update_live",
                    "run_id": bot_id,
                    "price": price,
                    "pnl": pnl,
                    "trades": trades,
                    "status": status,
                }
            )

        def stop_live_run(self, bot_id: str, pnl: float = 0.0, trades: int = 0) -> None:
            """Mark one live swarm row stopped."""
            self._stop("stop_live", bot_id, pnl, trades)

        def remove_wire(self, source_id: str, target_id: str) -> None:
            """Drop the wire between two bots."""
            self.take(
                {
                    "action": "remove_wire",
                    "source_id": source_id,
                    "target_id": target_id,
                }
            )

        # -- internals ----------------------------------------------------

        def _register(self, kind: str, run_id: str, label: str, cfg: dict) -> None:
            self.take(
                {
                    "action": "register_" + kind,
                    "run_id": run_id,
                    "label": label,
                    "cfg": cfg,
                }
            )

        def _stop(self, action: str, run_id: str, pnl: float, trades: int) -> None:
            self.take(
                {
                    "action": action,
                    "run_id": run_id,
                    "pnl": pnl,
                    "trades": trades,
                }
            )

        def _run(self, script: str) -> None:
            self._web.page().runJavaScript(script)

        def _on_load_finished(self, ok: bool) -> None:
            self._page_ready = bool(ok)
            if not ok:
                logger.warning("React Bot Swarm tab page failed to load")
                return
            self._run(
                push_script(self._last_model or surface.build_payload(self._state))
            )
            self._run(HELPERS_SCRIPT)
