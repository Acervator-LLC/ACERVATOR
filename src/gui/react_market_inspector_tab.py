# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
"""The whole Market Inspector tab drawn by React inside ``QWebEngineView``.

``MarketInspectorReactTab`` replaces every Qt control ``MarketInspectorTab``
builds and inherits its fetch cycle, its filtering and its analyzer writes.
``TopologiesPaneHost`` answers the four calls the tab makes on its right pane
and feeds ``market_inspector_topologies.js``. ``MarketInspectorPage`` carries
the page's console lines to ``run_action`` and ``run_topology_action``.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Optional

from .main_tabs import market_inspector_surface as surface
from .main_tabs import market_inspector_topologies_surface as topo_surface
from .market_inspector import _HAS_QT, MarketInspectorTab
from .react_history_panel import STYLE_SOURCE_ASSETS, page_html

try:
    from PySide6.QtWebEngineCore import QWebEnginePage
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWidgets import QVBoxLayout

    _HAS_WEBENGINE = True
except ImportError:
    # Without WebEngine the class is never defined and its import fails by name.
    _HAS_WEBENGINE = False

logger = logging.getLogger("acervator.gui.react_market_inspector")

SCREEN_PREFIX = "acervator-mi-act:"
TOPOLOGY_PREFIX = "acervator-topo-act:"

#: The element ``market_inspector.js`` draws the screen into.
SCREEN_ROOT_ID = "inspector-root"

#: The element ``market_inspector_topologies.js`` draws the right pane into.
TOPOLOGY_ROOT_ID = "topologies-root"

#: The element the preview screen is drawn into while one is open.
PREVIEW_ROOT_ID = "preview-root"

#: The slot in the screen the right pane is moved into once both are drawn.
TOPOLOGY_SLOT = "market-inspector-topologies"

#: The action key each page control reports, taken from its own part name.
REFRESH_KEY = "refresh-button"
SHOW_ACTIVE_KEY = "switch-box"
PREVIEW_KEY = "preview-button"
DISMISS_KEY = "dismiss-button"
CANCEL_KEY = "cancel-button"
ADOPT_KEY = "adopt-button"

ACCESSIBLE_NAME = "React Market Inspector Tab"

#: The style sheet the page carries.
TAB_STYLE_ASSETS: tuple[str, ...] = ("market_inspector.css",)

#: The scripts the page carries. Order is load order, and the style source
#: comes before the two screen modules, which parse their sheets with it.
TAB_SCRIPT_ASSETS: tuple[str, ...] = (
    ("vendor/react.production.min.js", "vendor/react-dom.production.min.js")
    + STYLE_SOURCE_ASSETS
    + ("market_inspector.js", "market_inspector_topologies.js")
)

#: The screen root fills the view, so the screen's own full height resolves
#: against it and the tab draws as tall as the Qt tab does.
SCREEN_ROOT_STYLE = "height:100%"

#: The pane root fills the slot it is moved into, so the pane's own full
#: height resolves against it instead of against its cards.
TOPOLOGY_ROOT_STYLE = "height:100%"

TAB_BODY = (
    f'<div id="{SCREEN_ROOT_ID}" style="{SCREEN_ROOT_STYLE}"></div>\n'
    f'<div id="{TOPOLOGY_ROOT_ID}" style="{TOPOLOGY_ROOT_STYLE}"></div>\n'
    f'<div id="{PREVIEW_ROOT_ID}" hidden></div>'
)

#: The JS expression that counts the table rows the browser drew.
ROW_COUNT_JS = "document.querySelectorAll('[data-part=\"grid-row\"]').length"

#: The bridge this host answers. The Electron shell binds its own preload,
#: so this source is never a file under ``src/gui/web``.
HOST_SCRIPT = """(function (global) {
  "use strict";

  global.acervatorMarketInspectorAction = function (key, value) {
    console.log("%(screen)s" + JSON.stringify({ key: key, value: value }));
    return null;
  };

  global.acervatorTopologiesAction = function (key, name) {
    console.log("%(topo)s" + JSON.stringify({ key: key, name: name }));
    return null;
  };

  global.acervatorMountTopologies = function () {
    var slot = document.querySelector('[data-slot="%(slot)s"]');
    var pane = document.getElementById("%(pane)s");
    if (slot !== null && pane !== null && pane.parentNode !== slot) {
      slot.appendChild(pane);
    }
    return slot !== null && pane !== null;
  };

  global.acervatorMarketInspector.renderTab(
    document.getElementById("%(screen_root)s"),
    null
  );
  global.acervatorTopologies.renderTab(
    document.getElementById("%(pane)s"),
    null
  );
})(window);""" % {
    "screen": SCREEN_PREFIX,
    "topo": TOPOLOGY_PREFIX,
    "slot": TOPOLOGY_SLOT,
    "pane": TOPOLOGY_ROOT_ID,
    "screen_root": SCREEN_ROOT_ID,
}


def tab_html(theme: str = "cyberpunk_dark") -> str:
    """The whole tab page as one string, with no network fetch."""
    return page_html(
        TAB_STYLE_ASSETS, TAB_SCRIPT_ASSETS, TAB_BODY, theme, (HOST_SCRIPT,)
    )


def screen_push_script(model: dict) -> str:
    """The JS that hands ``model`` to the screen and reseats the pane."""
    return (
        "window.acervatorMarketInspector.setTab("
        + json.dumps(model, ensure_ascii=True)
        + ");window.acervatorMountTopologies();"
    )


#: The index that empties the preview. Clearing the element instead leaves
#: React holding a tree that no longer matches it, and the next preview draws
#: nothing.
NO_PREVIEW_AT = -1


def topology_push_script(model: dict, preview_at: Optional[int]) -> str:
    """The JS that hands ``model`` to the pane and draws one preview.

    A ``preview_at`` of None hides ``PREVIEW_ROOT_ID`` and empties it.
    """
    head = (
        "window.acervatorTopologies.setTab("
        + json.dumps(model, ensure_ascii=True)
        + ");var p=document.getElementById("
        + json.dumps(PREVIEW_ROOT_ID)
        + ");"
    )
    if preview_at is None:
        return (
            head
            + "window.acervatorTopologies.renderPreview(p,"
            + json.dumps(NO_PREVIEW_AT)
            + ",null);p.hidden=true;"
        )
    return (
        head
        + "p.hidden=false;window.acervatorTopologies.renderPreview(p,"
        + json.dumps(int(preview_at))
        + ",null);"
    )


class TopologiesPaneHost:
    """The Market Inspector's right pane, drawn by React.

    Answers ``set_dismiss_store``, ``set_proposal_source``,
    ``current_proposals`` and the ``adoptRequested`` connect the tab makes,
    and holds the ``TopologiesPaneModel`` the page is drawn from.
    """

    def __init__(self) -> None:
        self.model = topo_surface.TopologiesPaneModel()
        self.adopt_handlers: list = []
        self.preview_at: Optional[int] = None

    def set_dismiss_store(self, store: Any) -> None:
        """Take the place the pane persists its dismissals in."""
        self.model.set_dismiss_store(store)

    def set_proposal_source(self, getter: Callable[[], Any]) -> None:
        """Take the callable the pane pulls its proposals from."""
        self.model.set_proposal_source(getter)

    def current_proposals(self) -> list:
        """The proposals the pane is showing."""
        return self.model.current_proposals()

    @property
    def adoptRequested(self) -> "TopologiesPaneHost":  # noqa: N802 - Qt signal name
        """The Adopt signal the tab wires the main window onto."""
        return self

    def connect(self, handler: Callable[[dict], Any]) -> None:
        """Wire one handler onto the Adopt signal."""
        self.adopt_handlers.append(handler)

    def view_model(self) -> dict:
        """The whole pane as one payload the page is drawn from."""
        return topo_surface.build_view_model(self.model)

    def act(self, key: str, name: Any) -> None:
        """Run one button press the page reported against the pane."""
        if key == REFRESH_KEY:
            self.model.refresh()
            return
        if key == PREVIEW_KEY:
            if self.model.on_preview(name) is not None:
                self.preview_at = len(self.model.previews) - 1
            return
        if key == DISMISS_KEY:
            self.model.on_dismiss(name)
            self.preview_at = None
            return
        if key in (CANCEL_KEY, ADOPT_KEY):
            self._close_preview(name, adopt=key == ADOPT_KEY)

    def _close_preview(self, at: Any, adopt: bool) -> None:
        """Reject or adopt the preview ``at`` names and close it."""
        try:
            preview = self.model.previews[int(at)]
        except (IndexError, TypeError, ValueError):
            self.preview_at = None
            return
        if not adopt:
            preview.reject()
            self.preview_at = None
            return
        proposal = self.model.adopt_from(preview)
        self.preview_at = None
        for handler in self.adopt_handlers:
            try:
                handler(proposal)
            except Exception as exc:  # noqa: BLE001 - handler is the main window
                logger.warning("topology adopt handler failed: %s", exc)


if _HAS_QT and _HAS_WEBENGINE:

    class MarketInspectorPage(QWebEnginePage):
        """Routes the page's ``acervator-`` console lines to its owner."""

        def __init__(self, owner) -> None:
            """Hold ``owner`` as the widget that answers the page."""
            super().__init__(owner)
            self._owner = owner

        def javaScriptConsoleMessage(self, level, message, line, source) -> None:
            """Hand an action to the owner and drop every other line."""
            del level, line, source
            if message.startswith(SCREEN_PREFIX):
                self._owner.run_action(message[len(SCREEN_PREFIX) :])
            elif message.startswith(TOPOLOGY_PREFIX):
                self._owner.run_topology_action(message[len(TOPOLOGY_PREFIX) :])

    class MarketInspectorReactTab(MarketInspectorTab):
        """The Market Inspector with its chrome, tables and pane drawn by React."""

        def _build_ui(self) -> None:
            """Build the one web view the whole tab is drawn in."""
            self._screen = surface.MarketInspectorScreenModel()
            self._topologies_pane = TopologiesPaneHost()
            self._page_ready = False
            self._last_model: dict = {}

            self.setAccessibleName(ACCESSIBLE_NAME)
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)
            self._web = QWebEngineView(self)
            self._web_page = MarketInspectorPage(self)
            self._web.setPage(self._web_page)
            self._web.loadFinished.connect(self._on_load_finished)
            self._web.setHtml(tab_html())
            layout.addWidget(self._web, 1)

        # -- what the page is drawn from ----------------------------------

        @property
        def page_ready(self) -> bool:
            """True once ``_on_load_finished`` has seen a successful load."""
            return self._page_ready

        def model(self) -> dict:
            """A copy of the last screen payload pushed."""
            return dict(self._last_model)

        def build_model(self) -> dict:
            """The whole screen as one payload, chrome and rows together."""
            screen = self._screen
            screen.scan_phase = self._scan_state
            screen.show_active = self._show_active
            screen.show_active_checked = self._show_active
            screen.active_symbols = set(self._active_symbols)
            screen.last_meta = dict(self._last_meta)
            screen.pending_refresh = self._pending_refresh
            screen.connectors_getter = self._connectors_getter
            screen.scheduler = self._scheduler
            screen.ata_run_source = self._ata_run_source
            return surface.build_view_model(screen)

        def push(self) -> None:
            """Send the screen payload and the pane payload to the page."""
            self._last_model = self.build_model()
            if not self._page_ready:
                return
            self._run(screen_push_script(self._last_model))
            pane = self._topologies_pane
            self._run(topology_push_script(pane.view_model(), pane.preview_at))

        def row_count(self, callback: Callable[[Any], None]) -> bool:
            """Run ``ROW_COUNT_JS`` and hand the count to ``callback``.

            Returns False and calls nothing while the page is not ready.
            """
            if not self._page_ready:
                return False
            self._web.page().runJavaScript(ROW_COUNT_JS, callback)
            return True

        # -- what the page reports back -----------------------------------

        def run_action(self, payload: str) -> None:
            """Run one filter-row press the page reported."""
            try:
                request = json.loads(payload)
            except ValueError:
                logger.warning("Market Inspector page sent a call that is not JSON")
                return
            key = str(request.get("key") or "")
            if key == REFRESH_KEY:
                self._start_fetch(force=True)
            elif key == SHOW_ACTIVE_KEY:
                self._on_toggle_show_active(bool(request.get("value")))

        def run_topology_action(self, payload: str) -> None:
            """Run one right-pane press the page reported."""
            try:
                request = json.loads(payload)
            except ValueError:
                logger.warning("Topology pane sent a call that is not JSON")
                return
            self._topologies_pane.act(
                str(request.get("key") or ""), request.get("name")
            )
            self.push()

        # -- the widgets the inherited logic writes through ----------------

        def _set_status(self, text: str) -> None:
            """Show ``text`` on the status line."""
            self._screen.status_label_text = text
            self.push()

        def _set_refresh_enabled(self, enabled: bool) -> None:
            """Let the operator press Refresh, or refuse while a scan runs."""
            self._screen.refresh_enabled = bool(enabled)
            self.push()

        def _fill_signal_rows(self, signals: list) -> None:
            """Draw one HTF Signals row per entry of ``signals``."""
            rows = self._screen.signal_rows
            surface.set_row_count(rows, len(signals), len(surface.SIGNAL_COLUMNS))
            for index, found in enumerate(signals):
                surface.fill_signal_row(rows[index], found)
            self.push()

        def _fill_pair_rows(self, pairs: list) -> None:
            """Draw one Opposing Pairs row per entry of ``pairs``."""
            rows = self._screen.pair_rows
            surface.set_row_count(rows, len(pairs), len(surface.PAIR_COLUMNS))
            for index, found in enumerate(pairs):
                surface.fill_pair_row(rows[index], found)
            self.push()

        def _render_empty_notes(self) -> None:
            """Carry the scan state the two empty sentences are built from."""
            self._screen.scan_phase = self._scan_state
            self.push()

        def _render_left_modules(self) -> None:
            """Redraw the three left-side modules from the state they read.

            ``build_model`` builds their lines, so the push is what the
            page needs; the Qt tab writes its own labels instead.
            """
            self.push()

        # -- internals ------------------------------------------------------

        def _run(self, script: str) -> None:
            self._web.page().runJavaScript(script)

        def _on_load_finished(self, ok: bool) -> None:
            self._page_ready = bool(ok)
            if not ok:
                logger.warning("React Market Inspector page failed to load")
                return
            self.push()
