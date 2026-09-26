# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
"""The Activity Log pane drawn by React inside ``QWebEngineView``.

``StatusLogReact`` answers the calls the window already makes on ``StatusLog``
-- ``log``, ``force_log``, ``pause``, ``resume``, ``is_paused``,
``toggle_pause`` and ``health_stats`` -- and draws ``src/gui/web/status_log.js``
in place of the Qt ``QTextEdit``. ``StatusLogPage`` carries the page's own
bridge calls back to ``run_action``, and ``page_html`` inlines
``status_log.css`` and every script, so the page fetches nothing.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from .main_tabs import design_system_surface as token_surface
from .main_tabs import status_log_surface as surface
from .react_history_panel import STYLE_SOURCE_ASSETS, page_html, read_asset

try:
    from PySide6.QtWebEngineCore import QWebEnginePage
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWidgets import QVBoxLayout, QWidget

    _HAS_WEBENGINE = True
except ImportError:
    # Without WebEngine, StatusLogReact is never defined and its import
    # fails by name.
    _HAS_WEBENGINE = False

logger = logging.getLogger("acervator.gui.react_status_log")

ACCESSIBLE_NAME = "React Status Log"

#: The element ``status_log.js`` draws the pane into.
PANEL_ROOT_ID = "status-log-root"

#: The renderer module the page draws.
PANEL_MODULE = "status_log.js"

#: The style sheet the page carries.
STYLE_ASSETS: tuple[str, ...] = ("status_log.css",)

#: The scripts every page carries before the modules. Order is load order.
BASE_SCRIPT_ASSETS: tuple[str, ...] = (
    "vendor/react.production.min.js",
    "vendor/react-dom.production.min.js",
)

#: The global each module defines once it has run to its end.
MODULE_GLOBALS: dict[str, str] = {
    "design_tokens.js": "acervatorTokens",
    "theme_engine.js": "acervatorThemes",
    "shared_widgets.js": "acervatorWidgets",
    "header_strip.js": "acervatorHeader",
    PANEL_MODULE: "acervatorLog",
}

#: The setter each module publishes for the payload of its own method.
METHOD_SETTERS: dict[str, str] = {
    token_surface.METHOD: "acervatorSetTokens",
    surface.METHOD: "acervatorSetLog",
}

#: The console line the page writes a bridge call on.
ACTION_PREFIX = "acervator-status-log:"

#: The JS expression naming every module whose global reached the page.
LOADED_MODULES_JS = "window.acervatorStatusLogPage.modules().join(',')"

#: The JS expression naming each style sheet the page holds and its rule count.
LOADED_STYLES_JS = "JSON.stringify(window.acervatorStatusLogPage.styles())"

#: The JS expression counting the line elements the pane really drew.
DRAWN_LINES_JS = "JSON.stringify(window.acervatorStatusLogPage.lines())"

#: The JS statement that takes the bridge away, which stops every page timer.
STOP_FEEDS_JS = "window.acervatorStatusLogPage.stop();"

_STYLE_TAG = '<style data-asset="%(name)s">%(source)s</style>'

_HOST_SOURCE = """(function (global, doc) {
  "use strict";

  var MODELS = %(models)s;
  var SETTERS = %(setters)s;
  var GLOBALS = %(globals)s;
  var METHOD = %(method)s;
  var ROOT = %(root)s;
  var PREFIX = %(prefix)s;
  var ASSET = %(asset)s;
  var LINE = %(line)s;

  global.ACERVATOR_MODULES = %(roster)s;

  function owns(bag, name) {
    return Object.prototype.hasOwnProperty.call(bag, name);
  }

  // Hands each module the payload of its own method, then writes the tokens
  // onto the document so a `var(--TOKEN)` in the style sheet resolves.
  function seat() {
    SETTERS.forEach(function (pair) {
      var setter = global[pair[1]];
      if (typeof setter === "function" && owns(MODELS, pair[0])) {
        setter(MODELS[pair[0]]);
      }
    });
    if (global.acervatorTokens && typeof global.acervatorTokens.apply === "function") {
      global.acervatorTokens.apply(doc.documentElement);
    }
  }

  function draw() {
    var api = global.acervatorLog;
    var node = doc.getElementById(ROOT);
    if (!api || typeof api.renderLog !== "function" || node === null) {
      return false;
    }
    api.renderLog(node, owns(MODELS, METHOD) ? MODELS[METHOD] : null);
    return true;
  }

  function modules() {
    return GLOBALS.filter(function (pair) {
      return global[pair[1]] !== undefined;
    }).map(function (pair) {
      return pair[0];
    });
  }

  function styles() {
    var found = [];
    var tags = doc.querySelectorAll("style[" + ASSET + "]");
    for (var at = 0; at < tags.length; at++) {
      var sheet = tags[at].sheet;
      found.push([
        tags[at].getAttribute(ASSET),
        sheet === null ? 0 : sheet.cssRules.length
      ]);
    }
    return found;
  }

  function lines() {
    return doc.querySelectorAll("#" + ROOT + " " + LINE).length;
  }

  function stop() {
    delete global.acervator;
    return true;
  }

  global.acervator = {
    call: function (method, params) {
      global.console.log(
        PREFIX + JSON.stringify({ method: method, params: params || {} })
      );
      return Promise.resolve(owns(MODELS, method) ? MODELS[method] : null);
    }
  };

  global.acervatorStatusLogPage = {
    modules: modules,
    styles: styles,
    lines: lines,
    stop: stop,
    hold: function (bag) {
      Object.keys(bag).forEach(function (name) {
        MODELS[name] = bag[name];
      });
      seat();
      return draw();
    }
  };

  seat();
  global.acervatorStatusLogPageDrawn = draw();
})(window, document);"""


def roster() -> tuple[str, ...]:
    """Every module the page carries, in load order.

    ``STYLE_SOURCE_ASSETS`` leads: ``status_log.js`` names a token through
    ``shared_widgets.variableFor`` before it paints a line.
    """
    return STYLE_SOURCE_ASSETS + (PANEL_MODULE,)


def module_globals() -> list:
    """Each module the page carries beside the global it defines when it runs."""
    return [[name, MODULE_GLOBALS[name]] for name in roster()]


def method_setters() -> list:
    """Each bridge method the page answers beside that module's own setter."""
    return [
        [method, METHOD_SETTERS[method]]
        for method in (token_surface.METHOD, surface.METHOD)
    ]


def host_script(built: dict) -> str:
    """The page's own glue: the models, the roster and the one pane to draw."""
    return _HOST_SOURCE % {
        "models": json.dumps(built, ensure_ascii=True),
        "setters": json.dumps(method_setters(), ensure_ascii=True),
        "globals": json.dumps(module_globals(), ensure_ascii=True),
        "method": json.dumps(surface.METHOD, ensure_ascii=True),
        "root": json.dumps(PANEL_ROOT_ID, ensure_ascii=True),
        "prefix": json.dumps(ACTION_PREFIX, ensure_ascii=True),
        "asset": json.dumps("data-asset", ensure_ascii=True),
        "line": json.dumps('[data-part="line"]', ensure_ascii=True),
        "roster": json.dumps(list(roster()), ensure_ascii=True),
    }


def _tag(source: str) -> str:
    """``source`` wrapped in a script tag of its own."""
    return "<script>" + source + "</script>"


def page_body() -> str:
    """The page's body: the named style sheets, the root, React, the modules.

    Each style sheet carries its own ``data-asset`` name, so ``styles`` reports
    which sheet the page holds and how many rules that sheet gave it.
    """
    parts = [
        _STYLE_TAG % {"name": name, "source": read_asset(name)} for name in STYLE_ASSETS
    ]
    parts.append(f'<div id="{PANEL_ROOT_ID}"></div>')
    for name in BASE_SCRIPT_ASSETS:
        parts.append(_tag(read_asset(name)))
    for name in roster():
        parts.append(_tag(read_asset(name)))
    return "".join(parts)


def panel_html(built: dict, theme: object = None) -> str:
    """The whole Activity Log page as one string, with no network fetch."""
    return page_html((), (), page_body(), theme, (host_script(built),))


def push_script(built: dict) -> str:
    """The one JS statement handing the page a fresh payload for each method.

    ``ensure_ascii=True`` escapes U+2028 and U+2029, which are legal inside a
    JSON string and are JavaScript line terminators.
    """
    body = json.dumps(built, ensure_ascii=True)
    return "window.acervatorStatusLogPage.hold(" + body + ");"


def pane_payload(model: surface.StatusLogModel) -> dict:
    """The pane's whole document, and every other field ``build_view_model`` gives.

    ``build_view_model`` drains ``take_painted``, so its ``document`` carries
    only the lines that one call painted; ``lines`` is every line the pane holds
    under ``max_blocks``, which is what ``document_blocks`` counts.
    """
    payload = surface.build_view_model(model)
    payload["document"] = {"lines": list(model.lines)}
    return payload


if _HAS_WEBENGINE:

    class StatusLogPage(QWebEnginePage):
        """Routes the page's ``acervator-status-log:`` console lines to its owner."""

        def __init__(self, owner) -> None:
            """Hold ``owner`` as the widget that answers the page."""
            super().__init__(owner)
            self._owner = owner

        def javaScriptConsoleMessage(self, level, message, line, source) -> None:
            """Hand a bridge call to the owner and drop every other line."""
            del level, line, source
            if message.startswith(ACTION_PREFIX):
                self._owner.run_action(message[len(ACTION_PREFIX) :])

    class StatusLogReact(QWidget):
        """The Activity Log pane, drawn by ``status_log.js``.

        ``build_panel`` loads the page once on the first show, and ``log``,
        ``force_log``, ``pause``, ``resume`` and ``health_stats`` answer the
        calls ``MainWindow`` and ``TradingTabMixin`` already make on
        ``StatusLog``.
        """

        def __init__(
            self,
            parent: Optional[QWidget] = None,
            theme: object = None,
        ) -> None:
            """Build the pane's own log model and the layout its view sits in."""
            super().__init__(parent)
            self.setAccessibleName(ACCESSIBLE_NAME)
            self._theme = theme
            self._log = surface.StatusLogModel()
            self._models: dict = {}
            self._page_ready = False
            self._stopped = False
            self._web: Any = None
            self._layout = QVBoxLayout(self)
            self._layout.setContentsMargins(0, 0, 0, 0)
            self._layout.setSpacing(0)

        # -- what the window already calls ----------------------------------

        def log(
            self,
            message: str,
            level: str = surface.DEFAULT_LOG_LEVEL,
            kind: Optional[str] = None,
            lights: Optional[list] = None,
        ) -> None:
            """Paint one line, or hold it while the pane is paused."""
            self._log.log(message, level, kind=kind, lights=lights)
            self._publish()

        def force_log(
            self,
            message: str,
            level: str = surface.DEFAULT_FORCE_LEVEL,
            kind: Optional[str] = None,
            lights: Optional[list] = None,
        ) -> None:
            """Paint one line whether or not the pane is paused."""
            self._log.force_log(message, level, kind=kind, lights=lights)
            self._publish()

        def is_paused(self) -> bool:
            """True while ``pause`` is holding arriving lines back."""
            return self._log.is_paused()

        def pause(self) -> None:
            """Hold each arriving line until ``resume`` paints it."""
            self._log.pause()
            self._publish()

        def resume(self) -> None:
            """Paint every held line in arrival order, then the resume notice."""
            self._log.resume()
            self._publish()

        def toggle_pause(self) -> bool:
            """Flip the paused state and return what it became."""
            became = self._log.toggle_pause()
            self._publish()
            return became

        def health_stats(self) -> dict:
            """The counters the Activity-Log watchdog polls every 60 s."""
            return self._log.health_stats()

        # -- what the page reports back --------------------------------------

        def run_action(self, payload: str) -> None:
            """Answer one bridge call the page made and push the new payload."""
            if self._stopped:
                return
            try:
                asked = json.loads(payload)
            except ValueError:
                logger.warning("Status log page sent a bridge call that is not JSON")
                return
            method = str(asked.get("method") or "")
            params = asked.get("params")
            self._answer(method, params if isinstance(params, dict) else {})
            self._publish()

        def stop_feeds(self) -> None:
            """Take the bridge off the page, which stops every timer it runs."""
            self._stopped = True
            if self._page_ready and self._web is not None:
                self._web.page().runJavaScript(STOP_FEEDS_JS)

        # -- the models the page is built from --------------------------------

        def models(self) -> dict:
            """A copy of the payloads the page was last built or pushed with."""
            return dict(self._models)

        @property
        def page_ready(self) -> bool:
            """True once ``_on_load_finished`` has seen a successful load."""
            return self._page_ready

        def panel_view(self):
            """The web view the pane draws in, or None before the first show."""
            return self._web

        def build_panel(self) -> None:
            """Create the pane's web view and load its page, once."""
            if self._web is not None:
                return
            self._models = self._build_models()
            self._web = QWebEngineView(self)
            self._web.setAccessibleName(ACCESSIBLE_NAME)
            self._web.setPage(StatusLogPage(self))
            self._web.loadFinished.connect(self._on_load_finished)
            self._web.setHtml(panel_html(self._models, self._theme))
            self._layout.addWidget(self._web, 1)

        def showEvent(self, event) -> None:  # noqa: N802
            """Build the web view the first time the pane is shown."""
            super().showEvent(event)
            self.build_panel()

        # -- internals ---------------------------------------------------------

        def _build_models(self) -> dict:
            """The payload of every bridge method the page's modules ask for."""
            return {
                token_surface.METHOD: token_surface.view_model({}),
                surface.METHOD: pane_payload(self._log),
            }

        def _answer(self, method: str, params: dict) -> None:
            if method == surface.METHOD:
                paused = params.get("paused")
                surface.build_view_model(
                    self._log,
                    params.get("messages") or [],
                    paused=None if paused is None else bool(paused),
                    toggle=bool(params.get("toggle", False)),
                )

        def _publish(self) -> None:
            self._models = self._build_models()
            if self._page_ready and not self._stopped and self._web is not None:
                self._web.page().runJavaScript(push_script(self._models))

        def _on_load_finished(self, ok: bool) -> None:
            self._page_ready = bool(ok)
            if not ok:
                logger.warning("The React status log page failed to load")
                return
            self._publish()
