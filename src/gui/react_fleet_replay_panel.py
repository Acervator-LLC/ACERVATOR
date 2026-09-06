# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
"""The Fleet Replay panel drawn by React inside ``QWebEngineView``.

``FleetReplayReactPanel`` inherits ``FleetReplayPanel``, so Load, Fetch YTD,
Reset, Start, Stop and both timers are the same code. It answers the panel's
accessors against ``fleet_replay_panel_surface.FleetReplayPanelModel``, and
``FleetReplayPage`` carries the page's console lines to ``run_action``.
"""

from __future__ import annotations

import json
import logging

from .main_tabs import fleet_replay_panel_surface as surface
from .react_history_panel import STYLE_SOURCE_ASSETS, page_html
from .simulator_tab.fleet.fleet_replay_panel import _HAS_QT, FleetReplayPanel

try:
    from PySide6.QtWebEngineCore import QWebEnginePage
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWidgets import QVBoxLayout

    _HAS_WEBENGINE = True
except ImportError:
    # Without WebEngine the class is never defined and its import fails by name.
    _HAS_WEBENGINE = False

logger = logging.getLogger("acervator.gui.react_fleet_replay_panel")

ACTION_PREFIX = "acervator-fleet-act:"

#: The element ``fleet_replay_panel.js`` draws the panel into.
PANEL_ROOT_ID = "fleet-replay-root"

ACCESSIBLE_NAME = "React Fleet Replay Panel"

#: The key the page names each press under.
ACTION_KEY = "action"

#: The key the Full evaluation switch reports its new state under.
FULL_EVALUATION_KEY = "full_evaluation"

#: The style sheet the page carries.
PANEL_STYLE_ASSETS: tuple[str, ...] = ("fleet_replay_panel.css",)

#: The scripts the page carries. Order is load order, and the style source
#: comes before ``fleet_replay_panel.js``, which parses its sheets with it.
PANEL_SCRIPT_ASSETS: tuple[str, ...] = (
    ("vendor/react.production.min.js", "vendor/react-dom.production.min.js")
    + STYLE_SOURCE_ASSETS
    + ("fleet_replay_panel.js",)
)

PANEL_BODY = f'<div id="{PANEL_ROOT_ID}"></div>'

#: The JS expression that reads the status line the browser drew.
STATUS_TEXT_JS = (
    "(document.querySelector('[data-part=\"status\"]')"
    " || {textContent: null}).textContent"
)

#: The JS expression that reads the progress line the browser drew.
PROGRESS_TEXT_JS = (
    "(document.querySelector('[data-part=\"progress\"]')"
    " || {textContent: null}).textContent"
)

#: The JS expression that counts the fleet rows the browser drew.
ROW_COUNT_JS = "document.querySelectorAll('[data-part=\"body-row\"]').length"

#: The JS expression that reads which buttons the browser drew live.
BUTTON_STATE_JS = (
    "Array.from(document.querySelectorAll('[data-part=\"button\"]'))"
    ".map(function (n) { return n.textContent + '/' + String(!n.disabled); })"
)

HOST_SCRIPT = """(function (global) {
  "use strict";

  global.acervator = {
    call: function (method, params) {
      console.log("%(prefix)s" + JSON.stringify(params));
      return Promise.resolve(null);
    }
  };

  global.acervatorFleetReplayDraw = function (model) {
    global.acervatorSetFleetReplay(model);
    return global.acervatorFleetReplay.renderPanel(
      document.getElementById("%(root)s"),
      null
    ) !== null;
  };
})(window);""" % {"prefix": ACTION_PREFIX, "root": PANEL_ROOT_ID}


def panel_html(theme: str = "cyberpunk_dark") -> str:
    """The whole panel page as one string, with no network fetch."""
    return page_html(
        PANEL_STYLE_ASSETS, PANEL_SCRIPT_ASSETS, PANEL_BODY, theme, (HOST_SCRIPT,)
    )


def draw_script(model: dict) -> str:
    """The one JS statement that hands ``model`` to the page."""
    return (
        "window.acervatorFleetReplayDraw(" + json.dumps(model, ensure_ascii=True) + ");"
    )


if _HAS_QT and _HAS_WEBENGINE:

    class FleetReplayPage(QWebEnginePage):
        """Routes the page's ``acervator-fleet-act`` lines to its owner."""

        def __init__(self, owner) -> None:
            """Hold ``owner`` as the widget that answers the page."""
            super().__init__(owner)
            self._owner = owner

        def javaScriptConsoleMessage(self, level, message, line, source) -> None:
            """Hand an action to the owner and drop every other line."""
            del level, line, source
            if message.startswith(ACTION_PREFIX):
                self._owner.run_action(message[len(ACTION_PREFIX) :])

    class FleetReplayReactPanel(FleetReplayPanel):
        """Fleet Replay with its header, buttons, table and lines drawn by React."""

        #: The method name each step in ``surface.ACTIONS`` runs. Looked up on
        #: the instance, so an override is honoured.
        STEP_RUNNERS = {
            "load": "_on_load_clicked",
            "fetch_ytd": "_on_fetch_ytd_clicked",
            "reset": "_on_reset_clicked",
            "start": "_on_start_clicked",
            "stop": "_on_stop_clicked",
            "refresh_progress": "_refresh_progress",
            "drain": "_drain_visual_snapshot",
        }

        def _build_ui(self) -> None:
            """Build the one web view the whole panel is drawn in."""
            self._panel = surface.FleetReplayPanelModel()
            self._page_ready = False
            self._last_model: dict = {}

            self.setAccessibleName(ACCESSIBLE_NAME)
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)
            self._web = QWebEngineView(self)
            self._web_page = FleetReplayPage(self)
            self._web.setPage(self._web_page)
            self._web.loadFinished.connect(self._on_load_finished)
            self._web.setHtml(panel_html())
            layout.addWidget(self._web, 1)

        # -- what the page is drawn from ----------------------------------

        @property
        def page_ready(self) -> bool:
            """True once ``_on_load_finished`` has seen a successful load."""
            return self._page_ready

        def model(self) -> dict:
            """A copy of the last panel payload pushed."""
            return dict(self._last_model)

        def build_model(self) -> dict:
            """The whole panel as one payload the page is drawn from."""
            return surface.build_view_model(self._panel)

        def push(self) -> None:
            """Send the panel payload to the page."""
            self._last_model = self.build_model()
            if self._page_ready:
                self._web.page().runJavaScript(draw_script(self._last_model))

        def read(self, script: str, callback) -> bool:
            """Run ``script`` and hand what the page answered to ``callback``.

            Returns False and calls nothing while the page is not ready.
            """
            if not self._page_ready:
                return False
            self._web.page().runJavaScript(script, callback)
            return True

        # -- what the page reports back -----------------------------------

        def run_action(self, payload: str) -> None:
            """Run one press the page reported against the panel."""
            try:
                request = json.loads(payload)
            except ValueError:
                logger.warning("Fleet Replay page sent a call that is not JSON")
                return
            if not isinstance(request, dict):
                logger.warning("Fleet Replay page sent a call that is not an object")
                return
            if FULL_EVALUATION_KEY in request:
                self._panel.full_evaluation = bool(request[FULL_EVALUATION_KEY])
                self.push()
            step = surface.ACTIONS.get(str(request.get(ACTION_KEY) or ""))
            named = self.STEP_RUNNERS.get(step)
            if named is not None:
                getattr(self, named)()

        # -- the controls the inherited logic writes through ---------------

        def _set_status(self, text: str) -> None:
            """Show ``text`` on the status line."""
            self._panel.status_text = text
            self.push()

        def _set_progress(self, text: str) -> None:
            """Show ``text`` on the progress line."""
            self._panel.progress_text = text
            self.push()

        def _set_start_enabled(self, enabled: bool) -> None:
            """Let the operator press Start Replay, or refuse."""
            self._panel.start_enabled = bool(enabled)
            self.push()

        def _set_stop_enabled(self, enabled: bool) -> None:
            """Let the operator press Stop, or refuse."""
            self._panel.stop_enabled = bool(enabled)
            self.push()

        def _set_fetch_enabled(self, enabled: bool) -> None:
            """Let the operator press Fetch YTD, or refuse."""
            self._panel.fetch_enabled = bool(enabled)
            self.push()

        def _full_evaluation(self) -> bool:
            """Whether the Full evaluation switch is on."""
            return bool(self._panel.full_evaluation)

        def _set_fleet_row_count(self, count: int) -> None:
            """Declare ``count`` fleet rows, dropping every row past it."""
            rows = self._panel.rows
            wanted = int(count)
            del rows[wanted:]
            while len(rows) < wanted:
                rows.append(["" for _ in surface.COLUMNS])
            self.push()

        def _set_fleet_row(self, at: int, cells: list) -> None:
            """Fill fleet row ``at`` with ``cells``, left to right."""
            row = self._panel.rows[at]
            for column, cell in enumerate(cells):
                row[column] = str(cell)
            self.push()

        def _fleet_row_count(self) -> int:
            """How many fleet rows the panel is showing."""
            return len(self._panel.rows)

        def _fleet_row_symbol(self, at: int) -> str:
            """The symbol on fleet row ``at``, or the empty string."""
            return str(self._panel.rows[at][self.SYMBOL_COLUMN])

        def _fleet_row_trades(self, at: int) -> str:
            """The trade count shown on fleet row ``at``, or the empty string."""
            return str(self._panel.rows[at][self.TRADES_COLUMN])

        def _set_fleet_row_trades(self, at: int, count: str) -> None:
            """Show ``count`` in the trades column of fleet row ``at``."""
            self._panel.rows[at][self.TRADES_COLUMN] = str(count)
            self.push()

        # -- internals ------------------------------------------------------

        def _on_load_finished(self, ok: bool) -> None:
            self._page_ready = bool(ok)
            if not ok:
                logger.warning("React Fleet Replay page failed to load")
                return
            self.push()
