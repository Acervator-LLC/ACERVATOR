# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
"""The Paper tab drawn by React inside ``QWebEngineView``.

``PaperTraderTabReact`` answers the same calls ``PaperTraderTabQt`` answers --
``model``, ``symbol``, ``run_state``, ``import_live_fleet``, ``start_run``,
``stop_run``, ``advance_once`` and ``refresh`` -- and pushes one
``paper_trader_tab_surface`` model into ``paper_trader_tab.js``, so both sides
draw the surface's own values. ``PaperTraderTabPage`` carries the page's
presses back to ``run_action``.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from ..paper.live_feed_source import LiveFeedSource
from .main_tabs import paper_trader_tab_surface as surface
from .react_history_panel import page_html

try:
    from PySide6.QtCore import QTimer
    from PySide6.QtWebEngineCore import QWebEnginePage
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWidgets import QVBoxLayout, QWidget

    _HAS_WEBENGINE = True
except ImportError:
    # Without WebEngine, PaperTraderTabReact is never defined and its import
    # fails by name.
    _HAS_WEBENGINE = False

logger = logging.getLogger("acervator.gui.react_paper_trader_tab")

ACTION_PREFIX = "acervator-act:"

#: The element ``paper_trader_tab.js`` draws the tab into.
TAB_ROOT_ID = "tab-root"

ACCESSIBLE_NAME = "Paper"

TAB_STYLE_ASSETS: tuple[str, ...] = ()

#: The scripts the page carries. Order is load order.
TAB_SCRIPT_ASSETS: tuple[str, ...] = (
    "vendor/react.production.min.js",
    "vendor/react-dom.production.min.js",
    "paper_trader_tab.js",
)

TAB_BODY = f'<div id="{TAB_ROOT_ID}"></div>'

SYMBOL_ACTION = surface.CHOOSE_SYMBOL_ACTION
PRIVACY_ACTION = surface.TOGGLE_PRIVACY_ACTION
IMPORT_LIVE_FLEET_ACTION = surface.IMPORT_LIVE_FLEET_ACTION
START_RUN_ACTION = surface.START_RUN_ACTION
STOP_RUN_ACTION = surface.STOP_RUN_ACTION

#: The bridge this host answers. The Electron shell binds ``window.acervator``
#: in its own preload, so this source is never a file under ``src/gui/web``.
HOST_SCRIPT = """(function (global) {
  "use strict";

  global.acervator = {
    call: function () {
      return Promise.resolve(null);
    }
  };

  global.acervatorPaperTraderTabDrawn = function () {
    return document.getElementById("%(tab)s") !== null;
  };
})(window);""" % {
    "tab": TAB_ROOT_ID,
}


def tab_html(theme: object = None) -> str:
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
        "window.acervatorSetPaperTraderTab("
        + body
        + ");window.acervatorPaperTraderTab.renderTab("
        + 'document.getElementById("'
        + TAB_ROOT_ID
        + '"), '
        + body
        + ");"
    )


if _HAS_WEBENGINE:

    class PaperTraderTabPage(QWebEnginePage):
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

    class PaperTraderTabReact(QWidget):
        """The Paper tab's clone, drawn by ``paper_trader_tab.js``."""

        def __init__(
            self,
            feed: Optional[LiveFeedSource] = None,
            parent: Optional[QWidget] = None,
            theme: object = None,
        ) -> None:
            """Load the page; the first successful load draws the model."""
            super().__init__(parent)
            self.setAccessibleName(ACCESSIBLE_NAME)
            self._feed = feed if feed is not None else LiveFeedSource()
            self._bots: list = []
            self._run = None
            self._symbol = ""
            self._cursor = 0
            self._model: dict = {}
            self._page_ready = False
            self._theme = theme
            self._web: Optional[QWebEngineView] = None
            self._tick_timer = QTimer(self)
            self._tick_timer.timeout.connect(self.advance_once)
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
            self._web_page = PaperTraderTabPage(self)
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

        def symbol(self) -> str:
            """The market the Indicator Voting Panel is reading."""
            return str(self._model.get("symbol") or "")

        def run_state(self) -> str:
            """The run's state, one of ``paper_run.RUN_STATES``."""
            return str(self._model.get("run", {}).get("state") or "")

        def feed(self) -> LiveFeedSource:
            """The one data path this tab reads."""
            return self._feed

        # -- what the operator presses ----------------------------------

        def import_live_fleet(self) -> int:
            """Read the fleet from ``bot_state.json`` and draw it."""
            self._bots = surface.live_fleet()
            self.refresh()
            return len(self._bots)

        def toggle_run(self) -> str:
            """Start the run when none is running, otherwise stop it."""
            if self._run is not None and self._run.running:
                return self.stop_run()
            return self.start_run()

        def start_run(self) -> str:
            """Open the run and tick one bot per timer fire from now."""
            if not self._bots:
                self._bots = surface.live_fleet()
            self._run = surface.start_run(self._bots)
            self._cursor = 0
            self.advance_once()
            self._tick_timer.start(surface.tick_interval_ms(self._run, self._symbol))
            return self._run.state

        def stop_run(self) -> str:
            """Stop the wall-clock timer; the balances and trades stay
            readable."""
            self._tick_timer.stop()
            if self._run is not None:
                surface.stop_run(self._run)
            self.refresh()
            return "" if self._run is None else self._run.state

        def advance_once(self) -> list:
            """Tick the next open bot against its newest live window."""
            if self._run is None or not self._run.running or not self._run.bots:
                return []
            chosen = self._run.bots[self._cursor % len(self._run.bots)].bot_id
            self._cursor += 1
            made = surface.advance_run(self._run, self._feed, chosen)
            self.refresh()
            return made

        def choose_symbol(self, symbol: str) -> str:
            """Draw the market ``symbol`` names in the Indicator Voting Panel."""
            self._symbol = str(symbol or "")
            self.refresh()
            return self._symbol

        def toggle_privacy(self) -> bool:
            """Flip every registered privacy field and redraw the button."""
            masked = surface.toggle_privacy()
            self.refresh()
            return masked

        def run_action(self, payload: str) -> None:
            """Run the press the page reported: privacy, market, fleet or run."""
            try:
                asked = json.loads(payload)
            except ValueError:
                logger.warning("The Paper page sent an action that is not JSON")
                return
            key = str(asked.get("key") or "")
            if key == PRIVACY_ACTION:
                self.toggle_privacy()
            elif key == SYMBOL_ACTION:
                self.choose_symbol(str(asked.get("value") or ""))
            elif key == IMPORT_LIVE_FLEET_ACTION:
                self.import_live_fleet()
            elif key == START_RUN_ACTION:
                self.start_run()
            elif key == STOP_RUN_ACTION:
                self.stop_run()

        # -- drawing ----------------------------------------------------

        def refresh(self) -> dict:
            """Re-read the live feed and push the new model to the page."""
            self._model = surface.build_view_model(
                self._feed, self._bots, self._run, self._symbol
            )
            if self._page_ready and self._web is not None:
                self._web.page().runJavaScript(push_script(self._model))
            return self._model

        def closeEvent(self, event) -> None:  # noqa: N802
            """Stop the wall-clock timer before the tab goes away."""
            self._tick_timer.stop()
            super().closeEvent(event)

        def _on_load_finished(self, ok: bool) -> None:
            self._page_ready = bool(ok)
            if not ok:
                logger.warning("The React Paper tab page failed to load")
                return
            self.refresh()
