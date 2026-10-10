# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
"""One unbuilt tab's empty state, drawn by React inside ``QWebEngineView``.

``EmptyTabReactPanel`` takes the same view model ``EmptyTabQtPanel`` takes and
draws the renderer module the model's ``method`` field names. ``panel_html``
builds the page from that module, the shared ``empty_tab.css`` skin and the
Electron shell's ``panel_host.js``, so neither side holds a colour of its own.
``EmptyTabPage`` carries the page's own bridge calls back to ``run_action``,
which fires ``buildRequested`` with the sector a press on the build button
names.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from .main_tabs import empty_tabs
from .react_history_panel import page_html
from .react_main_window import read_renderer_asset

try:
    from PySide6.QtCore import Signal
    from PySide6.QtWebEngineCore import QWebEnginePage
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWidgets import QVBoxLayout, QWidget

    _HAS_WEBENGINE = True
except ImportError:
    # Without WebEngine, EmptyTabReactPanel is never defined and its import
    # fails by name.
    _HAS_WEBENGINE = False

logger = logging.getLogger("acervator.gui.react_empty_tab")

#: The element the renderer module draws its empty state into.
PANEL_ROOT_ID = "panel-root"

#: The shared skin, read from ``src/gui/web`` with the module.
PANEL_STYLE_ASSET = "empty_tab.css"

#: The scripts every empty-tab page carries. Order is load order.
BASE_SCRIPT_ASSETS: tuple[str, ...] = (
    "vendor/react.production.min.js",
    "vendor/react-dom.production.min.js",
)

#: The panel host, read from ``desktop/renderer`` and inlined.
SHELL_SCRIPT = "panel_host.js"

#: The JS expression that reads back the whole text the page drew.
DRAWN_TEXT_JS = 'document.getElementById("' + PANEL_ROOT_ID + '").textContent'

#: The console line a page writes to carry one bridge call back to Qt, the
#: same route ``react_exchange_tab`` and ``react_trading_tab`` use.
ACTION_PREFIX = "acervator-empty-tab:"

#: The request field the page sends when the build button is pressed, matching
#: ``BUILD_PARAM`` in ``src/gui/web/class_note.js``.
BUILD_PARAM = "build_bot"

#: The class ``class_note.js`` gives the build button, which the page's own
#: rule paints from the ``--empty-tab-build-`` properties.
BUILD_SELECTOR = ".acervator-empty-tab-build"

_BUILD_RULE = (
    BUILD_SELECTOR + "{align-self:flex-start;margin-top:"
    "var(--empty-tab-build-top);padding:var(--empty-tab-build-pad);"
    "border:none;border-radius:var(--empty-tab-build-radius);"
    "background:var(--empty-tab-build-ground);"
    "color:var(--empty-tab-build-colour);font-family:inherit;"
    "font-size:var(--empty-tab-body-size);font-weight:bold;cursor:pointer;}"
    + BUILD_SELECTOR
    + ":hover{background:var(--empty-tab-build-hover);}"
)


def module_name(model: dict) -> str:
    """The renderer module the model's ``method`` field names, without ``.js``."""
    return str(model["method"]).split(".")[0]


def skin_rule() -> str:
    """The ``:root`` rule carrying ``empty_tabs.SKIN`` to the page.

    ``_BUILD_RULE`` rides with it, so the build button reads the same numbers
    ``empty_tabs.BUILD_STYLE`` paints the Qt one from.
    """
    body = "".join(f"{name}:{value};" for name, value in empty_tabs.SKIN.items())
    return ":root{" + body + "}" + _BUILD_RULE


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


def namer_script(model: dict) -> str:
    """The shim that hands the panel host the name the inlined module lacks."""
    return _NAMER_SOURCE % {"name": json.dumps(module_name(model), ensure_ascii=True)}


_HOST_SOURCE = """(function (global) {
  "use strict";

  var MODEL = %(model)s;
  var NAME = %(name)s;
  var PREFIX = %(prefix)s;

  global.ACERVATOR_MODULES = [NAME + ".js"];
  global.acervator = {
    call: function (method, params) {
      global.console.log(
        PREFIX + JSON.stringify({ method: method, params: params || {} })
      );
      return Promise.resolve(MODEL);
    }
  };

  global.acervatorEmptyTabDrawn = global.acervatorPanelHost.open(
    NAME,
    document.getElementById("%(root)s")
  );
})(window);"""


def host_script(model: dict) -> str:
    """The page's own glue: the model, the roster and the one panel to open.

    ``ACTION_PREFIX`` rides on every ``acervator.call``, so a press reaches
    ``EmptyTabPage.javaScriptConsoleMessage`` and nothing else.
    """
    return _HOST_SOURCE % {
        "model": json.dumps(model, ensure_ascii=True),
        "name": json.dumps(module_name(model), ensure_ascii=True),
        "root": PANEL_ROOT_ID,
        "prefix": json.dumps(ACTION_PREFIX, ensure_ascii=True),
    }


def pressed_class(payload: str, method: str) -> str:
    """The sector one page's bridge call names, or an empty string for none.

    A payload that is not JSON, names a method other than ``method``, or
    carries no ``BUILD_PARAM`` answers an empty string, so no press is invented.
    """
    try:
        asked = json.loads(payload)
    except ValueError:
        return ""
    if not isinstance(asked, dict):
        return ""
    if str(asked.get("method") or "") != str(method):
        return ""
    params = asked.get("params")
    if not isinstance(params, dict):
        return ""
    return str(params.get(BUILD_PARAM) or "")


def panel_html(model: dict, theme: object = None) -> str:
    """The whole empty-tab page as one string, with no network fetch.

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
        + namer_script(model)
        + "</script>"
    )
    scripts = BASE_SCRIPT_ASSETS + (module_name(model) + ".js",)
    return page_html((PANEL_STYLE_ASSET,), scripts, body, theme, (host_script(model),))


if _HAS_WEBENGINE:

    class EmptyTabPage(QWebEnginePage):
        """The panel's page, carrying its own bridge calls back to the panel.

        A console line beginning ``ACTION_PREFIX`` is the page reporting a
        press, and every other line is handed to the logger.
        """

        def __init__(self, owner) -> None:
            """Hold the panel ``_on_page_call`` answers."""
            super().__init__(owner)
            self._owner = owner

        def javaScriptConsoleMessage(self, level, message, line, source) -> None:
            """Hand a bridge call to the panel and drop every other line."""
            del level, line, source
            if message.startswith(ACTION_PREFIX):
                self._owner.run_action(message[len(ACTION_PREFIX) :])

    class EmptyTabReactPanel(QWidget):
        """One unbuilt tab whose empty state is drawn by its renderer module.

        Takes the view model ``_add_empty_tab`` already read from the surface,
        and builds its web view on the first show.
        """

        #: Carries ``build_class`` when the page reports a press on the button,
        #: matching ``EmptyTabQtPanel.buildRequested``.
        buildRequested = Signal(str)  # noqa: N815 - Qt signal name

        def __init__(self, model: dict, parent=None) -> None:
            """Hold ``model`` and lay out the space its page will fill."""
            super().__init__(parent)
            self._model = dict(model)
            self._web: Any = None
            self._page_ready = False
            self.setAccessibleName(model["accessible_name"])
            self._layout = QVBoxLayout(self)
            self._layout.setContentsMargins(0, 0, 0, 0)
            self._layout.setSpacing(0)

        def model(self) -> dict:
            """A copy of the view model the panel draws."""
            return dict(self._model)

        @property
        def page_ready(self) -> bool:
            """True once ``_on_load_finished`` has seen a successful load."""
            return self._page_ready

        def panel_view(self):
            """The web view the panel draws in, or None before the first show."""
            return self._web

        def showEvent(self, event) -> None:
            """Draw the React empty state the first time the tab is shown."""
            super().showEvent(event)
            self.build_panel()

        def run_action(self, payload: str) -> str:
            """Fire ``buildRequested`` for a press the page reported.

            Answers the sector carried, or an empty string where ``payload``
            named no press on this panel's own method.
            """
            key = pressed_class(payload, str(self._model["method"]))
            if key:
                self.buildRequested.emit(key)
            return key

        def build_panel(self) -> None:
            """Create the panel's web view and load its page, once."""
            if self._web is not None:
                return
            self._web = QWebEngineView(self)
            self._web.setPage(EmptyTabPage(self))
            self._web.setAccessibleName(self._model["accessible_name"])
            self._web.loadFinished.connect(self._on_load_finished)
            self._web.setHtml(panel_html(self._model))
            self._layout.addWidget(self._web, 1)

        def _on_load_finished(self, ok: bool) -> None:
            self._page_ready = bool(ok)
            if not ok:
                logger.warning(
                    "The React empty tab page failed to load: %s",
                    self._model["heading"],
                )
