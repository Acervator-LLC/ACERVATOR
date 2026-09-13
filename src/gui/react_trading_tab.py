# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
"""The Live tab drawn by React inside ``QWebEngineView``.

``TradingTabReact`` asks ``trading_tab_surface`` for the tab and draws
``src/gui/web/trading_tab.js`` through the Electron shell's ``panel_host.js``,
so the page in the desktop window and the page in the shell run the same
module. ``trading_tab.js`` mounts ``indicator_panel.js`` and ``status_log.js``
into slots it keeps for them, so the voting panel and the Activity Log need no
registration of their own. ``page_html`` inlines every script, so the page
fetches nothing.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from .main_tabs import indicator_panel_surface, status_log_surface, trading_tab_surface
from .react_history_panel import page_html, read_asset
from .react_main_window import read_renderer_asset

try:
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWidgets import QVBoxLayout, QWidget

    _HAS_WEBENGINE = True
except ImportError:
    # Without WebEngine, TradingTabReact is never defined and its import
    # fails by name.
    _HAS_WEBENGINE = False

logger = logging.getLogger("acervator.gui.react_trading_tab")

ACCESSIBLE_NAME = "React Live Tab"

#: The element ``trading_tab.js`` draws the tab into.
PANEL_ROOT_ID = "panel-root"

#: The renderer module the page draws.
PANEL_MODULE = "trading_tab.js"

#: The modules ``trading_tab.js`` mounts into its own slots. Order is load
#: order, and each one registers with ``panel_host.js`` under its own name.
CHILD_MODULES: tuple[str, ...] = ("status_log.js", "indicator_panel.js")

#: The scripts every page carries before the modules. Order is load order.
BASE_SCRIPT_ASSETS: tuple[str, ...] = (
    "vendor/react.production.min.js",
    "vendor/react-dom.production.min.js",
)

#: The panel host, read from ``desktop/renderer`` and inlined.
SHELL_SCRIPT = "panel_host.js"

#: The global a page carries the name of the module running now under.
NAME_GLOBAL = "acervatorInlinedModule"

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

_HOST_SOURCE = """(function (global) {
  "use strict";

  var MODELS = %(models)s;
  var NAME = %(name)s;

  global.ACERVATOR_MODULES = %(roster)s;
  global.acervator = {
    call: function (method) {
      var owns = Object.prototype.hasOwnProperty.call(MODELS, method);
      return Promise.resolve(owns ? MODELS[method] : null);
    }
  };

  global.acervatorTradingTabDrawn = global.acervatorPanelHost.open(
    NAME,
    document.getElementById("%(root)s")
  );
})(window);"""


def module_name(asset: str = PANEL_MODULE) -> str:
    """``asset`` without its ``.js`` suffix, which is the panel's own name."""
    return asset.rsplit(".", 1)[0]


def roster() -> tuple[str, ...]:
    """Every module the page carries, in load order."""
    return CHILD_MODULES + (PANEL_MODULE,)


def models(live: Any = None) -> dict:
    """The view model of every bridge method the page's modules ask for.

    ``live`` is a ``desktop_bridge.LiveSystem``, and ``bind_live`` builds the
    tab from the exchanges the running program is configured for.
    """
    tab = (
        trading_tab_surface.bind_live(live)
        if live is not None
        else trading_tab_surface.view_model
    )
    return {
        trading_tab_surface.METHOD: tab({}),
        status_log_surface.METHOD: status_log_surface.view_model({}),
        indicator_panel_surface.METHOD: indicator_panel_surface.view_model({}),
    }


def namer_script() -> str:
    """The shim that hands the panel host the name an inlined module lacks."""
    return _NAMER_SOURCE % {"name_global": NAME_GLOBAL}


def marker_script(asset: str) -> str:
    """The one statement naming the module whose script tag comes next."""
    return _MARKER_SOURCE % {
        "name_global": NAME_GLOBAL,
        "module": json.dumps(module_name(asset), ensure_ascii=True),
    }


def host_script(built: dict) -> str:
    """The page's own glue: the models, the roster and the one panel to open."""
    return _HOST_SOURCE % {
        "models": json.dumps(built, ensure_ascii=True),
        "name": json.dumps(module_name(), ensure_ascii=True),
        "roster": json.dumps(list(roster()), ensure_ascii=True),
        "root": PANEL_ROOT_ID,
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


def panel_html(built: dict, theme: object = None) -> str:
    """The whole Live page as one string, with no network fetch."""
    return page_html((), (), page_body(), theme, (host_script(built),))


if _HAS_WEBENGINE:

    class TradingTabReact(QWidget):
        """The Live tab, drawn by ``trading_tab.js`` and its two child modules.

        ``build_panel`` loads the page once, on the first show, so a window
        that never opens the tab pays for no web view.
        """

        def __init__(
            self,
            live: Any = None,
            parent: Optional[QWidget] = None,
            theme: object = None,
        ) -> None:
            """Hold ``live`` as the source the tab's view models are built from."""
            super().__init__(parent)
            self.setAccessibleName(ACCESSIBLE_NAME)
            self._live = live
            self._theme = theme
            self._models: dict = {}
            self._page_ready = False
            self._web: Any = None
            self._layout = QVBoxLayout(self)
            self._layout.setContentsMargins(0, 0, 0, 0)
            self._layout.setSpacing(0)

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

        def showEvent(self, event) -> None:  # noqa: N802
            """Build the web view the first time the tab is shown."""
            super().showEvent(event)
            self.build_panel()

        def build_panel(self) -> None:
            """Create the tab's web view and load its page, once."""
            if self._web is not None:
                return
            self._models = models(self._live)
            self._web = QWebEngineView(self)
            self._web.setAccessibleName(ACCESSIBLE_NAME)
            self._web.loadFinished.connect(self._on_load_finished)
            self._web.setHtml(panel_html(self._models, self._theme))
            self._layout.addWidget(self._web, 1)

        def _on_load_finished(self, ok: bool) -> None:
            self._page_ready = bool(ok)
            if not ok:
                logger.warning("The React Live tab page failed to load")
