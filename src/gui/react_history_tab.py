# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
"""The whole History tab drawn by React inside ``QWebEngineView``.

``HistoryReactTab`` replaces every Qt control ``HistoryTab`` builds and
inherits its fetch, filter, page and export behaviour unchanged.
``HistoryTabPage`` carries the page's own calls back to ``answer_call``
and ``run_action``.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Optional

from src.exchange import history_read_contract as hrc

from .history_tab import _HAS_QT, HistoryTab
from .main_tabs import history_tab_surface as surface
from .react_history_panel import ROW_COUNT_JS, page_html

try:
    from PySide6.QtWebEngineCore import QWebEnginePage
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWidgets import QVBoxLayout

    _HAS_WEBENGINE = True
except ImportError:
    # Without WebEngine, HistoryReactTab is never defined and its import fails by name.
    _HAS_WEBENGINE = False

logger = logging.getLogger("acervator.gui.react_history_tab")

CALL_PREFIX = "acervator-call:"
ACTION_PREFIX = "acervator-act:"

#: The element ``history_tab.js`` draws the tab's chrome into.
TAB_ROOT_ID = "tab-root"

#: The element inside that chrome the table's own root is moved into.
TABLE_MOUNT_ID = "history-tab-table"

ACCESSIBLE_NAME = "React History Tab"

#: The two style sheets the page carries. Order is load order.
TAB_STYLE_ASSETS: tuple[str, ...] = ("history_panel.css", "history_tab.css")

#: The four scripts the page carries. Order is load order.
TAB_SCRIPT_ASSETS: tuple[str, ...] = (
    "vendor/react.production.min.js",
    "vendor/react-dom.production.min.js",
    "history_panel.js",
    "history_tab.js",
)

TAB_BODY = f'<div id="{TAB_ROOT_ID}"></div>\n<div id="root"></div>'

#: The two buttons the page cannot answer without an exchange or a file dialog.
HOST_ACTIONS: tuple[str, ...] = ("refresh", "export")

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

  global.acervatorHistoryTabHostAction = function (key) {
    console.log("%(act)s" + JSON.stringify({ key: key }));
    return null;
  };

  global.acervatorHistoryTabDrawn = function () {
    var mount = document.getElementById("%(mount)s");
    var rows = document.getElementById("root");
    if (mount !== null && rows !== null && rows.parentNode !== mount) {
      mount.appendChild(rows);
    }
    return mount !== null && rows !== null;
  };

  global.acervatorHistoryTab.renderTab(document.getElementById("%(tab)s"), {});
})(window);""" % {
    "call": CALL_PREFIX,
    "act": ACTION_PREFIX,
    "mount": TABLE_MOUNT_ID,
    "tab": TAB_ROOT_ID,
}


def tab_html(theme: str = "cyberpunk_dark") -> str:
    """The whole tab page as one string, with no network fetch."""
    return page_html(
        TAB_STYLE_ASSETS, TAB_SCRIPT_ASSETS, TAB_BODY, theme, (HOST_SCRIPT,)
    )


def resolve_script(call_id: Any) -> str:
    """The one JS statement that settles the page's promise ``call_id``."""
    return "window.acervatorResolve(" + json.dumps(call_id) + ", null);"


def push_script(model: dict) -> str:
    """The one JS statement that hands ``model`` to the page.

    ``ensure_ascii=True`` escapes U+2028 and U+2029, which are legal inside
    a JSON string and are JavaScript line terminators.
    """
    return (
        "window.acervatorHistoryTab.setTab("
        + json.dumps(model, ensure_ascii=True)
        + ");"
    )


if _HAS_QT and _HAS_WEBENGINE:

    class HistoryTabPage(QWebEnginePage):
        """Routes the page's ``acervator-`` console lines to its owner."""

        def __init__(self, owner) -> None:
            """Hold ``owner`` as the widget that answers the page."""
            super().__init__(owner)
            self._owner = owner

        def javaScriptConsoleMessage(self, level, message, line, source) -> None:
            """Hand a call or an action to the owner and drop every other line."""
            del level, line, source
            if message.startswith(CALL_PREFIX):
                self._owner.answer_call(message[len(CALL_PREFIX) :])
            elif message.startswith(ACTION_PREFIX):
                self._owner.run_action(message[len(ACTION_PREFIX) :])

    class HistoryReactTab(HistoryTab):
        """The History tab with its chrome, controls and rows drawn by React."""

        def _build_ui(self) -> None:
            """Build the one web view the whole tab is drawn in."""
            self._set_filter_state(hrc.default_filters())
            self._exchanges: list[str] = []
            self._symbols: list[str] = []
            self._status: Optional[str] = hrc.STATUS_TEXT["idle"]
            self._page_ready = False
            self._last_model: dict = {}
            self._table = self

            self.setAccessibleName(ACCESSIBLE_NAME)
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)
            self._web = QWebEngineView(self)
            self._web_page = HistoryTabPage(self)
            self._web.setPage(self._web_page)
            self._web.loadFinished.connect(self._on_load_finished)
            self._web.setHtml(tab_html())
            layout.addWidget(self._web, 1)

        # -- the table host the render path pushes through ---------------

        @property
        def page_ready(self) -> bool:
            """True once ``_on_load_finished`` has seen a successful load."""
            return self._page_ready

        def model(self) -> dict:
            """A copy of the last model pushed, empty before the first push."""
            return dict(self._last_model)

        def set_model(self, model: dict) -> None:
            """Hold ``model`` and push it when the page is ready."""
            self._last_model = model
            if self._page_ready:
                self._run(push_script(model))

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
            """Apply one request from the page and settle its promise."""
            try:
                request = json.loads(payload)
            except ValueError:
                logger.warning("History page sent a call that is not JSON")
                return
            self._apply_request(request.get("params") or {})
            self._run(resolve_script(request.get("id")))

        def run_action(self, payload: str) -> None:
            """Run the Refresh or the Export the page cannot answer itself."""
            try:
                key = str(json.loads(payload).get("key") or "")
            except ValueError:
                logger.warning("History page sent an action that is not JSON")
                return
            if key == "refresh":
                self.refresh()
            elif key == "export":
                self._export_csv()

        # -- the state the Qt controls used to hold ----------------------

        def _set_filter_state(self, filters) -> None:
            """Hold ``filters`` as the five values the page draws."""
            self._from_ts = int(filters.from_ts)
            self._to_ts = int(filters.to_ts)
            self._to_default_ts = int(filters.to_ts)
            self._exchange = str(filters.exchange)
            self._symbol = str(filters.symbol)
            self._side = str(filters.side)

        def _current_filters(self):
            """The five filter values the page last reported."""
            return hrc.HistoryFilters(
                from_ts=int(self._from_ts),
                to_ts=int(self._to_ts),
                exchange=self._exchange,
                symbol=self._symbol,
                side=self._side,
            )

        def _since_ts(self) -> float:
            """The From bound in unix seconds."""
            return float(self._from_ts)

        def _to_bound_ts(self) -> int:
            """The To bound, following the clock while the operator leaves it."""
            import time

            if self._to_ts != self._to_default_ts:
                return int(self._to_ts)
            now = int(time.time())
            if now > self._to_ts:
                self._to_ts = now
                self._to_default_ts = now
            return int(self._to_default_ts)

        def _set_status(self, text: str) -> None:
            """Show ``text`` where the summary line goes."""
            self._status = text
            self.set_model(self._build_model())

        def _set_fetching(self, fetching: bool) -> None:
            """Show the busy bar and refuse Refresh while a fetch is in flight."""
            self._fetch_in_flight = fetching
            if not fetching:
                self._status = None
            self.set_model(self._build_model())

        def _filter_options(self) -> dict:
            """The exchange and symbol values the filter bar offers now."""
            return {"exchange": set(self._exchanges), "symbol": set(self._symbols)}

        def _set_filter_options(self, exchanges: list, symbols: list) -> None:
            """Hold the two choice lists the filter bar draws."""
            self._exchanges = list(exchanges)
            self._symbols = list(symbols)

        def _reset_filter_values(self) -> None:
            """Return the five filters to the values the tab opens on."""
            self._set_filter_state(hrc.default_filters())

        def _build_model(self) -> dict:
            """The whole tab as one payload, chrome and rows together."""
            return surface.build_view_model(
                self._all_trades,
                self._current_filters(),
                self._page,
                self._bot_manager,
                last_fetched_ts=self._last_fetched_ts,
                fetching=self._fetch_in_flight,
                status=self._status,
                gate_index=self._page_gate_index,
                voting_index=self._page_voting_index,
            )

        def _paint_chrome(self, total: int, max_page: int) -> None:
            """Drop the status line so the summary the model carries shows.

            The page counter and the two pager buttons ride in that model.
            """
            del total, max_page
            if self._status is not None:
                self._status = None
                self.set_model(self._build_model())

        # -- internals ----------------------------------------------------

        def _apply_request(self, params: dict) -> None:
            """Take the page's action, filters and page number."""
            action = str(params.get("action") or "")
            if action == "reset":
                self._reset_filters()
                return
            supplied = params.get("filters") or {}
            if supplied:
                self._adopt_filters(supplied)
            if action in ("prev", "next"):
                self._page = int(params.get("page") or 0)
                self._render_page()
                return
            self._apply_filters()

        def _adopt_filters(self, supplied: dict) -> None:
            """Take whichever of the five filter values ``supplied`` names."""
            values = self._current_filters().as_dict()
            values.update({key: supplied[key] for key in values if key in supplied})
            self._from_ts = int(values["from_ts"])
            self._to_ts = int(values["to_ts"])
            self._exchange = str(values["exchange"])
            self._symbol = str(values["symbol"])
            self._side = str(values["side"])

        def _run(self, script: str) -> None:
            self._web.page().runJavaScript(script)

        def _on_load_finished(self, ok: bool) -> None:
            self._page_ready = bool(ok)
            if not ok:
                logger.warning("React History tab page failed to load")
                return
            self.set_model(self._last_model or self._build_model())
