# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
"""One header stat card drawn by React inside ``QWebEngineView``.

``StatCardReact`` answers the ``set_value``, ``attach_privacy_dot``,
``refresh_privacy_dot`` and ``set_clickable`` calls ``StatCard`` answers and
writes them into ``StatCardModel``. A press on the card emits the inherited
``clicked`` signal; a press on its dot runs ``PrivacyDotModel.clicked``.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Optional

from .main_tabs import dashboard_stat_card_surface as surface
from .main_tabs import header_strip_surface as header
from .main_tabs import privacy_dot_surface as dot_surface
from .react_history_panel import STYLE_SOURCE_ASSETS, page_html
from .widgets.dashboard_stat_card import StatCard, _HAS_QT

try:
    from PySide6.QtWebEngineCore import QWebEnginePage
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtCore import QSize
    from PySide6.QtWidgets import QVBoxLayout

    _HAS_WEBENGINE = True
except ImportError:
    # Without WebEngine the class is never defined and its import fails by name.
    _HAS_WEBENGINE = False

logger = logging.getLogger("acervator.gui.react_dashboard_stat_card")

#: The console line prefix a card or dot press reaches ``pressed`` under.
CALL_PREFIX = "acervator-call:"

#: The method name the page reports a press of the card itself under.
CARD_METHOD = "dashboard_stat_card.clicked"

#: The element ``dashboard_stat_card.js`` draws the card into.
CARD_ROOT_ID = "stat-card-root"

ACCESSIBLE_NAME = "React Stat Card"

#: The width one card asks for. The page inside a ``QWebEngineView``
#: reports none, so the header row would otherwise draw it at its floor.
CARD_WIDTH_PX = header.COUNTER_NATURAL_W

#: The height the card asks for, matching the Qt card it replaces.
CARD_HEIGHT_PX = 72

#: The scripts the page carries. Order is load order, and the style
#: sources parse the Qt sheets before the card is drawn from them.
CARD_SCRIPT_ASSETS: tuple[str, ...] = (
    ("vendor/react.production.min.js", "vendor/react-dom.production.min.js")
    + STYLE_SOURCE_ASSETS
    + ("dashboard_stat_card.js",)
)

#: The page ground. ``page_html`` declares these six chrome colours on the
#: root from the theme, so the card carries no colour of its own.
PAGE_STYLE = (
    "*{margin:0;padding:0;box-sizing:border-box}"
    "html,body{height:100%;overflow:hidden}"
    "body{background:var(--bg);color:var(--text)}"
    f"#{CARD_ROOT_ID}{{height:100%}}"
    '[data-part="card"]{height:100%;background:var(--btn-bg)}'
)

CARD_BODY = "<style>" + PAGE_STYLE + "</style>" + f'<div id="{CARD_ROOT_ID}"></div>'

#: The JS expression reading the caption the browser drew.
LABEL_TEXT_JS = "document.querySelector('[data-part=\"label\"]').textContent"

#: The JS expression reading the amount the browser drew.
VALUE_TEXT_JS = "document.querySelector('[data-part=\"value\"]').textContent"

HOST_SCRIPT = """(function (global) {
  "use strict";

  global.acervator = {
    call: function (method, params) {
      console.log("%(call)s" + JSON.stringify({ method: method, params: params }));
      return Promise.resolve(null);
    }
  };

  document.addEventListener("click", function (event) {
    var at = event.target;
    while (at) {
      if (typeof at.getAttribute === "function") {
        var part = at.getAttribute("%(part)s");
        if (part === "privacy-dot") {
          global.acervator.call("%(dot)s", {
            field_id: at.getAttribute("data-field-id")
          });
          return;
        }
        if (part === "card") {
          global.acervator.call("%(card)s", {});
          return;
        }
      }
      at = at.parentElement;
    }
  });

  global.acervatorStatCardDraw = function (model) {
    global.acervatorSetStatCard(model);
    return (
      global.acervatorStatCard.renderCard(
        document.getElementById("%(root)s"),
        null
      ) !== null
    );
  };
})(window);""" % {
    "call": CALL_PREFIX,
    "card": CARD_METHOD,
    "dot": dot_surface.METHOD,
    "part": "data-part",
    "root": CARD_ROOT_ID,
}


def card_html(theme: object = None) -> str:
    """The whole card page as one string, with no network fetch."""
    return page_html((), CARD_SCRIPT_ASSETS, CARD_BODY, theme, (HOST_SCRIPT,))


def draw_script(model: dict) -> str:
    """The one JS statement that hands ``model`` to the page."""
    return "window.acervatorStatCardDraw(" + json.dumps(model, ensure_ascii=True) + ");"


def press_asked(payload: str) -> tuple:
    """The method and the ``field_id`` a ``CALL_PREFIX`` console line asks for."""
    try:
        asked = json.loads(payload)
    except ValueError:
        return ("", None)
    params = asked.get("params")
    field_id = params.get("field_id") if isinstance(params, dict) else None
    return (str(asked.get("method") or ""), field_id)


if _HAS_QT and _HAS_WEBENGINE:

    class StatCardPage(QWebEnginePage):
        """Routes the page's ``CALL_PREFIX`` console lines to its owner."""

        def __init__(self, owner) -> None:
            """Hold ``owner`` as the card that answers the page."""
            super().__init__(owner)
            self._owner = owner

        def javaScriptConsoleMessage(self, level, message, line, source) -> None:
            """Hand a press to the owner and drop every other line."""
            del level, line, source
            if message.startswith(CALL_PREFIX):
                self._owner.pressed(*press_asked(message[len(CALL_PREFIX) :]))

    class StatCardReact(StatCard):
        """The caption, the amount and the privacy dot, drawn by React.

        ``set_value``, ``attach_privacy_dot``, ``refresh_privacy_dot`` and
        ``set_clickable`` are the four calls the header strip makes.
        """

        def sizeHint(self) -> "QSize":
            """The room one amount needs, which the page cannot report."""
            return QSize(CARD_WIDTH_PX, CARD_HEIGHT_PX)

        def _setup_ui(self, label: str, value: str) -> None:
            """Build the one web view the whole card is drawn in."""
            self._model = surface.StatCardModel(label, value)
            self._dot: Optional[dot_surface.PrivacyDotModel] = None
            self._page_ready = False
            self.setAccessibleName(ACCESSIBLE_NAME)
            self.setMinimumHeight(CARD_HEIGHT_PX)
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)
            self._web = QWebEngineView(self)
            self._web_page = StatCardPage(self)
            self._web.setPage(self._web_page)
            self._web.loadFinished.connect(self._on_load_finished)
            self._web.setHtml(card_html())
            layout.addWidget(self._web, 1)

        @property
        def page_ready(self) -> bool:
            """True once ``_on_load_finished`` has seen a successful load."""
            return self._page_ready

        def model(self) -> dict:
            """The whole card as one payload the page is drawn from."""
            return surface.build_view_model(self._model)

        def set_value(self, value: str) -> None:
            """Show ``value``, through the mask once a dot is attached."""
            self._model.set_value(value)
            self._push()

        def attach_privacy_dot(self, field_id: str) -> Any:
            """Put a dot for ``field_id`` under the amount and redraw."""
            self._model.attach_privacy_dot(field_id)
            if self._dot is None:
                self._dot = dot_surface.PrivacyDotModel(
                    field_id, on_toggle=self._model.dot_clicked
                )
            self._push()
            return self._dot

        def refresh_privacy_dot(self) -> None:
            """Repaint the dot and re-render the amount from the kept value."""
            if self._dot is not None:
                self._dot.refresh()
            self._model.refresh_privacy_dot()
            self._push()

        def set_clickable(self, clickable: bool, tooltip_suffix: str = "") -> None:
            """Arm or disarm the card's press and carry the pointer cursor."""
            self._model.set_clickable(clickable, tooltip_suffix)
            super().setToolTip(self._model.tooltip)
            self._push()

        def setToolTip(self, words) -> None:  # noqa: N802
            """Hold ``words`` on the card and on the frame around it."""
            self._model.tooltip = "" if words is None else str(words)
            super().setToolTip(self._model.tooltip)
            self._push()

        def pressed(self, method: str, field_id: Any) -> bool:
            """Answer one press the page reports, and redraw the card.

            A press the page names no handler for answers False.
            """
            if method == CARD_METHOD:
                if self._model.is_clickable:
                    self._model.mouse_pressed(surface.LEFT_BUTTON)
                    self.clicked.emit()
                    self._push()
                    return True
                return False
            if method == dot_surface.METHOD and self._dot is not None:
                if field_id == self._dot.field_id():
                    self._dot.clicked()
                    self._push()
                    return True
            return False

        def label_text(self, callback: Callable[[Any], None]) -> bool:
            """Run ``LABEL_TEXT_JS`` and hand the caption to ``callback``.

            Returns False and calls nothing while the page is not ready.
            """
            if not self._page_ready:
                return False
            self._web.page().runJavaScript(LABEL_TEXT_JS, callback)
            return True

        def value_text(self, callback: Callable[[Any], None]) -> bool:
            """Run ``VALUE_TEXT_JS`` and hand the amount to ``callback``.

            Returns False and calls nothing while the page is not ready.
            """
            if not self._page_ready:
                return False
            self._web.page().runJavaScript(VALUE_TEXT_JS, callback)
            return True

        def _push(self) -> None:
            if self._page_ready:
                self._web.page().runJavaScript(draw_script(self.model()))

        def _on_load_finished(self, ok: bool) -> None:
            self._page_ready = bool(ok)
            if not ok:
                logger.warning("React stat card page failed to load")
                return
            self._push()
