# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
"""The Sim tab drawn by React inside ``QWebEngineView``.

``SimulatorTabReact`` answers the same calls ``SimulatorTabQt`` answers --
``model``, ``layer``, ``tablet_key``, ``flip_layer`` and ``refresh`` -- and
pushes one ``simulator_tab_surface`` model into ``simulator_tab.js``, so both
sides place the surface's own points. ``SimulatorTabPage`` carries the page's
flip and tablet presses back to ``run_action``.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from ..simulator.tablet_source import TabletSource
from .main_tabs import simulator_tab_surface as surface
from .react_history_panel import page_html

try:
    from PySide6.QtWebEngineCore import QWebEnginePage
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWidgets import QVBoxLayout, QWidget

    _HAS_WEBENGINE = True
except ImportError:
    # Without WebEngine, SimulatorTabReact is never defined and its import
    # fails by name.
    _HAS_WEBENGINE = False

logger = logging.getLogger("acervator.gui.react_simulator_tab")

ACTION_PREFIX = "acervator-act:"

#: The element ``simulator_tab.js`` draws the tab into.
TAB_ROOT_ID = "tab-root"

ACCESSIBLE_NAME = "Sim"

TAB_STYLE_ASSETS: tuple[str, ...] = ()

#: The scripts the page carries. Order is load order.
TAB_SCRIPT_ASSETS: tuple[str, ...] = (
    "vendor/react.production.min.js",
    "vendor/react-dom.production.min.js",
    "simulator_tab.js",
)

TAB_BODY = f'<div id="{TAB_ROOT_ID}"></div>'

FLIP_ACTION = "flip_layer"
TABLET_ACTION = "choose_tablet"
MODE_ACTION = "choose_mode"
PORTFOLIO_ACTION = surface.CHOOSE_PORTFOLIO_ACTION
SPAN_ACTION = surface.CHOOSE_SPAN_ACTION
PRIVACY_ACTION = "toggle_privacy"
IMPORT_LIVE_FLEET_ACTION = surface.IMPORT_LIVE_FLEET_ACTION
GENERATE_FROM_YTD_ACTION = surface.GENERATE_FROM_YTD_ACTION
CREATE_NEW_BOTS_ACTION = surface.CREATE_NEW_BOTS_ACTION
RUN_PORTFOLIO_ACTION = surface.RUN_PORTFOLIO_ACTION
RUN_EVERY_PORTFOLIO_ACTION = surface.RUN_EVERY_PORTFOLIO_ACTION

#: The bridge this host answers. The Electron shell binds ``window.acervator``
#: in its own preload, so this source is never a file under ``src/gui/web``.
HOST_SCRIPT = """(function (global) {
  "use strict";

  global.acervator = {
    call: function () {
      return Promise.resolve(null);
    }
  };

  global.acervatorSimulatorTabDrawn = function () {
    return document.getElementById("%(tab)s") !== null;
  };
})(window);""" % {
    "tab": TAB_ROOT_ID,
}


def tab_html(theme: str = "cyberpunk_dark") -> str:
    """The whole tab page as one string, with no network fetch."""
    return page_html(
        TAB_STYLE_ASSETS, TAB_SCRIPT_ASSETS, TAB_BODY, theme, (HOST_SCRIPT,)
    )


def push_script(model: dict) -> str:
    """The one JS statement that hands ``model`` to the page and redraws it.

    ``ensure_ascii=True`` escapes U+2028 and U+2029, which are legal inside a
    JSON string and are JavaScript line terminators.
    """
    body = json.dumps(model, ensure_ascii=True)
    return (
        "window.acervatorSetSimulatorTab("
        + body
        + ");window.acervatorSimulatorTab.renderTab("
        + 'document.getElementById("'
        + TAB_ROOT_ID
        + '"), '
        + body
        + ");"
    )


if _HAS_WEBENGINE:

    class SimulatorTabPage(QWebEnginePage):
        """Routes the page's ``acervator-act:`` console lines to its owner."""

        def __init__(self, owner) -> None:
            """Hold ``owner`` as the widget that answers the page."""
            super().__init__(owner)
            self._owner = owner

        def javaScriptConsoleMessage(self, level, message, line, source) -> None:
            """Hand an action to the owner and drop every other line."""
            del level, line, source
            if message.startswith(ACTION_PREFIX):
                self._owner.run_action(message[len(ACTION_PREFIX) :])

    class SimulatorTabReact(QWidget):
        """The Sim tab's clone, drawn by ``simulator_tab.js``."""

        def __init__(
            self,
            source: Optional[TabletSource] = None,
            parent: Optional[QWidget] = None,
            theme: str = "cyberpunk_dark",
        ) -> None:
            """Load the page; the first successful load draws the model."""
            super().__init__(parent)
            self.setAccessibleName(ACCESSIBLE_NAME)
            self._source = (
                source if source is not None else TabletSource(surface.TABLET_ROOT)
            )
            self._layer = surface.LAYER_INDICATORS
            self._mode = surface.MODE_VALIDATION
            self._tablet_key = ""
            self._model: dict = {}
            self._validation: Optional[dict] = None
            self._back_test: Optional[dict] = None
            self._battery: Optional[dict] = None
            self._portfolio = surface.DEFAULT_PORTFOLIO
            self._span = surface.DEFAULT_SPAN
            self._page_ready = False
            self._theme = theme
            self._web: Optional[QWebEngineView] = None
            self._layout = QVBoxLayout(self)
            self._layout.setContentsMargins(0, 0, 0, 0)
            self._layout.setSpacing(0)

        def showEvent(self, event) -> None:  # noqa: N802
            """Build the web view the first time the tab is shown."""
            super().showEvent(event)
            self.build_panel()

        def build_panel(self) -> None:
            """Create the tab's web view and load its page, once."""
            if self._web is not None:
                return
            self._web = QWebEngineView(self)
            self._web_page = SimulatorTabPage(self)
            self._web.setPage(self._web_page)
            self._web.loadFinished.connect(self._on_load_finished)
            self._web.setHtml(tab_html(self._theme))
            self._layout.addWidget(self._web, 1)

        # -- what the window reads --------------------------------------

        @property
        def page_ready(self) -> bool:
            """True once ``_on_load_finished`` has seen a successful load."""
            return self._page_ready

        def panel_view(self):
            """The web view the tab draws in."""
            return self._web

        def model(self) -> dict:
            """A copy of the model last pushed, empty before the first push."""
            return dict(self._model)

        def layer(self) -> str:
            """The layer the page is showing, ``indicators`` or ``playback``."""
            return self._layer

        def tablet_key(self) -> str:
            """The key of the tablet the windows are drawn from."""
            found = self._model.get("tablet")
            return str(found["key"]) if found else ""

        # -- what the operator presses ----------------------------------

        def flip_layer(self) -> str:
            """Swap the page between the panel layer and the chart layer."""
            self._layer = (
                surface.LAYER_PLAYBACK
                if self._layer == surface.LAYER_INDICATORS
                else surface.LAYER_INDICATORS
            )
            self.refresh()
            return self._layer

        def choose_tablet(self, key: str) -> str:
            """Draw the tablet ``key`` names."""
            self._tablet_key = str(key or "")
            self.refresh()
            return self._tablet_key

        def toggle_privacy(self) -> bool:
            """Flip every registered privacy field and redraw the button."""
            masked = surface.toggle_privacy()
            self.refresh()
            return masked

        def choose_mode(self, mode: str) -> str:
            """Show ``mode``'s buttons and result pane."""
            self._mode = mode if mode in surface.MODES else surface.MODE_VALIDATION
            self.refresh()
            return self._mode

        def mode(self) -> str:
            """The mode the page is showing, one of ``surface.MODES``."""
            return self._mode

        def import_live_fleet(self) -> dict:
            """Clone the live fleet from bot_state and validate it."""
            return self.run_validation(IMPORT_LIVE_FLEET_ACTION)

        def generate_from_ytd(self) -> dict:
            """Build a fleet from the YTD trade files and validate it."""
            return self.run_validation(GENERATE_FROM_YTD_ACTION)

        def create_new_bots(self) -> dict:
            """Make one simulated bot on the chosen tablet and back test it."""
            return self.run_back_test(CREATE_NEW_BOTS_ACTION)

        def run_validation(self, origin: str, exchange_id: str = "") -> dict:
            """Run ``origin``'s fleet against the record and redraw the page."""
            self._validation = surface.run_validation(origin, exchange_id)
            self.refresh()
            return dict(self._validation)

        def run_back_test(self, origin: str, exchange_id: str = "") -> dict:
            """Walk ``origin``'s fleet over the Stone Tablets and redraw the
            page."""
            self._back_test = surface.run_back_test(
                origin,
                exchange_id,
                surface.new_bot_specs(
                    surface.chosen_entry(self._source, self._tablet_key)
                ),
            )
            self.refresh()
            return dict(self._back_test)

        def validation(self) -> dict:
            """The Validation payload the page was last drawn from."""
            return dict(self._model.get("validation") or {})

        def back_test(self) -> dict:
            """The Back Test payload the page was last drawn from."""
            return dict(self._model.get("back_test") or {})

        def battery(self) -> dict:
            """The Portfolio Battery payload the page was last drawn from."""
            return dict(self._model.get("battery") or {})

        def choose_portfolio(self, name: str) -> str:
            """Draw the portfolio ``name`` names on the next battery press."""
            self._portfolio = str(name or surface.DEFAULT_PORTFOLIO)
            self.refresh()
            return self._portfolio

        def choose_span(self, span: str) -> str:
            """Read the span ``span`` names on the next battery press."""
            self._span = str(span or surface.DEFAULT_SPAN)
            self.refresh()
            return self._span

        def run_portfolio(self) -> dict:
            """Walk the chosen portfolio over the RA-StoneTablets."""
            return self.run_battery(RUN_PORTFOLIO_ACTION)

        def run_every_portfolio(self) -> dict:
            """Walk every portfolio over the RA-StoneTablets."""
            return self.run_battery(RUN_EVERY_PORTFOLIO_ACTION)

        def run_battery(self, origin: str) -> dict:
            """Run ``origin`` over the chosen span and redraw the page."""
            self._battery = surface.run_battery(origin, self._portfolio, self._span)
            self.refresh()
            return dict(self._battery)

        def run_action(self, payload: str) -> None:
            """Run the press the page reported: flip, privacy, tablet, mode or
            fleet."""
            try:
                asked = json.loads(payload)
            except ValueError:
                logger.warning("The Sim page sent an action that is not JSON")
                return
            key = str(asked.get("key") or "")
            if key == FLIP_ACTION:
                self.flip_layer()
            elif key == PRIVACY_ACTION:
                self.toggle_privacy()
            elif key == TABLET_ACTION:
                self.choose_tablet(str(asked.get("value") or ""))
            elif key == MODE_ACTION:
                self.choose_mode(str(asked.get("value") or ""))
            elif key == PORTFOLIO_ACTION:
                self.choose_portfolio(str(asked.get("value") or ""))
            elif key == SPAN_ACTION:
                self.choose_span(str(asked.get("value") or ""))
            elif key in (RUN_PORTFOLIO_ACTION, RUN_EVERY_PORTFOLIO_ACTION):
                self.run_battery(key)
            elif key == CREATE_NEW_BOTS_ACTION:
                self.run_back_test(key)
            elif key == IMPORT_LIVE_FLEET_ACTION:
                if self._mode == surface.MODE_BACK_TEST:
                    self.run_back_test(key)
                else:
                    self.run_validation(key)
            elif key == GENERATE_FROM_YTD_ACTION:
                self.run_validation(key)

        # -- drawing ----------------------------------------------------

        def refresh(self) -> dict:
            """Re-read the tablet and push the new model to the page."""
            self._model = surface.build_view_model(
                self._source,
                self._tablet_key,
                self._layer,
                self._validation,
                self._mode,
                self._back_test,
                self._battery,
            )
            if self._page_ready and self._web is not None:
                self._web.page().runJavaScript(push_script(self._model))
            return self._model

        def _on_load_finished(self, ok: bool) -> None:
            self._page_ready = bool(ok)
            if not ok:
                logger.warning("The React Sim tab page failed to load")
                return
            self.refresh()
