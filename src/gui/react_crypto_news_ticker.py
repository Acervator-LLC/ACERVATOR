# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
"""The exchange header's news strip drawn by React inside ``QWebEngineView``.

``CryptoNewsTickerReact`` answers the calls the exchange header already makes
on ``CryptoNewsTicker`` -- ``start``, ``stop``, ``force_refresh`` and
``current_headlines`` -- and draws ``src/gui/web/crypto_news_ticker.js`` in
place of the Qt ``QLabel``. ``TickerPage`` carries the page's own bridge calls
back to ``run_action``, and ``page_html`` inlines ``crypto_news_ticker.css``
and every script, so the page fetches nothing. ``CryptoNewsTickerModel`` reads
a feed only through the ``fetcher`` handed to it, so a strip built with
``fetcher=None`` answers every fetch with no story and opens no socket.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Optional

from .main_tabs import crypto_news_ticker_surface as surface
from .main_tabs import design_system_surface as token_surface
from .react_history_panel import STYLE_SOURCE_ASSETS, page_html, read_asset

try:
    from PySide6.QtWebEngineCore import QWebEnginePage
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWidgets import QVBoxLayout, QWidget

    _HAS_WEBENGINE = True
except ImportError:
    # Without WebEngine, CryptoNewsTickerReact is never defined and its
    # import fails by name.
    _HAS_WEBENGINE = False

logger = logging.getLogger("acervator.gui.react_crypto_news_ticker")

ACCESSIBLE_NAME = "React Crypto News Ticker"

#: The element ``crypto_news_ticker.js`` draws the strip into.
PANEL_ROOT_ID = "news-ticker-root"

#: The renderer module the page draws.
PANEL_MODULE = "crypto_news_ticker.js"

#: The style sheet the page carries.
STYLE_ASSETS: tuple[str, ...] = ("crypto_news_ticker.css",)

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
    PANEL_MODULE: "acervatorTicker",
}

#: The setter each module publishes for the payload of its own method.
METHOD_SETTERS: dict[str, str] = {
    token_surface.METHOD: "acervatorSetTokens",
    surface.METHOD: "acervatorSetTicker",
}

#: The console line the page writes a bridge call on.
ACTION_PREFIX = "acervator-news-ticker:"

#: The JS expression naming every module whose global reached the page.
LOADED_MODULES_JS = "window.acervatorTickerPage.modules().join(',')"

#: The JS expression naming each style sheet the page holds and its rule count.
LOADED_STYLES_JS = "JSON.stringify(window.acervatorTickerPage.styles())"

#: The JS expression counting the headline elements the strip really drew.
DRAWN_HEADLINES_JS = "JSON.stringify(window.acervatorTickerPage.headlines())"

#: The JS statement that takes the bridge away, which stops every page timer.
STOP_FEEDS_JS = "window.acervatorTickerPage.stop();"

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
  var HEADLINE = %(headline)s;

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
    var api = global.acervatorTicker;
    var node = doc.getElementById(ROOT);
    if (!api || typeof api.renderTicker !== "function" || node === null) {
      return false;
    }
    api.renderTicker(node, owns(MODELS, METHOD) ? MODELS[METHOD] : null);
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

  function headlines() {
    return doc.querySelectorAll("#" + ROOT + " " + HEADLINE).length;
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

  global.acervatorTickerPage = {
    modules: modules,
    styles: styles,
    headlines: headlines,
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
  global.acervatorTickerPageDrawn = draw();
})(window, document);"""


def news_fetcher() -> Optional[Callable[[], list]]:
    """The reader the Qt strip fetches its ten feeds with, or None when absent.

    ``fetch_all`` takes the transport its worker reads a feed body with, and a
    strip answers with no story without one.
    """
    import time
    from functools import partial

    try:
        from ..core.safe_url import SafeRequest, safe_urlopen
    except ImportError as exc:
        logger.debug("news feed reader not imported: %s", exc)
        return None
    return partial(surface.fetch_all, SafeRequest, safe_urlopen, clock=time.monotonic)


def roster() -> tuple[str, ...]:
    """Every module the page carries, in load order.

    ``STYLE_SOURCE_ASSETS`` leads: ``crypto_news_ticker.js`` parses the strip's
    Qt style sheet with ``header_strip.styleOf``.
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
    """The page's own glue: the models, the roster and the one strip to draw."""
    return _HOST_SOURCE % {
        "models": json.dumps(built, ensure_ascii=True),
        "setters": json.dumps(method_setters(), ensure_ascii=True),
        "globals": json.dumps(module_globals(), ensure_ascii=True),
        "method": json.dumps(surface.METHOD, ensure_ascii=True),
        "root": json.dumps(PANEL_ROOT_ID, ensure_ascii=True),
        "prefix": json.dumps(ACTION_PREFIX, ensure_ascii=True),
        "asset": json.dumps("data-asset", ensure_ascii=True),
        "headline": json.dumps('[data-part="headline"]', ensure_ascii=True),
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
        _STYLE_TAG % {"name": name, "source": read_asset(name)}
        for name in STYLE_ASSETS
    ]
    parts.append(f'<div id="{PANEL_ROOT_ID}"></div>')
    for name in BASE_SCRIPT_ASSETS:
        parts.append(_tag(read_asset(name)))
    for name in roster():
        parts.append(_tag(read_asset(name)))
    return "".join(parts)


def panel_html(built: dict, theme: object = None) -> str:
    """The whole news strip page as one string, with no network fetch."""
    return page_html((), (), page_body(), theme, (host_script(built),))


def push_script(built: dict) -> str:
    """The one JS statement handing the page a fresh payload for each method.

    ``ensure_ascii=True`` escapes U+2028 and U+2029, which are legal inside a
    JSON string and are JavaScript line terminators.
    """
    body = json.dumps(built, ensure_ascii=True)
    return "window.acervatorTickerPage.hold(" + body + ");"


if _HAS_WEBENGINE:

    class TickerPage(QWebEnginePage):
        """Routes the page's ``acervator-news-ticker:`` console lines to its owner."""

        def __init__(self, owner) -> None:
            """Hold ``owner`` as the widget that answers the page."""
            super().__init__(owner)
            self._owner = owner

        def javaScriptConsoleMessage(self, level, message, line, source) -> None:
            """Hand a bridge call to the owner and drop every other line."""
            del level, line, source
            if message.startswith(ACTION_PREFIX):
                self._owner.run_action(message[len(ACTION_PREFIX) :])

    class CryptoNewsTickerReact(QWidget):
        """The exchange header's news strip, drawn by ``crypto_news_ticker.js``.

        ``build_panel`` loads the page once on the first show; ``start``,
        ``stop``, ``force_refresh`` and ``current_headlines`` answer
        ``ExchangeTab``, and ``fetcher`` is the reader
        ``CryptoNewsTickerModel`` runs.
        """

        def __init__(
            self,
            parent: Optional[QWidget] = None,
            theme: object = None,
            headlines: Optional[list] = None,
            fetcher: Optional[Callable[[], list]] = None,
        ) -> None:
            """Build the strip's own model and seat the stories handed to it."""
            super().__init__(parent)
            self.setAccessibleName(ACCESSIBLE_NAME)
            self._theme = theme
            self._strip = surface.CryptoNewsTickerModel(fetcher=fetcher)
            if headlines:
                self._strip.on_headlines(
                    [surface.headline_from(row) for row in headlines]
                )
            self._models: dict = {}
            self._page_ready = False
            self._stopped = False
            self._web: Any = None
            self._layout = QVBoxLayout(self)
            self._layout.setContentsMargins(0, 0, 0, 0)
            self._layout.setSpacing(0)

        # -- what the exchange header already calls ---------------------------

        def start(self) -> None:
            """Fetch now and start the cycle and the refresh waits."""
            self._strip.start()
            self._run_fetch()
            self._publish()

        def stop(self) -> None:
            """End both waits and the fetch, and take the bridge off the page."""
            self._stopped = True
            self._strip.stop()
            if self._page_ready and self._web is not None:
                self._web.page().runJavaScript(STOP_FEEDS_JS)

        def force_refresh(self) -> None:
            """Start a fetch now, unless one is already running."""
            self._strip.force_refresh()
            self._run_fetch()
            self._publish()

        def _run_fetch(self) -> None:
            """Run the strip's worker, and run none without a ``fetcher``.

            ``on_headlines`` writes ``NO_FEEDS_TEXT`` for an empty answer, so a
            strip with no reader would report no feeds over the stories it holds.
            """
            if self._strip.fetcher is None:
                return
            surface.start_fetch(self._strip)

        def current_headlines(self) -> list:
            """The stories the strip is cycling through."""
            return self._strip.current_headlines()

        # -- what the page reports back ----------------------------------------

        def run_action(self, payload: str) -> None:
            """Answer one bridge call the page made and push the new payload."""
            if self._stopped:
                return
            try:
                asked = json.loads(payload)
            except ValueError:
                logger.warning("News strip page sent a bridge call that is not JSON")
                return
            method = str(asked.get("method") or "")
            params = asked.get("params")
            self._answer(method, params if isinstance(params, dict) else {})
            self._publish()

        # -- the models the page is built from ----------------------------------

        def models(self) -> dict:
            """A copy of the payloads the page was last built or pushed with."""
            return dict(self._models)

        @property
        def page_ready(self) -> bool:
            """True once ``_on_load_finished`` has seen a successful load."""
            return self._page_ready

        def panel_view(self):
            """The web view the strip draws in, or None before the first show."""
            return self._web

        def build_panel(self) -> None:
            """Create the strip's web view and load its page, once."""
            if self._web is not None:
                return
            self._models = self._build_models()
            self._web = QWebEngineView(self)
            self._web.setAccessibleName(ACCESSIBLE_NAME)
            self._web.setPage(TickerPage(self))
            self._web.loadFinished.connect(self._on_load_finished)
            self._web.setHtml(panel_html(self._models, self._theme))
            self._layout.addWidget(self._web, 1)

        def showEvent(self, event) -> None:  # noqa: N802
            """Build the web view the first time the strip is shown."""
            super().showEvent(event)
            self.build_panel()

        # -- internals -----------------------------------------------------------

        def _build_models(self) -> dict:
            """The payload of every bridge method the page's modules ask for."""
            return {
                token_surface.METHOD: token_surface.view_model({}),
                surface.METHOD: surface.build_view_model(self._strip),
            }

        def _answer(self, method: str, params: dict) -> None:
            if method != surface.METHOD:
                return
            rows = params.get("headlines")
            if rows is not None:
                self._strip.on_headlines([surface.headline_from(row) for row in rows])
            if params.get("start", False):
                self.start()
            if params.get("hover") is not None:
                self._strip.handle_event(
                    surface.EVENT_ENTER if params["hover"] else surface.EVENT_LEAVE
                )
            for _step in range(int(params.get("advance", 0))):
                self._strip.advance()
            if params.get("click", False):
                self._strip.handle_event(surface.EVENT_MOUSE_RELEASE)
            if params.get("stop", False):
                self.stop()

        def _publish(self) -> None:
            self._models = self._build_models()
            if self._page_ready and not self._stopped and self._web is not None:
                self._web.page().runJavaScript(push_script(self._models))

        def _on_load_finished(self, ok: bool) -> None:
            self._page_ready = bool(ok)
            if not ok:
                logger.warning("The React news strip page failed to load")
                return
            self._publish()
