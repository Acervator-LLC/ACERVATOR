# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
"""The header spendable-profits strip drawn by React inside ``QWebEngineView``.

``SpendableProfitsReact`` answers the ``update_profits`` and
``refresh_privacy_dots`` calls ``SpendableProfitsWidget`` answers and writes
them into ``SpendableProfitsModel``. Each column's dot is
``privacy_dot_surface.PrivacyDotModel``, so a press on the page runs the same
registry flip the Qt dot runs.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

from .main_tabs import privacy_dot_surface as dot_surface
from .main_tabs import spendable_profits_surface as surface
from .react_history_panel import STYLE_SOURCE_ASSETS, page_html
from .widgets.spendable_profits import SpendableProfitsWidget, _HAS_QT

try:
    from PySide6.QtWebEngineCore import QWebEnginePage
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWidgets import QVBoxLayout

    _HAS_WEBENGINE = True
except ImportError:
    # Without WebEngine the class is never defined and its import fails by name.
    _HAS_WEBENGINE = False

logger = logging.getLogger("acervator.gui.react_spendable_profits")

#: The console line prefix a dot press reaches ``press_field`` under.
CALL_PREFIX = "acervator-call:"

#: The element ``spendable_profits.js`` draws the strip into.
STRIP_ROOT_ID = "spendable-profits-root"

ACCESSIBLE_NAME = "React Spendable Profits"

#: The height the strip asks for, matching the Qt columns it replaces.
STRIP_HEIGHT_PX = 72

#: The scripts the page carries. Order is load order: the style sources
#: parse the Qt sheets, then ``privacy_dot.js`` draws each column's dot.
STRIP_SCRIPT_ASSETS: tuple[str, ...] = (
    ("vendor/react.production.min.js", "vendor/react-dom.production.min.js")
    + STYLE_SOURCE_ASSETS
    + ("privacy_dot.js", "spendable_profits.js")
)

STRIP_BODY = f'<div id="{STRIP_ROOT_ID}"></div>'

#: The JS expression reading the five amounts the browser drew.
VALUE_TEXTS_JS = (
    "Array.from(document.querySelectorAll('[data-part=\"column-value\"]'))"
    ".map(function (n) { return n.textContent; })"
)

#: The JS expression reading the five dot glyphs the browser drew.
DOT_GLYPHS_JS = (
    "Array.from(document.querySelectorAll('[data-part=\"column-dot\"]'))"
    ".map(function (n) { return n.textContent; })"
)

HOST_SCRIPT = """(function (global) {
  "use strict";

  global.acervator = {
    call: function (method, params) {
      console.log("%(call)s" + JSON.stringify({ method: method, params: params }));
      return Promise.resolve(null);
    }
  };

  global.acervatorProfitsDraw = function (model) {
    global.acervatorSetProfits(model);
    return (
      global.acervatorProfits.renderStrip(
        document.getElementById("%(root)s"),
        null
      ) !== null
    );
  };
})(window);""" % {
    "call": CALL_PREFIX,
    "root": STRIP_ROOT_ID,
}


def strip_html(theme: object = None) -> str:
    """The whole strip page as one string, with no network fetch."""
    return page_html((), STRIP_SCRIPT_ASSETS, STRIP_BODY, theme, (HOST_SCRIPT,))


def draw_script(model: dict) -> str:
    """The one JS statement that hands ``model`` to the page."""
    return "window.acervatorProfitsDraw(" + json.dumps(model, ensure_ascii=True) + ");"


def press_field(payload: str) -> Any:
    """The ``field_id`` a ``CALL_PREFIX`` console line asks for, or None."""
    try:
        asked = json.loads(payload)
    except ValueError:
        return None
    if asked.get("method") != dot_surface.METHOD:
        return None
    params = asked.get("params")
    return params.get("field_id") if isinstance(params, dict) else None


if _HAS_QT and _HAS_WEBENGINE:

    class SpendableProfitsPage(QWebEnginePage):
        """Routes the page's ``CALL_PREFIX`` console lines to its owner."""

        def __init__(self, owner) -> None:
            """Hold ``owner`` as the strip that answers the page."""
            super().__init__(owner)
            self._owner = owner

        def javaScriptConsoleMessage(self, level, message, line, source) -> None:
            """Hand a dot press to the owner and drop every other line."""
            del level, line, source
            if message.startswith(CALL_PREFIX):
                self._owner.dot_pressed(press_field(message[len(CALL_PREFIX) :]))

    class SpendableProfitsReact(SpendableProfitsWidget):
        """The five KPI columns and their dots, drawn by React.

        ``update_profits`` and ``refresh_privacy_dots`` are the two calls
        the main window makes, and both redraw the page.
        """

        def _setup_ui(self) -> None:
            """Build the one web view the whole strip is drawn in."""
            self._model = surface.SpendableProfitsModel()
            self._dots = {
                column["field_id"]: dot_surface.PrivacyDotModel(
                    column["field_id"], on_toggle=self._model.privacy_toggled
                )
                for column in surface.COLUMNS
            }
            self._page_ready = False
            self.setAccessibleName(ACCESSIBLE_NAME)
            self.setMinimumHeight(STRIP_HEIGHT_PX)
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)
            self._web = QWebEngineView(self)
            self._web_page = SpendableProfitsPage(self)
            self._web.setPage(self._web_page)
            self._web.loadFinished.connect(self._on_load_finished)
            self._web.setHtml(strip_html())
            layout.addWidget(self._web, 1)

        @property
        def page_ready(self) -> bool:
            """True once ``_on_load_finished`` has seen a successful load."""
            return self._page_ready

        def model(self) -> dict:
            """The whole strip as one payload, dots and all.

            Each column's dot is the payload ``privacy_dot_surface``
            publishes, so the page draws it with ``privacy_dot.js``.
            """
            found = surface.build_view_model(self._model)
            for column in found["columns"]:
                held = self._dots.get(column["field_id"])
                if held is not None:
                    column["dot"] = dot_surface.build_view_model(held)
            return found

        def update_profits(self, data: dict) -> None:
            """Draw every column from one payload, then keep that payload."""
            self._model.update_profits(data)
            self._push()

        def refresh_privacy_dots(self) -> None:
            """Repaint every dot, then re-draw the kept payload."""
            for held in self._dots.values():
                held.refresh()
            self._model.refresh_privacy_dots()
            self._push()

        def dot_pressed(self, field_id: Any) -> bool:
            """Click the dot the page names and redraw. False for no dot."""
            held = self._dots.get(field_id)
            if held is None:
                return False
            held.clicked()
            self._push()
            return True

        def values(self, callback: Callable[[Any], None]) -> bool:
            """Run ``VALUE_TEXTS_JS`` and hand the five amounts to ``callback``.

            Returns False and calls nothing while the page is not ready.
            """
            if not self._page_ready:
                return False
            self._web.page().runJavaScript(VALUE_TEXTS_JS, callback)
            return True

        def glyphs(self, callback: Callable[[Any], None]) -> bool:
            """Run ``DOT_GLYPHS_JS`` and hand the five glyphs to ``callback``.

            Returns False and calls nothing while the page is not ready.
            """
            if not self._page_ready:
                return False
            self._web.page().runJavaScript(DOT_GLYPHS_JS, callback)
            return True

        def _push(self) -> None:
            if self._page_ready:
                self._web.page().runJavaScript(draw_script(self.model()))

        def _on_load_finished(self, ok: bool) -> None:
            self._page_ready = bool(ok)
            if not ok:
                logger.warning("React spendable profits page failed to load")
                return
            self._push()
