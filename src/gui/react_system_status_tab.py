# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
"""The Status tab's emitter network read-out, drawn by React inside ``QWebEngineView``.

``SystemStatusReactPanel`` asks ``system_status_tab_surface.view_model`` for the
read-out and draws ``src/gui/web/system_status_tab.js`` through the Electron
shell's ``panel_host.js``, so the page in the desktop window and the page in the
shell run the same module. ``panel_html`` carries the design tokens the style
sheet reads, and ``SKIN`` is the one place they are named.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from . import design_system as ds
from .main_tabs import system_status_tab_surface as surface
from .react_history_panel import page_html, read_asset
from .react_main_window import read_renderer_asset

try:
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWidgets import QVBoxLayout, QWidget

    _HAS_WEBENGINE = True
except ImportError:
    # Without WebEngine, SystemStatusReactPanel is never defined and its import
    # fails by name.
    _HAS_WEBENGINE = False

logger = logging.getLogger("acervator.gui.react_system_status_tab")

#: The element the renderer module draws the read-out into.
PANEL_ROOT_ID = "panel-root"

#: The style sheet the page carries.
PANEL_STYLE_ASSET = "system_status_tab.css"

#: The renderer module the page draws.
PANEL_MODULE = "system_status_tab.js"

#: The scripts every page carries before the module. Order is load order.
BASE_SCRIPT_ASSETS: tuple[str, ...] = (
    "vendor/react.production.min.js",
    "vendor/react-dom.production.min.js",
)

#: The panel host, read from ``desktop/renderer`` and inlined.
SHELL_SCRIPT = "panel_host.js"

#: Every design token ``system_status_tab.css`` reads, under the name and in
#: the form the shell's ``design_tokens.js`` writes: a size is unitless, and
#: the sheet multiplies it by 1px.
SKIN = {
    "--SURFACE_0": ds.SURFACE_0,
    "--SURFACE_1": ds.SURFACE_1,
    "--SURFACE_2": ds.SURFACE_2,
    "--SURFACE_3": ds.SURFACE_3,
    "--TEXT_MAX": ds.TEXT_MAX,
    "--TEXT_HIGH": ds.TEXT_HIGH,
    "--TEXT_MED": ds.TEXT_MED,
    "--TEXT_LOW": ds.TEXT_LOW,
    "--OUTLINE": ds.OUTLINE,
    "--SUCCESS": ds.SUCCESS,
    "--WARNING": ds.WARNING,
    "--TYPE_H2": ds.TYPE_H2,
    "--TYPE_H4": ds.TYPE_H4,
    "--TYPE_BODY": ds.TYPE_BODY,
    "--TYPE_SMALL": ds.TYPE_SMALL,
    "--SPACE_S": ds.SPACE_S,
    "--SPACE_M": ds.SPACE_M,
    "--SPACE_L": ds.SPACE_L,
    "--RADIUS_XS": ds.RADIUS_XS,
}

#: The JS expression that reads back the whole text the page drew.
DRAWN_TEXT_JS = 'document.getElementById("' + PANEL_ROOT_ID + '").textContent'

#: The JS expression naming each style sheet the page holds and its rule count.
LOADED_STYLES_JS = "JSON.stringify(window.acervatorSystemStatusPage.styles())"

#: The JS expression naming every module that registered a panel.
DRAWN_MODULES_JS = "window.acervatorPanelHost.registered().join(',')"

_NAMER_SOURCE = """(function (global) {
  "use strict";

  var NAME = %(name)s;
  var host = global.acervatorPanelHost;
  var real = host.register;

  // The module is inlined, so document.currentScript names no file.
  host.register = function (spec, called) {
    return real(spec, called || NAME);
  };
})(window);"""

_HOST_SOURCE = """(function (global) {
  "use strict";

  var MODEL = %(model)s;
  var NAME = %(name)s;

  global.ACERVATOR_MODULES = [NAME + ".js"];
  global.acervator = {
    call: function () {
      return Promise.resolve(MODEL);
    }
  };

  global.acervatorSystemStatusPage = {
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

  global.acervatorSystemStatusDrawn = global.acervatorPanelHost.open(
    NAME,
    document.getElementById("%(root)s")
  );
})(window);"""


def module_name() -> str:
    """The renderer module the page draws, without its ``.js`` suffix."""
    return PANEL_MODULE.rsplit(".", 1)[0]


def skin_rule() -> str:
    """The ``:root`` rule carrying ``SKIN`` to the page."""
    body = "".join(f"{name}:{value};" for name, value in SKIN.items())
    return ":root{" + body + "}"


def namer_script() -> str:
    """The shim that hands the panel host the name the inlined module lacks."""
    return _NAMER_SOURCE % {"name": json.dumps(module_name(), ensure_ascii=True)}


def host_script(model: dict) -> str:
    """The page's own glue: the read-out, the roster and the one panel to open."""
    return _HOST_SOURCE % {
        "model": json.dumps(model, ensure_ascii=True),
        "name": json.dumps(module_name(), ensure_ascii=True),
        "root": PANEL_ROOT_ID,
    }


def panel_html(model: dict, theme: object = None) -> str:
    """The whole Status page as one string, with no network fetch.

    The panel host rides in the body, so it is on the page before the renderer
    module runs and asks it for a registration.
    """
    body = (
        "<style>"
        + skin_rule()
        + "</style>"
        + f'<div id="{PANEL_ROOT_ID}"></div>'
        + "<script>"
        + read_renderer_asset(SHELL_SCRIPT)
        + "</script><script>"
        + namer_script()
        + "</script>"
    )
    scripts = BASE_SCRIPT_ASSETS + (PANEL_MODULE,)
    return page_html((PANEL_STYLE_ASSET,), scripts, body, theme, (host_script(model),))


def style_sheet() -> str:
    """The style sheet text the page carries, read from ``src/gui/web``."""
    return read_asset(PANEL_STYLE_ASSET)


if _HAS_WEBENGINE:

    class SystemStatusReactPanel(QWidget):
        """The Status tab, whose emitter read-out is drawn by its renderer module.

        Asks the surface for the read-out on each build, so a panel shown again
        after a run draws what the sink holds then.
        """

        def __init__(self, model: dict | None = None, parent=None) -> None:
            """Hold ``model``, or ask the surface for one, and lay out its space."""
            super().__init__(parent)
            self._model = dict(model) if model is not None else surface.view_model({})
            self._web: Any = None
            self._page_ready = False
            self.setAccessibleName(self._model["accessible_name"])
            self._layout = QVBoxLayout(self)
            self._layout.setContentsMargins(0, 0, 0, 0)
            self._layout.setSpacing(0)

        def model(self) -> dict:
            """A copy of the read-out the panel draws."""
            return dict(self._model)

        @property
        def page_ready(self) -> bool:
            """True once ``_on_load_finished`` has seen a successful load."""
            return self._page_ready

        def panel_view(self):
            """The web view the panel draws in, or None before the first show."""
            return self._web

        def showEvent(self, event) -> None:
            """Draw the read-out the first time the tab is shown."""
            super().showEvent(event)
            self.build_panel()

        def build_panel(self) -> None:
            """Create the panel's web view and load its page, once."""
            if self._web is not None:
                return
            self._web = QWebEngineView(self)
            self._web.setAccessibleName(self._model["accessible_name"])
            self._web.loadFinished.connect(self._on_load_finished)
            self._web.setHtml(panel_html(self._model))
            self._layout.addWidget(self._web, 1)

        def _on_load_finished(self, ok: bool) -> None:
            self._page_ready = bool(ok)
            if not ok:
                logger.warning(
                    "The Status page failed to load: %s", self._model["heading"]
                )
