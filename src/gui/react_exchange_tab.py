# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
"""One venue's page drawn by React inside ``QWebEngineView``.

``ExchangeTabReact`` answers the four calls ``MainWindow`` makes on
``ExchangeTab`` -- ``exchange_id``, ``update_bots``, ``stop_feeds`` and
``_refresh_privacy_mode_btn_style`` -- and draws ``src/gui/web/exchange_tab.js``
in place of the Qt controls. ``exchange_tab.js`` mounts ``bot_status_table.js``,
``extractor_bot_table.js`` and ``crypto_news_ticker.js`` into spaces it keeps,
so the two bot tables and the news strip need no host of their own.
``ExchangePage`` carries the page's own bridge calls back to ``run_action``,
and ``page_html`` inlines ``exchange_tab.css`` and every script, so the page
fetches nothing.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from .main_tabs import bot_status_table_surface as scrum_surface
from .main_tabs import crypto_news_ticker_surface as ticker_surface
from .main_tabs import design_system_surface as token_surface
from .main_tabs import exchange_tab_surface as surface
from .main_tabs import extractor_bot_table_surface as extractor_surface
from .react_history_panel import STYLE_SOURCE_ASSETS, page_html, read_asset

try:
    from PySide6.QtCore import QTimer, Signal
    from PySide6.QtWebEngineCore import QWebEnginePage
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWidgets import QVBoxLayout, QWidget

    _HAS_WEBENGINE = True
except ImportError:
    # Without WebEngine, ExchangeTabReact is never defined and its import
    # fails by name.
    _HAS_WEBENGINE = False

logger = logging.getLogger("acervator.gui.react_exchange_tab")

ACCESSIBLE_NAME = "React Exchange Tab"

#: The element ``exchange_tab.js`` draws the venue's page into.
PANEL_ROOT_ID = "exchange-root"

#: The renderer module the page draws.
PANEL_MODULE = "exchange_tab.js"

#: The modules ``exchange_tab.js`` mounts into its own spaces, and the cell
#: module both tables read. Order is load order.
CHILD_MODULES: tuple[str, ...] = (
    "table_cells.js",
    "bot_status_table.js",
    "extractor_bot_table.js",
    "crypto_news_ticker.js",
)

#: The style sheet the page carries.
STYLE_ASSETS: tuple[str, ...] = ("exchange_tab.css",)

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
    "table_cells.js": "acervatorCells",
    "bot_status_table.js": "acervatorBotTable",
    "extractor_bot_table.js": "acervatorExtractorTable",
    "crypto_news_ticker.js": "acervatorTicker",
    PANEL_MODULE: "acervatorExchangeTab",
}

#: The setter each module publishes for the payload of its own method.
METHOD_SETTERS: dict[str, str] = {
    token_surface.METHOD: "acervatorSetTokens",
    scrum_surface.METHOD: "acervatorSetBotTable",
    extractor_surface.METHOD: "acervatorSetExtractorTable",
    ticker_surface.METHOD: "acervatorSetTicker",
    surface.METHOD: "acervatorSetExchangeTab",
}

#: The console line the page writes a bridge call on.
ACTION_PREFIX = "acervator-exchange:"

#: The JS expression naming every module whose global reached the page.
LOADED_MODULES_JS = "window.acervatorExchangePage.modules().join(',')"

#: The JS expression naming each style sheet the page holds and its rule count.
LOADED_STYLES_JS = "JSON.stringify(window.acervatorExchangePage.styles())"

#: The JS expression counting the bot rows each table space really drew.
DRAWN_ROWS_JS = "JSON.stringify(window.acervatorExchangePage.rows())"

#: The JS statement that takes the bridge away, which stops every page timer.
STOP_FEEDS_JS = "window.acervatorExchangePage.stop();"

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
  var ROW = %(row)s;
  var SPACES = %(spaces)s;

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
    var api = global.acervatorExchangeTab;
    var node = doc.getElementById(ROOT);
    if (!api || typeof api.renderTab !== "function" || node === null) {
      return false;
    }
    api.renderTab(node, owns(MODELS, METHOD) ? MODELS[METHOD] : null);
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

  function rows() {
    var found = {};
    SPACES.forEach(function (part) {
      found[part] = doc.querySelectorAll(part + " " + ROW).length;
    });
    return found;
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

  global.acervatorExchangePage = {
    modules: modules,
    styles: styles,
    rows: rows,
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
  global.acervatorExchangePageDrawn = draw();
})(window, document);"""


def roster() -> tuple[str, ...]:
    """Every module the page carries, in load order.

    ``STYLE_SOURCE_ASSETS`` leads: ``exchange_tab.js`` parses every Qt style
    sheet in its payload with ``header_strip.styleOf``.
    """
    return STYLE_SOURCE_ASSETS + CHILD_MODULES + (PANEL_MODULE,)


def module_globals() -> list:
    """Each module the page carries beside the global it defines when it runs."""
    return [[name, MODULE_GLOBALS[name]] for name in roster()]


def method_setters() -> list:
    """Each bridge method the page answers beside that module's own setter."""
    return [
        [method, METHOD_SETTERS[method]]
        for method in (
            token_surface.METHOD,
            scrum_surface.METHOD,
            extractor_surface.METHOD,
            ticker_surface.METHOD,
            surface.METHOD,
        )
    ]


def table_spaces() -> list:
    """The selector of each space a bot table draws its own rows into."""
    return ['[data-part="scrum-table"]', '[data-part="extractor-table"]']


def host_script(built: dict) -> str:
    """The page's own glue: the models, the roster and the one page to draw."""
    return _HOST_SOURCE % {
        "models": json.dumps(built, ensure_ascii=True),
        "setters": json.dumps(method_setters(), ensure_ascii=True),
        "globals": json.dumps(module_globals(), ensure_ascii=True),
        "method": json.dumps(surface.METHOD, ensure_ascii=True),
        "root": json.dumps(PANEL_ROOT_ID, ensure_ascii=True),
        "prefix": json.dumps(ACTION_PREFIX, ensure_ascii=True),
        "asset": json.dumps("data-asset", ensure_ascii=True),
        "row": json.dumps('[data-part="row"]', ensure_ascii=True),
        "spaces": json.dumps(table_spaces(), ensure_ascii=True),
        "roster": json.dumps(list(roster()), ensure_ascii=True),
    }


def _tag(source: str) -> str:
    """``source`` wrapped in a script tag of its own."""
    return "<script>" + source + "</script>"


def page_body() -> str:
    """The page's body: the named style sheets, the root, React, the modules.

    Each style sheet carries its own ``data-asset`` name, so ``styles`` can
    report which sheet the page holds and how many rules that sheet gave it.
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
    """The whole venue page as one string, with no network fetch."""
    return page_html((), (), page_body(), theme, (host_script(built),))


def push_script(built: dict) -> str:
    """The one JS statement handing the page a fresh payload for each method.

    ``ensure_ascii=True`` escapes U+2028 and U+2029, which are legal inside a
    JSON string and are JavaScript line terminators.
    """
    body = json.dumps(built, ensure_ascii=True)
    return "window.acervatorExchangePage.hold(" + body + ");"


def bind_news_transport() -> bool:
    """Hand the news strip the reader ``desktop_bridge`` gives it, once.

    ``crypto_news_ticker_surface.use_fetch`` takes the transport its worker
    reads a feed body with, and the strip answers with no story without one.
    """
    import time

    try:
        from ..core.safe_url import SafeRequest, safe_urlopen
    except ImportError as exc:
        logger.debug("news feed reader not imported: %s", exc)
        return False
    ticker_surface.use_fetch(SafeRequest, safe_urlopen, time.monotonic)
    return True


def data_pool_summary() -> Optional[dict]:
    """The shared market cache's own freshness report, or None when unreadable.

    ``ExchangeTabModel.update_pull_rate_label`` reads this for the line under
    the "+ New Bot" button.
    """
    try:
        from ..exchange.data_pool import get_data_pool

        return get_data_pool().pull_rate_summary()
    except Exception as exc:
        logger.debug("data pool freshness not read: %s", exc)
        return None


if _HAS_WEBENGINE:

    class ExchangePage(QWebEnginePage):
        """Routes the page's ``acervator-exchange:`` console lines to its owner."""

        def __init__(self, owner) -> None:
            """Hold ``owner`` as the widget that answers the page."""
            super().__init__(owner)
            self._owner = owner

        def javaScriptConsoleMessage(self, level, message, line, source) -> None:
            """Hand a bridge call to the owner and drop every other line."""
            del level, line, source
            if message.startswith(ACTION_PREFIX):
                self._owner.run_action(message[len(ACTION_PREFIX) :])

    class ExchangeTabReact(QWidget):
        """One venue's page, drawn by ``exchange_tab.js`` and its four modules.

        ``build_panel`` loads the page once on the first show, and
        ``update_bots``, ``stop_feeds`` and ``_refresh_privacy_mode_btn_style``
        answer the calls ``MainWindow`` already makes on ``ExchangeTab``.
        ``published`` carries each rebuilt payload to whatever else draws
        this venue, which under the React build is ``TradingTabReact``.
        """

        published = Signal()

        def __init__(
            self,
            exchange_id: str,
            exchange_name: str,
            on_new_bot=None,
            on_bot_clicked=None,
            on_bot_cmd=None,
            on_bot_fire=None,
            status_log=None,
            parent: Optional[QWidget] = None,
            theme: object = None,
            on_bot_selected=None,
            on_fleet_cmd=None,
        ) -> None:
            """Build the venue's three surface models from the window's wiring."""
            super().__init__(parent)
            self.setAccessibleName(ACCESSIBLE_NAME)
            self.exchange_id = exchange_id
            self.exchange_name = exchange_name
            self._theme = theme
            self._screen = surface.ExchangeTabModel(
                exchange_id,
                exchange_name,
                on_new_bot=on_new_bot,
                on_bot_clicked=on_bot_clicked,
                on_bot_cmd=on_bot_cmd,
                on_fleet_cmd=on_fleet_cmd,
                on_bot_fire=on_bot_fire,
                status_log=status_log,
                news_ticker_factory=surface.react_news_ticker,
                pool_reader=data_pool_summary,
                window_refresh=self._refresh_window_privacy,
            )
            self._scrum = scrum_surface.BotStatusTableModel(
                on_bot_clicked=self._scrum_detail,
                on_fire_clicked=on_bot_fire,
                on_bot_selected=on_bot_selected,
            )
            self._scrum.exchange_id = exchange_id
            self._extractor = extractor_surface.ExtractorBotTableModel(
                on_bot_clicked=self._extractor_detail,
            )
            self._extractor.exchange_id = exchange_id
            self._models: dict = {}
            self._news_asked = False
            self._page_ready = False
            self._stopped = False
            self._web: Any = None
            self._layout = QVBoxLayout(self)
            self._layout.setContentsMargins(0, 0, 0, 0)
            self._layout.setSpacing(0)
            self._pull_rate_timer = QTimer(self)
            self._pull_rate_timer.setInterval(surface.PULL_RATE_INTERVAL_MS)
            self._pull_rate_timer.timeout.connect(self._update_pull_rate_label)
            self._pull_rate_timer.start()

        # -- what the window already calls --------------------------------

        def _update_pull_rate_label(self) -> None:
            """Rewrite the data-pool line from ``data_pool_summary`` and publish it.

            The Qt venue page runs the same read on its own
            ``PULL_RATE_INTERVAL_MS`` timer.
            """
            if self._stopped:
                return
            self._screen.update_pull_rate_label()
            self._publish()

        def update_bots(self, statuses: list) -> None:
            """Route one fleet list to the screen and to both bot tables."""
            surface.drive(self._screen, {surface.STATUSES_PARAM: statuses})
            scrum_surface.drive(
                self._scrum,
                {
                    scrum_surface.STATUSES_PARAM: scrum_surface.scrumming_statuses(
                        statuses
                    )
                },
            )
            extractor_surface.drive(
                self._extractor,
                {
                    extractor_surface.ACTION_PARAM: extractor_surface.UPDATE_ACTION,
                    extractor_surface.BOT_STATUSES_PARAM: (
                        extractor_surface.extractor_statuses(statuses)
                    ),
                },
            )
            self._publish()

        def stop_feeds(self) -> None:
            """Take the bridge off the page, which stops every timer it runs."""
            self._stopped = True
            self._pull_rate_timer.stop()
            if self._page_ready and self._web is not None:
                self._web.page().runJavaScript(STOP_FEEDS_JS)

        def toggle_privacy(self, column: Any) -> None:
            """Hide or show one bot-table column, then publish the fleet again.

            ``TradingTabReact.run_action`` calls this when the dot under a
            column's label is pressed on the Live page.
            """
            scrum_surface.drive(
                self._scrum, {scrum_surface.PRIVACY_TOGGLE_PARAM: column}
            )
            self._publish()

        def sort_by(self, column: Any) -> None:
            """Order the bot table by one column, then publish the fleet again.

            ``TradingTabReact.run_action`` calls this when a column heading
            is pressed on the Live page.
            """
            scrum_surface.drive(self._scrum, {scrum_surface.SORT_COLUMN_PARAM: column})
            self._publish()

        def select_bot(self, bot_id: Any) -> None:
            """Answer a press on one bot row, then publish the fleet again.

            ``TradingTabReact.run_action`` calls this when a row is pressed
            on the Live page, and the model's ``on_bot_selected`` carries the
            bot to the window's Voting Panel.
            """
            scrum_surface.drive(self._scrum, {scrum_surface.SELECT_BOT_PARAM: bot_id})
            self._publish()

        def press_command(self, command: Any, shift_held: Any = False) -> None:
            """Send one command-bar press on, then publish the fleet again.

            ``TradingTabReact.run_action`` calls this; the bar acts on the bot
            the drawn list holds, or on the whole fleet while SHIFT is held.
            """
            self._screen.hold_scrum_bot(self._scrum.get_selected_bot_id())
            self._screen.cmd(str(command or ""), bool(shift_held))
            self._publish()

        def highlight_bot(self, bot_id: Any) -> str:
            """Put the bot table's highlight on the Voting Panel's bot.

            ``BotListPanelLink.panel_selected`` calls this, which is why it
            drives ``highlight_bot`` and not the press.
            """
            found = self._scrum.highlight_bot(str(bot_id or ""))
            self._publish()
            return found

        def _refresh_privacy_mode_btn_style(self) -> None:
            """Rewrite the Privacy Mode button from the register's own answer."""
            self._screen.refresh_privacy_mode_btn_style()
            self._scrum.refresh_header_dots()
            self._publish()

        # -- what the page reports back ------------------------------------

        def run_action(self, payload: str) -> None:
            """Answer one bridge call the page made and push the new payloads."""
            if self._stopped:
                return
            try:
                asked = json.loads(payload)
            except ValueError:
                logger.warning("Exchange page sent a bridge call that is not JSON")
                return
            method = str(asked.get("method") or "")
            params = asked.get("params")
            self._answer(method, params if isinstance(params, dict) else {})
            self._publish()

        # -- the models the page is built from -----------------------------

        def models(self) -> dict:
            """A copy of the payloads the page was last built or pushed with."""
            return dict(self._models)

        @property
        def page_ready(self) -> bool:
            """True once ``_on_load_finished`` has seen a successful load."""
            return self._page_ready

        def panel_view(self):
            """The web view the page draws in, or None before the first show."""
            return self._web

        def build_panel(self) -> None:
            """Create the venue's web view and load its page, once."""
            if self._web is not None:
                return
            self._models = self._build_models()
            self._web = QWebEngineView(self)
            self._web.setAccessibleName(ACCESSIBLE_NAME)
            self._web.setPage(ExchangePage(self))
            self._web.loadFinished.connect(self._on_load_finished)
            self._web.setHtml(panel_html(self._models, self._theme))
            self._layout.addWidget(self._web, 1)

        def showEvent(self, event) -> None:  # noqa: N802
            """Build the web view the first time the venue's page is shown."""
            super().showEvent(event)
            self.build_panel()

        # -- internals ------------------------------------------------------

        def _build_models(self) -> dict:
            """The payload of every bridge method the page's modules ask for."""
            return {
                token_surface.METHOD: token_surface.view_model({}),
                surface.METHOD: surface.build_view_model(self._screen),
                scrum_surface.METHOD: scrum_surface.build_view_model(self._scrum),
                extractor_surface.METHOD: extractor_surface.build_payload(
                    self._extractor
                ),
                ticker_surface.METHOD: self._news_model(),
            }

        def _news_model(self) -> dict:
            """The news strip's payload, started against its feeds on the first ask."""
            if self._news_asked:
                return ticker_surface.view_model({})
            self._news_asked = True
            bind_news_transport()
            return ticker_surface.view_model({"start": True})

        def _answer(self, method: str, params: dict) -> None:
            if method == surface.METHOD:
                # The command bar reads _screen.scrum_table; the row press
                # reaches _scrum.
                self._screen.hold_scrum_bot(self._scrum.get_selected_bot_id())
                surface.drive(self._screen, params)
            elif method == scrum_surface.METHOD:
                scrum_surface.drive(self._scrum, params)
            elif method == extractor_surface.METHOD:
                extractor_surface.drive(self._extractor, params)
            elif method == ticker_surface.METHOD:
                ticker_surface.view_model(params)

        def _publish(self) -> None:
            self._models = self._build_models()
            if self._page_ready and not self._stopped and self._web is not None:
                self._web.page().runJavaScript(push_script(self._models))
            self.published.emit()

        def _row_of(self, table, bot_id: str) -> int:
            ids = list(table.bot_ids)
            return ids.index(bot_id) if bot_id in ids else surface.NO_SELECTION_ROW

        def _scrum_detail(self, bot_id: str) -> None:
            self._screen.select_scrum_row(
                self._row_of(self._screen.scrum_table, bot_id)
            )
            self._screen.scrum_clicked(bot_id)

        def _extractor_detail(self, bot_id: str) -> None:
            self._screen.select_extractor_row(
                self._row_of(self._screen.extractor_table, bot_id)
            )
            self._screen.extractor_clicked(bot_id)

        def _refresh_window_privacy(self) -> None:
            root = self.window()
            refresh = getattr(root, "refresh_all_privacy_widgets", None)
            if callable(refresh):
                refresh()

        def _on_load_finished(self, ok: bool) -> None:
            self._page_ready = bool(ok)
            if not ok:
                logger.warning("The React exchange page failed to load")
                return
            self._publish()
