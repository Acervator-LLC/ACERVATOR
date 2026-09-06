# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
"""The Nuclear Mode panel drawn by React inside ``QWebEngineView``.

``NuclearModeReactPanel`` replaces every Qt control ``NuclearModePanel`` builds
and inherits its fleet preview, its Start, its Stop and its status tick.
``NuclearModePage`` carries the page's console lines to ``run_action``, which
is where the Reload, Start, Stop and timer presses arrive.
"""

from __future__ import annotations

import json
import logging

from .main_tabs import nuclear_mode_panel_surface as surface
from .react_history_panel import STYLE_SOURCE_ASSETS, page_html
from .simulator_tab.nuclear_mode_panel import NuclearModePanel

try:
    from PySide6.QtWebEngineCore import QWebEnginePage
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWidgets import QVBoxLayout

    _HAS_WEBENGINE = True
except ImportError:
    # Without WebEngine the class is never defined and its import fails by name.
    _HAS_WEBENGINE = False

logger = logging.getLogger("acervator.gui.react_nuclear_mode_panel")

ACTION_PREFIX = "acervator-nuclear-act:"

#: The element ``nuclear_mode_panel.js`` draws the panel into.
PANEL_ROOT_ID = "nuclear-panel-root"

ACCESSIBLE_NAME = "React Nuclear Mode Panel"

#: The key the page names each press under.
ACTION_KEY = "action"

RELOAD_ACTION = "reload_button_clicked"
START_ACTION = "start_button_clicked"
STOP_ACTION = "stop_button_clicked"
TICK_ACTION = "refresh_timer_tick"

#: The style sheet the page carries.
PANEL_STYLE_ASSETS: tuple[str, ...] = ("nuclear_mode_panel.css",)

#: The scripts the page carries. Order is load order, and the style source
#: comes before ``nuclear_mode_panel.js``, which parses its sheets with it.
PANEL_SCRIPT_ASSETS: tuple[str, ...] = (
    ("vendor/react.production.min.js", "vendor/react-dom.production.min.js")
    + STYLE_SOURCE_ASSETS
    + ("nuclear_mode_panel.js",)
)

PANEL_BODY = f'<div id="{PANEL_ROOT_ID}"></div>'

#: The JS expression that reads the live-status values the browser drew.
STATUS_VALUES_JS = (
    "Array.from(document.querySelectorAll('[data-part=\"cell-value\"]'))"
    ".map(function (n) { return n.textContent; })"
)

#: The JS expression that reads the fleet readout the browser drew.
FLEET_DETAIL_JS = (
    '(document.querySelector(\'[data-part="field"][data-name="detail"]\')'
    " || {}).textContent"
)

#: The JS expression that reads which buttons the browser drew live.
BUTTON_STATE_JS = (
    "Array.from(document.querySelectorAll('[data-part=\"button\"]'))"
    ".map(function (n) { return n.getAttribute('data-name')"
    " + '=' + n.getAttribute('data-enabled'); })"
)

HOST_SCRIPT = """(function (global) {
  "use strict";

  global.acervator = {
    call: function (method, params) {
      console.log("%(prefix)s" + JSON.stringify(params));
      return Promise.resolve(null);
    }
  };

  global.acervatorNuclearDraw = function (model) {
    global.acervatorSetNuclearPanel(model);
    return global.acervatorNuclearPanel.renderPanel(
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
    return "window.acervatorNuclearDraw(" + json.dumps(model, ensure_ascii=True) + ");"


if _HAS_WEBENGINE:

    class NuclearModePage(QWebEnginePage):
        """Routes the page's ``acervator-nuclear-act`` lines to its owner."""

        def __init__(self, owner) -> None:
            """Hold ``owner`` as the widget that answers the page."""
            super().__init__(owner)
            self._owner = owner

        def javaScriptConsoleMessage(self, level, message, line, source) -> None:
            """Hand an action to the owner and drop every other line."""
            del level, line, source
            if message.startswith(ACTION_PREFIX):
                self._owner.run_action(message[len(ACTION_PREFIX) :])

    class NuclearModeReactPanel(NuclearModePanel):
        """Nuclear Mode with its cards, settings and status grid drawn by React."""

        def _build_ui(self) -> None:
            """Build the one web view the whole panel is drawn in."""
            self._panel = surface.PanelModel(surface.PanelWorld())
            self._page_ready = False
            self._last_model: dict = {}

            self.setAccessibleName(ACCESSIBLE_NAME)
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)
            self._web = QWebEngineView(self)
            self._web_page = NuclearModePage(self)
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
            return surface.envelope(self._panel.build())

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
                logger.warning("Nuclear Mode page sent a call that is not JSON")
                return
            if not isinstance(request, dict):
                logger.warning("Nuclear Mode page sent a call that is not an object")
                return
            action = str(request.get(ACTION_KEY) or "")
            if action == RELOAD_ACTION:
                self._rescan_cache()
            elif action == START_ACTION:
                self._take_settings(request)
                self._on_start_clicked()
            elif action == STOP_ACTION:
                self._on_stop_clicked()
            elif action == TICK_ACTION:
                self._refresh_status()

        def _take_settings(self, request: dict) -> None:
            """Read the four run settings the Start press carried."""
            panel = self._panel
            if "cycle_candles" in request:
                panel.cycle_candles = int(request["cycle_candles"])
            if "max_cycles" in request:
                panel.max_cycles = int(request["max_cycles"])
            if "noise" in request:
                panel.noise_enabled = bool(request["noise"])
            if "load_oscillation" in request:
                panel.load_oscillation = bool(request["load_oscillation"])
            self.push()

        # -- the controls the inherited logic writes through ---------------

        def _set_fleet_detail(self, text: str) -> None:
            """Show ``text`` on the fleet readout row."""
            self._panel.fleet_detail = text
            self.push()

        def _set_empty_notice(self, text: str, visible: bool) -> None:
            """Show ``text`` as the empty-fleet notice, or hide the notice."""
            self._panel.empty_text = text
            self._panel.empty_visible = bool(visible)
            self.push()

        def _set_start_enabled(self, enabled: bool) -> None:
            """Let the operator press Start, or refuse."""
            self._panel.start_enabled = bool(enabled)
            self.push()

        def _set_stop_enabled(self, enabled: bool) -> None:
            """Let the operator press Stop, or refuse."""
            self._panel.stop_enabled = bool(enabled)
            self.push()

        def _set_reload_enabled(self, enabled: bool) -> None:
            """Let the operator press Reload fleet, or refuse."""
            self._panel.reload_enabled = bool(enabled)
            self.push()

        def _set_run_controls_enabled(self, enabled: bool) -> None:
            """Let the operator change the four run settings, or refuse."""
            live = bool(enabled)
            self._panel.control_enabled = {
                name: live for name in surface.RUN_CONTROL_KEYS
            }
            self.push()

        def _cycle_candles(self) -> int:
            """Candles per cycle, as the cycle-length control reads."""
            return int(self._panel.cycle_candles)

        def _max_cycles(self) -> int:
            """Cycles to stop after, as the max-cycles control reads."""
            return int(self._panel.max_cycles)

        def _noise_enabled(self) -> bool:
            """Whether the market-structure tick box is ticked."""
            return bool(self._panel.noise_enabled)

        def _load_oscillation(self) -> bool:
            """Whether the system-load tick box is ticked."""
            return bool(self._panel.load_oscillation)

        def _set_status_text(self, key: str, text: str) -> None:
            """Show ``text`` on the live-status row ``key`` names."""
            if key in self._panel.status_text:
                self._panel.status_text[key] = text
                self.push()

        def _set_timer_running(self, running: bool) -> None:
            """Run the 500 ms status tick, or stop it.

            The page owns the interval, so the tick arrives as ``TICK_ACTION``.
            """
            self._panel.timer_running = bool(running)
            self.push()

        # -- internals ------------------------------------------------------

        def _on_load_finished(self, ok: bool) -> None:
            self._page_ready = bool(ok)
            if not ok:
                logger.warning("React Nuclear Mode page failed to load")
                return
            self.push()
