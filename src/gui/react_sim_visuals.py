# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
"""The Simulator price and VWAP chart drawn by React inside ``QWebEngineView``.

``SimPriceVwapChartReact`` inherits ``SimPriceVwapChart``, so the tick buffers,
the decimation and the trade markers are the same code. It publishes those
buffers under the names ``sim_visuals_surface.chart_program`` reads, and its
``update`` sends the draw program to ``sim_visuals.js``.
"""

from __future__ import annotations

import json
import logging

from .main_tabs import sim_visuals_surface as surface
from .react_history_panel import STYLE_SOURCE_ASSETS, page_html
from .simulator_tab.fleet.sim_visuals import (
    _HAS_QT,
    GateStatusPanel,
    SimPriceVwapChart,
)

try:
    from PySide6.QtCore import QTimer
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWidgets import QVBoxLayout

    _HAS_WEBENGINE = True
except ImportError:
    # Without WebEngine the class is never defined and its import fails by name.
    _HAS_WEBENGINE = False

logger = logging.getLogger("acervator.gui.react_sim_visuals")

#: The element ``sim_visuals.js`` draws the chart into.
CHART_ROOT_ID = "sim-visuals-root"

#: The element ``sim_visuals.js`` draws the gate pane into.
PANE_ROOT_ID = "sim-gate-pane-root"

ACCESSIBLE_NAME = "React Sim Price + VWAP Chart"

PANE_ACCESSIBLE_NAME = "React Gate Status Panel"

#: The style sheet the page carries.
CHART_STYLE_ASSETS: tuple[str, ...] = ("sim_visuals.css",)

#: The scripts the page carries. Order is load order, and the style source
#: comes before ``sim_visuals.js``, which parses its sheets with it.
CHART_SCRIPT_ASSETS: tuple[str, ...] = (
    ("vendor/react.production.min.js", "vendor/react-dom.production.min.js")
    + STYLE_SOURCE_ASSETS
    + ("sim_visuals.js",)
)

CHART_BODY = f'<div id="{CHART_ROOT_ID}"></div>'

#: The JS expression that reads how many draw steps the browser was given.
OPS_COUNT_JS = (
    "(document.querySelector('[data-part=\"chart-mount\"]')"
    " || {getAttribute: function () { return null; }}).getAttribute('data-ops')"
)

#: The JS expression that counts the pixels the canvas painted.
PAINTED_PIXELS_JS = """(function () {
  var canvas = document.querySelector('[data-part="chart-canvas"]');
  if (canvas === null) {
    return -1;
  }
  var surface = canvas.getContext("2d", { willReadFrequently: true });
  var data = surface.getImageData(0, 0, canvas.width, canvas.height).data;
  var painted = 0;
  for (var at = 3; at < data.length; at += 4) {
    if (data[at] !== 0) {
      painted += 1;
    }
  }
  return painted;
})()"""

HOST_SCRIPT = """(function (global) {
  "use strict";

  global.acervatorSimVisualsDraw = function (model) {
    global.acervatorSetSimVisuals(model);
    return global.acervatorSimVisuals.renderChartMount(
      document.getElementById("%(root)s"),
      null
    ) !== null;
  };
})(window);""" % {"root": CHART_ROOT_ID}

PANE_BODY = f'<div id="{PANE_ROOT_ID}"></div>'

PANE_HOST_SCRIPT = """(function (global) {
  "use strict";

  global.acervatorSimPaneDraw = function (model) {
    global.acervatorSetSimVisuals(model);
    return global.acervatorSimVisuals.renderPane(
      document.getElementById("%(root)s"),
      null
    ) !== null;
  };
})(window);""" % {"root": PANE_ROOT_ID}

#: The JS expression that counts the gate rows the browser drew.
PANE_ROW_COUNT_JS = "document.querySelectorAll('[data-part=\"pane-row\"]').length"

#: The JS expression that counts the gate lights the browser drew.
PANE_LAMP_COUNT_JS = "document.querySelectorAll('[data-part=\"lamp\"]').length"


def chart_html(theme: str = "cyberpunk_dark") -> str:
    """The whole chart page as one string, with no network fetch."""
    return page_html(
        CHART_STYLE_ASSETS, CHART_SCRIPT_ASSETS, CHART_BODY, theme, (HOST_SCRIPT,)
    )


def pane_html(theme: str = "cyberpunk_dark") -> str:
    """The whole gate pane page as one string, with no network fetch."""
    return page_html(
        CHART_STYLE_ASSETS, CHART_SCRIPT_ASSETS, PANE_BODY, theme, (PANE_HOST_SCRIPT,)
    )


def draw_script(model: dict) -> str:
    """The one JS statement that hands ``model`` to the chart page."""
    return (
        "window.acervatorSimVisualsDraw(" + json.dumps(model, ensure_ascii=True) + ");"
    )


def pane_draw_script(model: dict) -> str:
    """The one JS statement that hands ``model`` to the gate pane page."""
    return "window.acervatorSimPaneDraw(" + json.dumps(model, ensure_ascii=True) + ");"


if _HAS_QT and _HAS_WEBENGINE:

    class SimPriceVwapChartReact(SimPriceVwapChart):
        """The stacked bands and the focused candles, drawn by React."""

        def __init__(self, parent=None) -> None:
            """Build the one web view the chart is drawn in."""
            super().__init__(parent)
            self.setAccessibleName(ACCESSIBLE_NAME)
            self._page_ready = False
            self._last_model: dict = {}
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)
            self._web = QWebEngineView(self)
            self._web.loadFinished.connect(self._on_load_finished)
            self._web.setHtml(chart_html())
            layout.addWidget(self._web, 1)

        # -- the buffers, under the names the draw program reads -----------

        @property
        def symbols(self) -> list:
            """The fleet the chart tracks, one band each."""
            return list(self._symbols)

        @property
        def series(self) -> dict:
            """Close prices and rolling VWAP per symbol."""
            return self._series

        @property
        def candles(self) -> dict:
            """The open, high, low and close bars per symbol."""
            return self._candles

        @property
        def ytd_from(self) -> dict:
            """Where the documented overlay begins per symbol."""
            return self._ytd_from

        @property
        def focus(self) -> str:
            """The symbol filling the chart, or "" while bands are shown."""
            return self._focus

        @property
        def height_px(self) -> int:
            """The least height the chart asks for."""
            return int(self.minimumHeight())

        # -- what the page is drawn from ----------------------------------

        @property
        def page_ready(self) -> bool:
            """True once ``_on_load_finished`` has seen a successful load."""
            return self._page_ready

        def model(self) -> dict:
            """A copy of the last chart payload pushed."""
            return dict(self._last_model)

        def build_model(self) -> dict:
            """The chart as one payload, the draw program built in Python."""
            return surface.build_view_model(
                chart=self,
                width_px=max(self.width(), 1),
                height_px=max(self.height(), 1),
            )

        def push(self) -> None:
            """Send the chart payload to the page."""
            self._last_model = self.build_model()
            if self._page_ready:
                self._web.page().runJavaScript(draw_script(self._last_model))

        def read(self, script: str, callback) -> bool:
            """Run ``script`` and hand what the page answered to ``callback``.

            Returns False and calls nothing while the page is not ready.
            """
            if not self._page_ready:
                return False
            self._web.page().runJavaScript(script, callback)
            return True

        def update(self, *args) -> None:
            """Redraw the chart, which every caller already asks for by name."""
            super().update(*args)
            self.push()

        def _on_load_finished(self, ok: bool) -> None:
            self._page_ready = bool(ok)
            if not ok:
                logger.warning("React Sim Price + VWAP page failed to load")
                return
            self.push()

    class GateCell:
        """One bot's gate row, written through to the page that draws it."""

        def __init__(self, lights, panel) -> None:
            """Hold the row ``lights`` and the ``panel`` that redraws it."""
            self._lights = lights
            self._panel = panel

        def update_gates(self, *args, **kwargs) -> None:
            """Take one candle's gate reading and ask for a redraw."""
            self._lights.update_gates(*args, **kwargs)
            self._panel.mark_dirty()

        def clear_gates(self) -> None:
            """Return the row to the not-evaluated state and redraw."""
            self._lights.clear_gates()
            self._panel.mark_dirty()

        def lights(self) -> list:
            """The nineteen lights, scrum bank then fold, in draw order."""
            return self._lights.lights()

    class GateStatusPanelReact(GateStatusPanel):
        """Every bot's gate row, drawn by React in one ``QWebEngineView``."""

        def __init__(self, parent=None) -> None:
            """Build the one web view the pane is drawn in."""
            super().__init__(parent)
            # Kept as a child, so it never becomes a window of its own.
            self.layout().removeWidget(self._scroll)
            self._scroll.hide()
            self._pane = surface.GatePanelModel()
            self._page_ready = False
            self._dirty = False
            self._last_model: dict = {}
            self.setAccessibleName(PANE_ACCESSIBLE_NAME)
            self.layout().setContentsMargins(0, 0, 0, 0)
            self._web = QWebEngineView(self)
            self._web.loadFinished.connect(self._on_load_finished)
            self._web.setHtml(pane_html())
            self.layout().addWidget(self._web, 1)

        @property
        def page_ready(self) -> bool:
            """True once ``_on_load_finished`` has seen a successful load."""
            return self._page_ready

        def model(self) -> dict:
            """A copy of the last pane payload pushed."""
            return dict(self._last_model)

        def set_symbols(self, symbols) -> None:
            """Track one gate row per symbol and redraw the pane."""
            self._pane.set_symbols(symbols)
            self.push()

        def cell_for(self, symbol: str):
            """The row ``symbol`` draws into, or None when it has none."""
            found = self._pane.cell_for(symbol)
            return None if found is None else GateCell(found, self)

        def symbols(self) -> list:
            """Every symbol the pane holds a row for, in name order."""
            return self._pane.symbols()

        def mark_dirty(self) -> None:
            """Ask for one redraw, however many rows were written first."""
            if self._dirty:
                return
            self._dirty = True
            QTimer.singleShot(0, self._redraw)

        def push(self) -> None:
            """Send the pane payload to the page."""
            self._last_model = surface.build_view_model(panel=self._pane)
            if self._page_ready:
                self._web.page().runJavaScript(pane_draw_script(self._last_model))

        def read(self, script: str, callback) -> bool:
            """Run ``script`` and hand what the page answered to ``callback``.

            Returns False and calls nothing while the page is not ready.
            """
            if not self._page_ready:
                return False
            self._web.page().runJavaScript(script, callback)
            return True

        def _redraw(self) -> None:
            self._dirty = False
            self.push()

        def _on_load_finished(self, ok: bool) -> None:
            self._page_ready = bool(ok)
            if not ok:
                logger.warning("React Gate Status Panel page failed to load")
                return
            self.push()
