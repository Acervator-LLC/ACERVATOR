# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
"""The Start All progress dialog drawn by React inside ``QWebEngineView``.

``StartAllProgressReactDialog`` replaces every Qt control ``_setup_ui`` builds
and inherits ``_on_progress_event``, ``_handle_progress_main_thread``,
``_replace_last_matching``, ``_on_cancel`` and ``closeEvent`` unchanged. The
page-backed holders answer ``setText``, ``setEnabled``, ``addItem`` and
``count`` the way the widgets they replace do.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Optional

from .main_tabs import start_all_progress_surface as surface
from .react_history_panel import STYLE_SOURCE_ASSETS, page_html
from .start_all_progress_dialog import StartAllProgressDialog

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

#: The element ``start_all_progress.js`` draws the dialog into.
DIALOG_ROOT_ID = "start-all-root"

ACCESSIBLE_NAME = "React Start All Progress Dialog"

STYLE_ASSET = "start_all_progress.css"

#: The scripts the page carries. Order is load order, and the style
#: sources parse the Qt sheets before the dialog is drawn from them.
DIALOG_SCRIPT_ASSETS: tuple[str, ...] = (
    ("vendor/react.production.min.js", "vendor/react-dom.production.min.js")
    + STYLE_SOURCE_ASSETS
    + ("start_all_progress.js",)
)

DIALOG_BODY = f'<div id="{DIALOG_ROOT_ID}"></div>'

#: The JS expression reading the headline the browser drew.
HEADLINE_TEXT_JS = "document.querySelector('[data-part=\"headline\"]').textContent"

#: The JS expression reading the bot lines the browser drew.
ROW_TEXTS_JS = (
    "Array.from(document.querySelectorAll('[data-part=\"list-row\"]'))"
    ".map(function (n) { return n.textContent; })"
)

#: The JS expression reading which buttons the browser drew as pressable.
BUTTON_STATE_JS = (
    "Array.from(document.querySelectorAll('[data-part=\"button\"]'))"
    ".map(function (n) { return n.getAttribute('data-name') + '='"
    " + String(!n.disabled); })"
)

HOST_SCRIPT = """(function (global) {
  "use strict";

  global.acervator = {
    call: function (method, params) {
      console.log("%(call)s" + JSON.stringify({ method: method, params: params }));
      return Promise.resolve(null);
    }
  };

  global.acervatorStartAllDraw = function (model) {
    global.acervatorSetStartAllProgress(model);
    return (
      global.acervatorStartAllProgress.renderDialog(
        document.getElementById("%(root)s"),
        null
      ) !== null
    );
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


def draw_script(model: dict) -> str:
    """The one JS statement that hands ``model`` to the page."""
    return "window.acervatorStartAllDraw(" + json.dumps(model, ensure_ascii=True) + ");"


def pressed_button(payload: str) -> str:
    """``cancel``, ``close`` or the empty string for a ``CALL_PREFIX`` line."""
    try:
        asked = json.loads(payload)
    except ValueError:
        return ""
    params = asked.get("params")
    if not isinstance(params, dict):
        return ""
    if params.get("cancel"):
        return "cancel"
    if params.get("close"):
        return "close"
    return ""


class PageText:
    """A label the dialog writes words into, as ``QLabel`` reports it."""

    def __init__(self, owner: Any) -> None:
        """Hold ``owner`` as the dialog that carries the headline."""
        self._owner = owner

    def text(self) -> str:
        """The words the headline is showing."""
        return self._owner.store().headline

    def setText(self, words: Any) -> None:  # noqa: N802
        """Show ``words`` in the headline and redraw."""
        self._owner.store().set_headline("" if words is None else str(words))
        self._owner.redraw()


class PageRow:
    """One line of ``PageList``, as ``QListWidgetItem`` reports it."""

    def __init__(self, owner: Any, at: int) -> None:
        """Hold ``owner`` and the position ``at`` of this line."""
        self._owner = owner
        self._at = at

    def text(self) -> str:
        """The words on the line."""
        return self._owner.store().item_text(self._at)

    def setText(self, words: Any) -> None:  # noqa: N802
        """Rewrite the line and redraw."""
        self._owner.store().set_item_text(self._at, str(words))
        self._owner.redraw()


class PageList:
    """The bot lines, as ``QListWidget`` reports them."""

    def __init__(self, owner: Any) -> None:
        """Hold ``owner`` as the dialog that carries the lines."""
        self._owner = owner

    def clear(self) -> None:
        """Drop every line and redraw."""
        self._owner.store().clear_items()
        self._owner.redraw()

    def addItem(self, words: Any) -> None:  # noqa: N802
        """Append ``words`` as the last line and redraw."""
        self._owner.store().add_item(str(words))
        self._owner.redraw()

    def count(self) -> int:
        """How many lines the list holds."""
        return self._owner.store().item_count()

    def item(self, at: int) -> Optional[PageRow]:
        """The line at ``at``, or None when the list is shorter."""
        if 0 <= at < len(self._owner.store().items):
            return PageRow(self._owner, at)
        return None

    def scrollToBottom(self) -> None:  # noqa: N802
        """Keep the newest line in view."""
        self._owner.store().scroll_to_bottom()


class PagePress:
    """A button the dialog turns on and off, as ``QPushButton`` reports it."""

    def __init__(self, owner: Any, name: str) -> None:
        """Hold ``owner`` and the button ``name`` the page draws."""
        self._owner = owner
        self._name = name

    def isEnabled(self) -> bool:  # noqa: N802
        """True while the button takes a press."""
        store = self._owner.store()
        return store.cancel_enabled if self._name == "cancel" else store.close_enabled

    def setEnabled(self, on: Any) -> None:  # noqa: N802
        """Take presses or refuse them, and redraw."""
        store = self._owner.store()
        if self._name == "cancel":
            store.set_cancel_enabled(bool(on))
        else:
            store.set_close_enabled(bool(on))
        self._owner.redraw()


if _HAS_WEBENGINE:

    class StartAllProgressPage(QWebEnginePage):
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

    class StartAllProgressReactDialog(StartAllProgressDialog):
        """The Start All progress dialog with every control drawn by React."""

        def _setup_ui(self) -> None:
            """Build the one web view the whole dialog is drawn in.

            Every control the Qt dialog builds gets a page-backed holder
            under the same attribute name, so the progress handlers run
            unchanged.
            """
            self._model = surface.StartAllProgressModel()
            self._page_ready = False
            self._headline = PageText(self)
            self._list = PageList(self)
            self._cancel_btn = PagePress(self, "cancel")
            self._close_btn = PagePress(self, "close")

            self.setAccessibleName(ACCESSIBLE_NAME)
            self.setWindowTitle(surface.WINDOW_TITLE)
            self.setModal(surface.MODAL)
            self.setMinimumWidth(surface.MINIMUM_WIDTH_PX)
            self.resize(*surface.SIZE_PX)
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)
            self._web = QWebEngineView(self)
            self._web_page = StartAllProgressPage(self)
            self._web.setPage(self._web_page)
            self._web.loadFinished.connect(self._on_load_finished)
            self._web.setHtml(dialog_html())
            layout.addWidget(self._web, 1)

        @property
        def page_ready(self) -> bool:
            """True once ``_on_load_finished`` has seen a successful load."""
            return self._page_ready

        def store(self) -> surface.StartAllProgressModel:
            """The dialog's headline, bot lines and two button states."""
            return self._model

        def model(self) -> dict:
            """The whole dialog as one payload the page is drawn from."""
            return surface.build_view_model(self._model)

        def redraw(self) -> None:
            """Push the payload built from the store to the page."""
            if self._page_ready:
                self._web.page().runJavaScript(draw_script(self.model()))

        def run_action(self, name: str) -> bool:
            """Run the Cancel or Close press the page reports.

            A press the page names neither answers False.
            """
            if name == "cancel":
                self._on_cancel()
                return True
            if name == "close":
                self.accept()
                return True
            return False

        def headline_text(self, callback: Callable[[Any], None]) -> bool:
            """Run ``HEADLINE_TEXT_JS`` and hand the words to ``callback``.

            Returns False and calls nothing while the page is not ready.
            """
            if not self._page_ready:
                return False
            self._web.page().runJavaScript(HEADLINE_TEXT_JS, callback)
            return True

        def row_texts(self, callback: Callable[[Any], None]) -> bool:
            """Run ``ROW_TEXTS_JS`` and hand the bot lines to ``callback``.

            Returns False and calls nothing while the page is not ready.
            """
            if not self._page_ready:
                return False
            self._web.page().runJavaScript(ROW_TEXTS_JS, callback)
            return True

        def _on_load_finished(self, ok: bool) -> None:
            self._page_ready = bool(ok)
            if not ok:
                logger.warning("React Start All progress page failed to load")
                return
            self.redraw()
