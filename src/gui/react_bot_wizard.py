# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
"""The Create Auto Trader wizard drawn by React inside ``QWebEngineView``.

``BotWizardReactDialog`` answers the four calls ``main_window._create_bot``
makes on ``BotCreationWizard``: construction with the venue list and the
stored defaults, ``exec``, ``DialogCode`` and ``get_bot_config``.
``src/gui/web/bot_wizard.js`` draws every page from the ``bot_wizard.state``
payload ``bot_wizard_surface.view_model`` builds, and ``BotWizardPage``
routes the page's own action lines back into Python. The venue list, the
market list and the stored defaults are all arguments, so nothing here opens
a connection, reads a credential or creates a bot.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Optional

from .main_tabs import bot_wizard_surface as surface
from .react_history_panel import STYLE_SOURCE_ASSETS, page_html

try:
    from PySide6.QtWebEngineCore import QWebEnginePage
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWidgets import QDialog, QVBoxLayout

    _HAS_WEBENGINE = True
except ImportError:
    # Without WebEngine the class is never defined and its import fails by name.
    _HAS_WEBENGINE = False

logger = logging.getLogger(surface.LOGGER_NAME)

ACCESSIBLE_NAME = "React Bot Creation Wizard"

#: The console line prefix a page action reaches ``answer_call`` under.
CALL_PREFIX = "acervator-call:"

#: The element ``bot_wizard.js`` finds its own drawing space by.
WIZARD_SPACE_PART = "bot-wizard-page"

STYLE_ASSET = "bot_wizard.css"

#: The module giving ``bot_wizard.js`` the ``acervatorCells`` colour reading.
CELLS_ASSET = "table_cells.js"

WIZARD_ASSET = "bot_wizard.js"

#: Load order: React, the four style sources, then the cells and the wizard.
WIZARD_SCRIPT_ASSETS: tuple[str, ...] = (
    ("vendor/react.production.min.js", "vendor/react-dom.production.min.js")
    + STYLE_SOURCE_ASSETS
    + (CELLS_ASSET, WIZARD_ASSET)
)

#: The global each asset defines once its script tag has run.
MODULE_GLOBALS: dict[str, str] = {
    "vendor/react.production.min.js": "React",
    "vendor/react-dom.production.min.js": "ReactDOM",
    "design_tokens.js": "acervatorTokens",
    "theme_engine.js": "acervatorThemes",
    "shared_widgets.js": "acervatorWidgets",
    "header_strip.js": "acervatorHeader",
    CELLS_ASSET: "acervatorCells",
    WIZARD_ASSET: "acervatorBotWizard",
}

WIZARD_BODY = f'<div data-part="{WIZARD_SPACE_PART}"></div>'

#: The JS expression reading which module globals the page carries.
LOADED_MODULES_JS = "JSON.stringify(window.acervatorBotWizardModules());"

#: The JS expression reading the sheets and the rules the page parsed.
LOADED_STYLES_JS = "JSON.stringify(window.acervatorBotWizardStyles());"

#: The JS expression naming every payload fault ``bot_wizard.js`` found.
WIZARD_FAULTS_JS = "JSON.stringify(window.acervatorBotWizard.faults());"

#: The JS expression reading the page stops the browser drew.
RAIL_STOPS_JS = (
    "JSON.stringify(Array.from("
    "document.querySelectorAll('[data-part=\"page-rail-stop\"]'))"
    ".map(function (n) { return n.getAttribute('data-name') + '='"
    " + n.getAttribute('data-current') + '=' + n.textContent; }));"
)

#: The JS expression reading the field rows the browser drew.
DRAWN_ROWS_JS = (
    "JSON.stringify(Array.from("
    "document.querySelectorAll('[data-part=\"field-row\"]'))"
    ".map(function (n) { return n.getAttribute('data-name') + '='"
    " + n.textContent; }));"
)

#: The JS expression reading the unit notes the browser drew.
UNIT_NOTES_JS = (
    "JSON.stringify(Array.from("
    "document.querySelectorAll('[data-part=\"unit-note\"]'))"
    ".map(function (n) { return n.getAttribute('data-name') + '='"
    " + n.textContent; }));"
)

#: The class ``bot_wizard.js`` puts on the one element it owns.
WIZARD_CLASS = "acervator-bot-wizard"

HOST_SCRIPT = """(function (global) {
  "use strict";

  var MODULES = %(modules)s;
  var SPACE = "%(space)s";
  var WIZARD_CLASS = "%(wizard_class)s";
  var kept = {};
  var nextId = 0;

  global.acervator = {
    call: function (method, params) {
      nextId = nextId + 1;
      var id = nextId;
      var held = new Promise(function (keep) {
        kept[id] = keep;
      });
      console.log(
        "%(call)s" + JSON.stringify({ id: id, method: method, params: params })
      );
      return held;
    }
  };

  global.acervatorBotWizardAnswer = function (id, model) {
    var keep = kept[id];
    if (keep === undefined) {
      return false;
    }
    delete kept[id];
    keep(model);
    return true;
  };

  global.acervatorBotWizardOpen = function (model) {
    var space = document.querySelector('[data-part="' + SPACE + '"]');
    if (space === null) {
      return false;
    }
    return global.acervatorBotWizard.fill(space, model, null) !== null;
  };

  global.acervatorBotWizardModules = function () {
    var found = {};
    Object.keys(MODULES).forEach(function (asset) {
      found[asset] = global[MODULES[asset]] !== undefined;
    });
    return found;
  };

  global.acervatorBotWizardStyles = function () {
    var sheets = Array.prototype.slice.call(document.styleSheets);
    var rules = 0;
    var mine = 0;
    sheets.forEach(function (sheet) {
      var found = Array.prototype.slice.call(sheet.cssRules);
      rules = rules + found.length;
      found.forEach(function (rule) {
        var text = rule.selectorText;
        if (text !== undefined && text.indexOf(WIZARD_CLASS) >= 0) {
          mine = mine + 1;
        }
      });
    });
    return { sheets: sheets.length, rules: rules, wizard_rules: mine };
  };
})(window);""" % {
    "call": CALL_PREFIX,
    "space": WIZARD_SPACE_PART,
    "wizard_class": WIZARD_CLASS,
    "modules": json.dumps(MODULE_GLOBALS, ensure_ascii=True),
}


def dialog_html(theme: object = None) -> str:
    """The whole wizard page as one string, with no network fetch."""
    return page_html(
        (STYLE_ASSET,), WIZARD_SCRIPT_ASSETS, WIZARD_BODY, theme, (HOST_SCRIPT,)
    )


def open_script(model: dict) -> str:
    """The one JS statement that hands ``model`` to the page."""
    return (
        "window.acervatorBotWizardOpen(" + json.dumps(model, ensure_ascii=True) + ");"
    )


def answer_script(call_id: int, model: dict) -> str:
    """The one JS statement answering the page's ``call_id`` with ``model``."""
    return (
        "window.acervatorBotWizardAnswer("
        + json.dumps(call_id, ensure_ascii=True)
        + ", "
        + json.dumps(model, ensure_ascii=True)
        + ");"
    )


def read_call(payload: str) -> Optional[tuple]:
    """The ``call_id`` and the steps a ``CALL_PREFIX`` line carries, or None.

    A line naming a method other than ``bot_wizard.state``, or carrying no
    whole-number id, is not the wizard's and answers None.
    """
    try:
        asked = json.loads(payload)
    except ValueError:
        return None
    if not isinstance(asked, dict) or asked.get("method") != surface.METHOD:
        return None
    call_id = asked.get("id")
    if type(call_id) is not int:
        return None
    params = asked.get("params")
    return call_id, params if isinstance(params, dict) else {}


if _HAS_WEBENGINE:

    class BotWizardPage(QWebEnginePage):
        """Routes the page's ``CALL_PREFIX`` console lines to its owner."""

        def __init__(self, owner) -> None:
            """Hold ``owner`` as the dialog that answers the page."""
            super().__init__(owner)
            self._owner = owner

        def javaScriptConsoleMessage(self, level, message, line, source) -> None:
            """Hand one page action to the owner and log every other line."""
            del source
            if message.startswith(CALL_PREFIX):
                self._owner.answer_call(message[len(CALL_PREFIX) :])
                return
            logger.debug("bot wizard page line %s at %s: %s", level, line, message)

    class BotWizardReactDialog(QDialog):
        """The Create Auto Trader wizard with every page drawn by React.

        ``markets`` and ``timeframes`` carry the venue data the pages list, so
        the dialog reaches no exchange of its own.
        """

        def __init__(
            self,
            exchanges: Any = None,
            defaults: Any = None,
            parent: Any = None,
            theme: object = None,
            markets: Any = None,
            timeframes: Any = None,
            sector: Any = "",
        ) -> None:
            """Hold the venue list, the defaults and the sector the payload is
            built from, ``sector`` being the layer New Bot was pressed on."""
            super().__init__(parent)
            self._exchanges = exchanges
            self._defaults = defaults
            self._markets = markets
            self._timeframes = timeframes
            self._sector = surface.normalise_sector(sector)
            self._steps: dict = {}
            self._page_ready = False
            self._payload = self.model()

            self.setAccessibleName(ACCESSIBLE_NAME)
            self.setAccessibleDescription(surface.ACCESSIBLE_DESCRIPTION)
            self.setWindowTitle(surface.WINDOW_TITLE)
            self.setMinimumSize(*surface.MINIMUM_SIZE_PX)
            self.resize(*surface.OPENING_SIZE_PX)

            layout = QVBoxLayout(self)
            layout.setContentsMargins(*surface.OUTER_MARGINS)
            layout.setSpacing(surface.OUTER_SPACING_PX)
            self._web = QWebEngineView(self)
            self._web.setAccessibleName(ACCESSIBLE_NAME)
            self._web_page = BotWizardPage(self)
            self._web.setPage(self._web_page)
            self._web.loadFinished.connect(self._on_load_finished)
            self._web.setHtml(dialog_html(theme))
            layout.addWidget(self._web, 1)

        @property
        def page_ready(self) -> bool:
            """True once ``_on_load_finished`` has seen a successful load."""
            return self._page_ready

        def panel_view(self):
            """The web view the wizard is drawn in."""
            return self._web

        def model(self, steps: Any = None) -> dict:
            """The whole wizard as one payload, built from ``steps``.

            The venue list, the defaults, the markets, the offered timeframes
            and the sector are put in around the steps the page sends.
            """
            asked = dict(steps or {})
            asked.setdefault("exchanges", self._exchanges)
            asked.setdefault("defaults", self._defaults)
            asked.setdefault("markets", self._markets)
            asked.setdefault("timeframes", self._timeframes)
            asked.setdefault("sector", self._sector)
            return surface.view_model(asked)

        def payload(self) -> dict:
            """The payload the page was last drawn from."""
            return dict(self._payload)

        def steps(self) -> dict:
            """The steps the page last sent, which is what it has been told."""
            return dict(self._steps)

        def get_bot_config(self) -> dict:
            """The settings the new bot is created from."""
            return dict(self._payload.get("config") or {})

        def answer_call(self, payload: str) -> bool:
            """Answer one page action with a freshly built payload.

            Rebuilds the model from the steps the page sends, hands it back
            through ``answer_script`` and calls ``close_on`` with it.
            """
            asked = read_call(payload)
            if asked is None:
                return False
            call_id, steps = asked
            self._steps = steps
            self._payload = self.model(steps)
            self._web.page().runJavaScript(answer_script(call_id, self._payload))
            self.close_on(self._payload)
            return True

        def close_on(self, payload: dict) -> str:
            """Accept on a finished walk, reject on a cancelled one."""
            walk = payload.get("walk") or {}
            outcome = walk.get("outcome")
            if outcome == surface.OUTCOME_FINISHED:
                self.accept()
            elif outcome == surface.OUTCOME_CANCELLED:
                self.reject()
            return str(outcome or "")

        def redraw(self, steps: Any = None) -> bool:
            """Rebuild the payload from ``steps`` and push it to the page."""
            if not self._page_ready:
                return False
            if steps is not None:
                self._steps = dict(steps)
            self._payload = self.model(self._steps)
            self._web.page().runJavaScript(open_script(self._payload))
            return True

        def loaded_modules(self, callback: Callable[[Any], None]) -> bool:
            """Run ``LOADED_MODULES_JS`` and hand the answer to ``callback``.

            Returns False and calls nothing while the page is not ready.
            """
            if not self._page_ready:
                return False
            self._web.page().runJavaScript(LOADED_MODULES_JS, callback)
            return True

        def loaded_styles(self, callback: Callable[[Any], None]) -> bool:
            """Run ``LOADED_STYLES_JS`` and hand the answer to ``callback``.

            Returns False and calls nothing while the page is not ready.
            """
            if not self._page_ready:
                return False
            self._web.page().runJavaScript(LOADED_STYLES_JS, callback)
            return True

        def wizard_faults(self, callback: Callable[[Any], None]) -> bool:
            """Run ``WIZARD_FAULTS_JS`` and hand the faults to ``callback``."""
            if not self._page_ready:
                return False
            self._web.page().runJavaScript(WIZARD_FAULTS_JS, callback)
            return True

        def rail_stops(self, callback: Callable[[Any], None]) -> bool:
            """Run ``RAIL_STOPS_JS`` and hand the drawn stops to ``callback``."""
            if not self._page_ready:
                return False
            self._web.page().runJavaScript(RAIL_STOPS_JS, callback)
            return True

        def drawn_rows(self, callback: Callable[[Any], None]) -> bool:
            """Run ``DRAWN_ROWS_JS`` and hand the drawn rows to ``callback``."""
            if not self._page_ready:
                return False
            self._web.page().runJavaScript(DRAWN_ROWS_JS, callback)
            return True

        def drawn_unit_notes(self, callback: Callable[[Any], None]) -> bool:
            """Run ``UNIT_NOTES_JS`` and hand the drawn unit notes to
            ``callback``, which reads the text the browser drew."""
            if not self._page_ready:
                return False
            self._web.page().runJavaScript(UNIT_NOTES_JS, callback)
            return True

        def _on_load_finished(self, ok: bool) -> None:
            self._page_ready = bool(ok)
            if not ok:
                logger.warning("The React bot wizard page failed to load")
                return
            self._web.page().runJavaScript(open_script(self._payload))
