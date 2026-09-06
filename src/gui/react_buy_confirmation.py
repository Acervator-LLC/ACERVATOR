# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
"""The buy confirmation modal drawn by React inside ``QWebEngineView``.

``BuyConfirmationReactDialog`` replaces every Qt control ``_setup_ui`` builds and
inherits ``_answer``, ``result_value`` and ``details_text`` unchanged, so the
figures on the page and the answer the broker reads come from the same Python.
``BuyConfirmationPage`` routes a button press on the page back to ``run_action``.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

from .buy_confirmation_dialog import BuyConfirmationDialog
from .main_tabs import buy_confirmation_surface as surface
from .react_history_panel import STYLE_SOURCE_ASSETS, page_html

try:
    from PySide6.QtWebEngineCore import QWebEnginePage
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWidgets import QVBoxLayout

    _HAS_WEBENGINE = True
except ImportError:
    # Without WebEngine the class is never defined and its import fails by name.
    _HAS_WEBENGINE = False

logger = logging.getLogger(surface.LOGGER_NAME)

#: The console line prefix a button press reaches ``run_action`` under.
CALL_PREFIX = "acervator-call:"

#: The element ``buy_confirmation.js`` draws the dialog into.
DIALOG_ROOT_ID = "buy-confirmation-root"

ACCESSIBLE_NAME = "React Buy Confirmation Dialog"

STYLE_ASSET = "buy_confirmation.css"

#: Load order: the style sources parse the Qt sheets before the dialog draws.
DIALOG_SCRIPT_ASSETS: tuple[str, ...] = (
    ("vendor/react.production.min.js", "vendor/react-dom.production.min.js")
    + STYLE_SOURCE_ASSETS
    + ("buy_confirmation.js",)
)

DIALOG_BODY = f'<div id="{DIALOG_ROOT_ID}"></div>'

#: The JS expression reading the banner the browser drew.
BANNER_TEXT_JS = "document.querySelector('[data-part=\"reason-banner\"]').textContent"

#: The JS expression reading the detail rows the browser drew.
DETAIL_ROWS_JS = (
    "Array.from(document.querySelectorAll('[data-part=\"detail-row\"]'))"
    ".map(function (n) { return n.textContent; })"
)

#: The JS expression reading the answer each drawn button carries.
BUTTON_ANSWERS_JS = (
    "Array.from(document.querySelectorAll('[data-part=\"confirm-button\"]'))"
    ".map(function (n) { return n.getAttribute('data-key') + '='"
    " + n.getAttribute('data-answer') + '=' + n.textContent; })"
)

HOST_SCRIPT = """(function (global) {
  "use strict";

  global.acervatorBuyConfirmModel = null;

  global.acervator = {
    call: function (method, params) {
      console.log("%(call)s" + JSON.stringify({ method: method, params: params }));
      return Promise.resolve(global.acervatorBuyConfirmModel);
    }
  };

  global.acervatorBuyConfirmOpen = function (model, fields) {
    global.acervatorBuyConfirmModel = model;
    var root = document.getElementById("%(root)s");
    if (root === null) {
      return false;
    }
    global.acervatorBuyConfirmation.load(root, fields);
    return true;
  };
})(window);""" % {
    "call": CALL_PREFIX,
    "root": DIALOG_ROOT_ID,
}


def dialog_html(theme: str = "cyberpunk_dark") -> str:
    """The whole dialog page as one string, with no network fetch."""
    return page_html(
        (STYLE_ASSET,), DIALOG_SCRIPT_ASSETS, DIALOG_BODY, theme, (HOST_SCRIPT,)
    )


def open_script(model: dict, fields: dict) -> str:
    """The one JS statement that hands ``model`` and ``fields`` to the page."""
    return (
        "window.acervatorBuyConfirmOpen("
        + json.dumps(model, ensure_ascii=True)
        + ", "
        + json.dumps(fields, ensure_ascii=True)
        + ");"
    )


def pressed_button(payload: str) -> str:
    """``yes``, ``no``, ``skip`` or the empty string for a ``CALL_PREFIX`` line."""
    try:
        asked = json.loads(payload)
    except ValueError:
        return ""
    params = asked.get("params")
    if not isinstance(params, dict):
        return ""
    name = params.get("button")
    return name if name in surface.BUTTON_ANSWERS else ""


if _HAS_WEBENGINE:

    class BuyConfirmationPage(QWebEnginePage):
        """Routes the page's ``CALL_PREFIX`` console lines to its owner."""

        def __init__(self, owner) -> None:
            """Hold ``owner`` as the dialog that answers the page."""
            super().__init__(owner)
            self._owner = owner

        def javaScriptConsoleMessage(self, level, message, line, source) -> None:
            """Hand a button press to the owner and drop every other line."""
            del level, line, source
            if message.startswith(CALL_PREFIX):
                self._owner.run_action(pressed_button(message[len(CALL_PREFIX) :]))

    class BuyConfirmationReactDialog(BuyConfirmationDialog):
        """The buy confirmation modal with every control drawn by React."""

        def _setup_ui(self) -> None:
            """Build the one web view the whole dialog is drawn in.

            The window keeps the title, the modality and the minimum width
            ``buy_confirmation_surface`` names for the Qt dialog.
            """
            self._model = surface.BuyConfirmationModel()
            self._page_ready = False

            self.setAccessibleName(ACCESSIBLE_NAME)
            self.result_value = surface.DEFAULT_ANSWER
            self.setWindowTitle(surface.WINDOW_TITLE)
            self.setModal(surface.MODAL)
            self.setMinimumWidth(surface.MINIMUM_WIDTH_PX)
            self.resize(*surface.DEFAULT_SIZE_PX)

            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)
            self._web = QWebEngineView(self)
            self._web_page = BuyConfirmationPage(self)
            self._web.setPage(self._web_page)
            self._web.loadFinished.connect(self._on_load_finished)
            self._web.setHtml(dialog_html())
            layout.addWidget(self._web, 1)

        @property
        def page_ready(self) -> bool:
            """True once ``_on_load_finished`` has seen a successful load."""
            return self._page_ready

        def request_fields(self) -> dict:
            """The values ``surface.DIALOG_FIELDS`` names, off this dialog."""
            return {name: getattr(self, "_" + name) for name in surface.DIALOG_FIELDS}

        def model(self) -> dict:
            """The whole dialog as one payload the page is drawn from."""
            return surface.build_view_model(self._model, **self.request_fields())

        def redraw(self) -> None:
            """Push the payload built from the request to the page."""
            if self._page_ready:
                self._web.page().runJavaScript(
                    open_script(self.model(), self.request_fields())
                )

        def run_action(self, name: str) -> bool:
            """Answer the buy with the button the page reports.

            A name outside ``surface.BUTTON_ANSWERS`` answers False and
            leaves ``result_value`` at the answer it already carries.
            """
            answer = surface.BUTTON_ANSWERS.get(name)
            if answer is None:
                return False
            self._answer(answer)
            return True

        def banner_text(self, callback: Callable[[Any], None]) -> bool:
            """Run ``BANNER_TEXT_JS`` and hand the words to ``callback``.

            Returns False and calls nothing while the page is not ready.
            """
            if not self._page_ready:
                return False
            self._web.page().runJavaScript(BANNER_TEXT_JS, callback)
            return True

        def detail_rows(self, callback: Callable[[Any], None]) -> bool:
            """Run ``DETAIL_ROWS_JS`` and hand the rows to ``callback``.

            Returns False and calls nothing while the page is not ready.
            """
            if not self._page_ready:
                return False
            self._web.page().runJavaScript(DETAIL_ROWS_JS, callback)
            return True

        def _on_load_finished(self, ok: bool) -> None:
            self._page_ready = bool(ok)
            if not ok:
                logger.warning("React buy confirmation page failed to load")
                return
            self.redraw()
