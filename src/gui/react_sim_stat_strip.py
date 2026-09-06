# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
"""The Simulator's header stat strip drawn by React inside ``QWebEngineView``.

``SimStatStripWebStrip`` answers the ``set`` and ``clear`` calls ``SimStatStrip``
answers, and writes them into ``SimStatStripModel``. ``strip_html`` builds the
page from ``sim_stat_strip.js`` and ``sim_stat_strip.css``.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

from .main_tabs import sim_stat_strip_surface as surface
from .react_history_panel import STYLE_SOURCE_ASSETS, page_html

try:
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWidgets import QVBoxLayout, QWidget

    _HAS_WEBENGINE = True
except ImportError:
    # Without WebEngine the class is never defined and its import fails by name.
    _HAS_WEBENGINE = False

logger = logging.getLogger("acervator.gui.react_sim_stat_strip")

#: The element ``sim_stat_strip.js`` draws the strip into.
STRIP_ROOT_ID = "sim-stat-strip-root"

ACCESSIBLE_NAME = "React Sim Stat Strip"

#: The height the strip asks for, matching the ten Qt cells it replaces.
STRIP_HEIGHT_PX = 44

STRIP_STYLE_ASSETS: tuple[str, ...] = ("sim_stat_strip.css",)

#: The scripts the page carries. Order is load order, and the style source
#: comes before ``sim_stat_strip.js``, which parses its sheets with it.
STRIP_SCRIPT_ASSETS: tuple[str, ...] = (
    ("vendor/react.production.min.js", "vendor/react-dom.production.min.js")
    + STYLE_SOURCE_ASSETS
    + ("sim_stat_strip.js",)
)

STRIP_BODY = f'<div id="{STRIP_ROOT_ID}"></div>'

#: The JS expression that reads the ten values the browser drew.
VALUE_TEXTS_JS = (
    "Array.from(document.querySelectorAll('[data-part=\"value\"]'))"
    ".map(function (n) { return n.textContent; })"
)

HOST_SCRIPT = """(function (global) {
  "use strict";

  global.acervatorSimStripDraw = function (model) {
    global.acervatorSetSimStrip(model);
    return global.acervatorSimStrip.renderStrip(
      document.getElementById("%(root)s"),
      null
    ) !== null;
  };
})(window);""" % {"root": STRIP_ROOT_ID}


def strip_html(theme: str = "cyberpunk_dark") -> str:
    """The whole strip page as one string, with no network fetch."""
    return page_html(
        STRIP_STYLE_ASSETS, STRIP_SCRIPT_ASSETS, STRIP_BODY, theme, (HOST_SCRIPT,)
    )


def draw_script(model: dict) -> str:
    """The one JS statement that hands ``model`` to the page."""
    return "window.acervatorSimStripDraw(" + json.dumps(model, ensure_ascii=True) + ");"


if _HAS_WEBENGINE:

    class SimStatStripWebStrip(QWidget):
        """The ten stat cells, drawn by React where ``SimStatStrip`` drew labels.

        ``set`` and ``clear`` are the two calls the Simulator tab and the fleet
        panel make, and ``FIELDS`` is the same tuple in the same order.
        """

        FIELDS = surface.FIELDS

        def __init__(self, parent=None) -> None:
            """Build the one web view the strip is drawn in."""
            super().__init__(parent)
            self._model = surface.SimStatStripModel()
            self._page_ready = False
            self.setAccessibleName(ACCESSIBLE_NAME)
            self.setObjectName(surface.STRIP_OBJECT_NAME)
            self.setFixedHeight(STRIP_HEIGHT_PX)
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)
            self._web = QWebEngineView(self)
            self._web.loadFinished.connect(self._on_load_finished)
            self._web.setHtml(strip_html())
            layout.addWidget(self._web, 1)

        @property
        def page_ready(self) -> bool:
            """True once ``_on_load_finished`` has seen a successful load."""
            return self._page_ready

        def model(self) -> dict:
            """The whole strip as one payload the page is drawn from."""
            return surface.build_view_model(self._model)

        def set(self, field: str, value: str) -> None:
            """Update one field's value, ignoring a field the strip lacks."""
            self._model.set_field(field, value)
            self._push()

        def clear(self) -> None:
            """Reset every field to the em-dash placeholder."""
            self._model.clear()
            self._push()

        def values(self, callback: Callable[[Any], None]) -> bool:
            """Run ``VALUE_TEXTS_JS`` and hand the ten values to ``callback``.

            Returns False and calls nothing while the page is not ready.
            """
            if not self._page_ready:
                return False
            self._web.page().runJavaScript(VALUE_TEXTS_JS, callback)
            return True

        def _push(self) -> None:
            if self._page_ready:
                self._web.page().runJavaScript(draw_script(self.model()))

        def _on_load_finished(self, ok: bool) -> None:
            self._page_ready = bool(ok)
            if not ok:
                logger.warning("React Sim Stat Strip page failed to load")
                return
            self._push()
