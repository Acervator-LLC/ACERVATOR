# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
"""The whole Notifications and Alerts tab drawn by React inside ``QWebEngineView``.

``AlertsReactTab`` replaces every Qt control ``AlertsTab._setup_ui`` builds and
inherits ``refresh``, ``_test_telegram``, ``_save_config`` and
``_acknowledge_all`` unchanged. ``AlertsTabPage`` carries the page's own calls
back to ``answer_call``.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

from .alerts_tab import _HAS_QT, AlertsTab
from .color_alpha import css_colours
from .main_tabs import alerts_tab_surface as surface
from .react_history_panel import page_html

try:
    from PySide6.QtCore import Qt
    from PySide6.QtWebEngineCore import QWebEnginePage
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWidgets import QVBoxLayout

    _HAS_WEBENGINE = True
except ImportError:
    # Without WebEngine, AlertsReactTab is never defined and its import fails by name.
    _HAS_WEBENGINE = False

logger = logging.getLogger("acervator.gui.react_alerts_tab")

CALL_PREFIX = "acervator-call:"

#: The element ``alerts_tab.js`` draws the whole tab into.
TAB_ROOT_ID = "tab-root"

ACCESSIBLE_NAME = "React Notifications and Alerts Tab"

#: The page ground and the words every part inherits.
TAB_STYLE_ASSETS: tuple[str, ...] = ("alerts_tab.css",)

#: The seven scripts the page carries. Order is load order.
TAB_SCRIPT_ASSETS: tuple[str, ...] = (
    "vendor/react.production.min.js",
    "vendor/react-dom.production.min.js",
    "design_tokens.js",
    "theme_engine.js",
    "shared_widgets.js",
    "header_strip.js",
    "alerts_tab.js",
)

TAB_BODY = f'<div id="{TAB_ROOT_ID}"></div>'

#: The words the page drew, read back off the browser.
TAB_TEXT_JS = f'document.getElementById("{TAB_ROOT_ID}").textContent'

#: What the page reports each press as, and the method that runs it.
ACTION_HANDLERS: dict[str, str] = {
    "test_telegram": "_test_telegram",
    "save_config": "_save_config",
    "acknowledge_all": "_acknowledge_all",
}

#: The three typed values the page reports, each with the attribute holding it.
FIELD_HOLDERS: tuple[tuple[str, str], ...] = (
    ("token", "_tg_token"),
    ("chat_id", "_tg_chat"),
    ("phone", "_sms_phone"),
)

#: The bridge this host answers. The Electron shell binds ``window.acervator``
#: in its own preload, so this source is never a file under ``src/gui/web``.
HOST_SCRIPT = """(function (global) {
  "use strict";

  var pending = {};
  var lastId = 0;

  global.acervator = {
    call: function (method, params) {
      lastId += 1;
      var id = lastId;
      return new Promise(function (resolve) {
        pending[id] = resolve;
        console.log(
          "%(call)s" +
            JSON.stringify({ id: id, method: method, params: params || {} })
        );
      });
    }
  };

  global.acervatorResolve = function (id, answer) {
    var resolve = pending[id];
    delete pending[id];
    if (typeof resolve === "function") {
      resolve(answer);
    }
    return id;
  };

  global.acervatorAlertsTabDrawn = function () {
    var root = document.getElementById("%(root)s");
    return root !== null && root.childElementCount > 0;
  };
})(window);""" % {
    "call": CALL_PREFIX,
    "root": TAB_ROOT_ID,
}


def tab_html(theme: object = None) -> str:
    """The whole tab page as one string, with no network fetch."""
    return page_html(
        TAB_STYLE_ASSETS, TAB_SCRIPT_ASSETS, TAB_BODY, theme, (HOST_SCRIPT,)
    )


def push_script(model: dict) -> str:
    """The one JS statement that hands ``model`` to the page and draws it.

    ``ensure_ascii=True`` escapes U+2028 and U+2029, which are legal inside a
    JSON string and are JavaScript line terminators.
    """
    return (
        "window.acervatorSetAlertsTab("
        + json.dumps(model, ensure_ascii=True)
        + ');window.acervatorAlertsTab.renderTab(document.getElementById("'
        + TAB_ROOT_ID
        + '"), null);'
    )


def resolve_script(call_id: Any, answer: dict) -> str:
    """The one JS statement that settles the page's promise ``call_id``."""
    return (
        "window.acervatorResolve("
        + json.dumps(call_id)
        + ", "
        + json.dumps(answer, ensure_ascii=True)
        + ");"
    )


if _HAS_QT and _HAS_WEBENGINE:

    FOREGROUND_ROLE = Qt.ItemDataRole.ForegroundRole

    def item_colour(item: Any) -> str:
        """One table item's colour, or the surface's no-colour when unset."""
        held = item.data(FOREGROUND_ROLE)
        return surface.NO_COLOR if held is None else held.color().name()

    class PageLabel:
        """A label the tab writes words and a style into, held on the store."""

        def __init__(self, owner: Any, words: str, style: str) -> None:
            self._owner = owner
            self._words = words
            self._style = style

        def text(self) -> str:
            """The words the label is showing."""
            return str(getattr(self._owner.store(), self._words, ""))

        def setText(self, words: Any) -> None:  # noqa: N802
            """Show ``words`` where this label sits."""
            self._owner.write(self._words, "" if words is None else str(words))

        def setStyleSheet(self, sheet: Any) -> None:  # noqa: N802
            """Paint this label with ``sheet``."""
            self._owner.write(self._style, "" if sheet is None else str(sheet))

    class PageField:
        """A line of text the operator types, held on the store."""

        def __init__(self, owner: Any, name: str) -> None:
            self._owner = owner
            self._name = name

        def text(self) -> str:
            """The words typed in the field."""
            return str(getattr(self._owner.store(), self._name, ""))

        def setText(self, words: Any) -> None:  # noqa: N802
            """Put ``words`` in the field."""
            self._owner.write(self._name, "" if words is None else str(words))

    class PageTable:
        """A table the tab writes rows and cells into, held on the store."""

        def __init__(self, owner: Any, name: str, columns: int) -> None:
            self._owner = owner
            self._name = name
            self._columns = columns

        def _rows(self) -> list:
            return getattr(self._owner.store(), self._name)

        def rowCount(self) -> int:  # noqa: N802
            """How many rows the table holds."""
            return len(self._rows())

        def setRowCount(self, count: Any) -> None:  # noqa: N802
            """Give the table ``count`` rows with no cell written yet."""
            held = max(0, int(count))
            self._owner.write(
                self._name, [surface.blank_row(self._columns) for _ in range(held)]
            )

        def setItem(self, row: Any, column: Any, item: Any) -> None:  # noqa: N802
            """Write one cell's words and colour at ``row`` and ``column``."""
            rows = self._rows()
            at = int(row)
            across = int(column)
            if 0 <= at < len(rows) and 0 <= across < self._columns:
                rows[at][across] = surface.cell(item.text(), item_colour(item))

    class AlertsTabPage(QWebEnginePage):
        """Routes the page's ``acervator-`` console lines to its owner."""

        def __init__(self, owner) -> None:
            """Hold ``owner`` as the tab that answers the page."""
            super().__init__(owner)
            self._owner = owner

        def javaScriptConsoleMessage(self, level, message, line, source) -> None:
            """Hand a call to the owner and drop every other line."""
            del level, line, source
            if message.startswith(CALL_PREFIX):
                self._owner.answer_call(message[len(CALL_PREFIX) :])

    class AlertsReactTab(AlertsTab):
        """The Notifications and Alerts tab with every control drawn by React."""

        def _setup_ui(self) -> None:
            """Build the one web view the whole tab is drawn in.

            Every control ``AlertsTab._setup_ui`` builds gets a page-backed
            holder under the same attribute name.
            """
            self._store = surface.AlertsTabModel(self._notif)
            self._page_ready = False
            self._last_model: dict = {}
            self._build_holders()

            self.setAccessibleName(ACCESSIBLE_NAME)
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)
            self._web = QWebEngineView(self)
            self._web_page = AlertsTabPage(self)
            self._web.setPage(self._web_page)
            self._web.loadFinished.connect(self._on_load_finished)
            self._web.setHtml(tab_html())
            layout.addWidget(self._web, 1)

        # -- the store every holder reads and writes ---------------------

        def store(self) -> surface.AlertsTabModel:
            """The tab's words, styles, typed values and two tables."""
            return self._store

        def write(self, name: str, value: Any) -> None:
            """Hold ``value`` under ``name`` for the next draw."""
            setattr(self._store, name, value)

        @property
        def page_ready(self) -> bool:
            """True once ``_on_load_finished`` has seen a successful load."""
            return self._page_ready

        def model(self) -> dict:
            """A copy of the last payload pushed, empty before the first push."""
            return dict(self._last_model)

        def redraw(self) -> None:
            """Build the payload from the store and push it to the page."""
            found = self._build_model()
            self._last_model = found
            if self._page_ready:
                self._run(push_script(found))

        def refresh(self, notification_manager=None) -> None:
            """Read the manager the way ``AlertsTab`` does, then draw."""
            super().refresh(notification_manager)
            self.redraw()

        def read_text(self, callback: Callable[[Any], None]) -> bool:
            """Hand the words the page drew to ``callback``.

            Returns False and calls nothing while the page is not ready.
            """
            if not self._page_ready:
                return False
            self._web.page().runJavaScript(TAB_TEXT_JS, callback)
            return True

        # -- what the page reports back ----------------------------------

        def answer_call(self, payload: str) -> None:
            """Apply one request from the page and settle its promise."""
            try:
                request = json.loads(payload)
            except ValueError:
                logger.warning("Alerts page sent a call that is not JSON")
                return
            self._apply_request(request.get("params") or {})
            self.redraw()
            self._run(resolve_script(request.get("id"), self._last_model))

        # -- internals ----------------------------------------------------

        def _apply_request(self, params: dict) -> None:
            """Take the page's typed values, then run whichever button it pressed."""
            for name, value in (params.get("fields") or {}).items():
                held = self._holders.get(name)
                if held is not None:
                    held.setText(value)
            handler = ACTION_HANDLERS.get(str(params.get("action") or ""))
            if handler is not None:
                getattr(self, handler)()

        def _build_model(self) -> dict:
            """The whole tab as one payload the renderer draws."""
            return css_colours(surface.build_view_model(self._store))

        def _build_holders(self) -> None:
            self._lbl_status = PageLabel(self, "status_text", "status_style")
            self._lbl_unread = PageLabel(self, "unread_text", "unread_style")
            self._tg_status = PageLabel(
                self, "telegram_status_text", "telegram_status_style"
            )
            self._sms_status = PageLabel(self, "sms_status_text", "sms_status_style")
            self._holders = {}
            for field, attribute in FIELD_HOLDERS:
                held = PageField(self, field)
                self._holders[field] = held
                setattr(self, attribute, held)
            self._rules_table = PageTable(
                self, "rules_rows", surface.RULES_COLUMN_COUNT
            )
            self._history_table = PageTable(
                self, "history_rows", surface.HISTORY_COLUMN_COUNT
            )

        def _run(self, script: str) -> None:
            self._web.page().runJavaScript(script)

        def _on_load_finished(self, ok: bool) -> None:
            self._page_ready = bool(ok)
            if not ok:
                logger.warning("React Alerts tab page failed to load")
                return
            self.redraw()
