# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
"""The Charts tab drawn by React inside ``QWebEngineView``.

``ChartsTabReact`` holds one ``trade_charts_tab_surface.TradeChartsTabModel``
and draws ``src/gui/web/trade_charts_tab.js`` through ``panel_host.js``, whose
chart slot asks ``IMAGE_METHOD`` for the image one ``ChartPainter`` paints at
the slot's width and the display's device pixel ratio, ``ChartPainter`` being
the painter ``render_chart_png`` draws the ATA-SPM post images with. The tab
answers ``update_charts``, ``fetch_chart_data`` and ``set_ata_source``, and
``ChartsTabPage`` carries the page's own bridge asks back to ``run_ask``,
``chart_view`` answering the pointer inputs the page's chart host sends.
``page_html`` inlines ``trade_charts_tab.css`` and every script, so the page
fetches nothing.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import json
import logging
import time
from typing import Any, Optional

from ..core.signal_contract import emit as _pin_emit
from .._variant import resolve_variant
from .main_tabs import design_system_surface, native_chart_surface
from .main_tabs import trade_charts_tab_surface as surface
from .react_history_panel import STYLE_SOURCE_ASSETS, page_html, read_asset
from .react_main_window import read_renderer_asset

#: How long the tab waits after the last resize step before it redraws.
RESIZE_SETTLE_MS = 120

try:
    from PySide6.QtCore import QBuffer, QIODevice, QTimer
    from PySide6.QtGui import QImageWriter
    from PySide6.QtWebEngineCore import QWebEnginePage
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWidgets import QVBoxLayout, QWidget

    from .native_chart import (
        POST_IMAGE_WIDTH_PX,
        Candle,
        ChartPainter,
        PositionMarker,
        paint_image,
    )

    _HAS_WEBENGINE = True
except ImportError:
    # Without WebEngine, ChartsTabReact is never defined and its import
    # fails by name.
    _HAS_WEBENGINE = False

logger = logging.getLogger("acervator.gui.react_charts_tab")

ACCESSIBLE_NAME = "React Charts Tab"

#: The console-line prefix every bridge ask the page makes carries.
ASK_PREFIX = "acervator-ask:"

#: The bus topic every fill of every bot crosses; ``_on_trade_filled`` records it.
FILLED_TOPIC = "trade.filled"

#: The element ``trade_charts_tab.js`` draws the tab into.
PANEL_ROOT_ID = "panel-root"

#: The renderer module the page draws.
PANEL_MODULE = "trade_charts_tab.js"

#: Modules ``trade_charts_tab.js`` mounts into its own chart slot. None: the
#: slot shows the image ``ChartPainter`` paints, so ``native_chart.js`` is
#: not carried.
CHILD_MODULES: tuple[str, ...] = ()

#: The bridge method the page's chart slot asks for the painted image.
IMAGE_METHOD = "trade_charts_tab.image"

#: The ``IMAGE_METHOD`` request fields: the slot's width and height in CSS
#: pixels and the page's device pixel ratio. The tab ask takes one overlay
#: toggle to apply before it answers.
IMAGE_WIDTH_PARAM = "width"
IMAGE_HEIGHT_PARAM = "height"
IMAGE_RATIO_PARAM = "dpr"
TOGGLE_KEY_PARAM = "toggle_overlay"
TOGGLE_ON_PARAM = "toggle_on"

#: The width the painter draws at when the page has not measured its slot.
FALLBACK_IMAGE_WIDTH_PX = POST_IMAGE_WIDTH_PX if _HAS_WEBENGINE else 1200

PNG_FORMAT = b"PNG"
DATA_URI_PREFIX = "data:image/png;base64,"
SHA_PREFIX_LENGTH = 16

#: The style sheet the page carries.
STYLE_ASSETS: tuple[str, ...] = ("trade_charts_tab.css",)

#: The scripts every page carries before the modules. Order is load order.
BASE_SCRIPT_ASSETS: tuple[str, ...] = (
    "vendor/react.production.min.js",
    "vendor/react-dom.production.min.js",
)

#: The panel host, read from ``desktop/renderer`` and inlined.
SHELL_SCRIPT = "panel_host.js"

#: The global a page carries the name of the module running now under.
NAME_GLOBAL = "acervatorInlinedModule"

#: The page ground. Every colour a chart mark paints arrives from the payload
#: skin, so no rule here may set one on a mark.
PAGE_STYLE = (
    "*{margin:0;padding:0;box-sizing:border-box}"
    "html,body{height:100%}"
    "body{background:var(--bg);color:var(--text);overflow:hidden;"
    'font:12px/1.4 "Segoe UI","Helvetica Neue",Arial,sans-serif}'
    f"#{PANEL_ROOT_ID}{{height:100%}}"
)

#: The JS expression naming every module that registered a panel.
DRAWN_MODULES_JS = "window.acervatorPanelHost.registered().join(',')"

#: The JS expression naming every panel the page refused to draw.
PANEL_FAULTS_JS = "JSON.stringify(window.acervatorPanelHost.faults())"

#: The JS expression naming each style sheet the page holds and its rule count.
LOADED_STYLES_JS = "JSON.stringify(window.acervatorChartsPage.styles())"

_NAMER_SOURCE = """(function (global) {
  "use strict";

  var host = global.acervatorPanelHost;
  var real = host.register;

  // Every module is inlined, so document.currentScript names no file.
  host.register = function (spec, called) {
    return real(spec, called || global.%(name_global)s || null);
  };
})(window);"""

_MARKER_SOURCE = "window.%(name_global)s = %(module)s;"

_HOST_SOURCE = """(function (global) {
  "use strict";

  var NAME = %(name)s;
  var ROOT = "%(root)s";
  var waiting = {};
  var next = 1;

  global.ACERVATOR_MODULES = %(roster)s;
  global.acervatorSetTokens(%(tokens)s);
  global.acervatorTokens.apply(document.documentElement);

  // An ask goes out as one console line and is answered by its own id, so
  // an arrow, the ticker and the chart slot all reach the same model.
  global.acervator = {
    call: function (method, params) {
      var id = next;
      next += 1;
      console.log(
        "%(ask)s" +
          JSON.stringify({ id: id, method: method, params: params || {} })
      );
      return new Promise(function (resolve, reject) {
        waiting[id] = { resolve: resolve, reject: reject };
      });
    }
  };

  global.acervatorChartsAnswer = function (id, model, refusal) {
    var held = waiting[id];
    delete waiting[id];
    if (!held) {
      return false;
    }
    if (refusal) {
      held.reject(new Error(refusal));
      return true;
    }
    held.resolve(model);
    return true;
  };

  function root() {
    return document.getElementById(ROOT);
  }

  global.acervatorChartsMount = function (model) {
    global.acervatorSetCharts(model);
    return global.acervatorPanelHost.mount(NAME, root(), model);
  };

  global.acervatorChartsPush = function (model) {
    global.acervatorSetCharts(model);
    global.acervatorCharts.renderTab(root(), model);
    return true;
  };

  global.acervatorChartsPage = {
    styles: function () {
      var found = [];
      var tags = document.querySelectorAll("style[data-asset]");
      for (var at = 0; at < tags.length; at++) {
        var sheet = tags[at].sheet;
        found.push([
          tags[at].getAttribute("data-asset"),
          sheet === null ? 0 : sheet.cssRules.length
        ]);
      }
      return found;
    }
  };
})(window);"""


def module_name(asset: str = PANEL_MODULE) -> str:
    """``asset`` without its ``.js`` suffix, which is the panel's own name."""
    return asset.rsplit(".", 1)[0]


def roster() -> tuple[str, ...]:
    """Every module the page carries, in load order.

    ``STYLE_SOURCE_ASSETS`` leads: ``trade_charts_tab.js`` reads a payload
    colour back to its token through ``shared_widgets.variableFor``.
    """
    return STYLE_SOURCE_ASSETS + CHILD_MODULES + (PANEL_MODULE,)


def namer_script() -> str:
    """The shim that hands the panel host the name an inlined module lacks."""
    return _NAMER_SOURCE % {"name_global": NAME_GLOBAL}


def marker_script(asset: str) -> str:
    """The one statement naming the module whose script tag comes next."""
    return _MARKER_SOURCE % {
        "name_global": NAME_GLOBAL,
        "module": json.dumps(module_name(asset), ensure_ascii=True),
    }


def host_script() -> str:
    """The page's own glue: the design tokens, the roster and the ask channel."""
    return _HOST_SOURCE % {
        "ask": ASK_PREFIX,
        "name": json.dumps(module_name(), ensure_ascii=True),
        "roster": json.dumps(list(roster()), ensure_ascii=True),
        "root": PANEL_ROOT_ID,
        "tokens": json.dumps(design_system_surface.view_model({}), ensure_ascii=True),
    }


def _tag(source: str) -> str:
    """``source`` wrapped in a script tag of its own."""
    return "<script>" + source + "</script>"


def page_body() -> str:
    """The page's body: the root, the panel host, React, then every module.

    ``namer_script`` runs before any module, so a ``register`` call is given
    the name the module cannot read off its own inlined script tag.
    """
    parts = [
        "<style>" + PAGE_STYLE + "</style>",
        f'<div id="{PANEL_ROOT_ID}"></div>',
        _tag(read_renderer_asset(SHELL_SCRIPT)),
        _tag(namer_script()),
    ]
    for name in BASE_SCRIPT_ASSETS:
        parts.append(_tag(read_asset(name)))
    for name in roster():
        parts.append(_tag(marker_script(name)))
        parts.append(_tag(read_asset(name)))
    return "".join(parts)


def panel_html(theme: object = None) -> str:
    """The whole Charts page as one string, with no network fetch.

    ``STYLE_ASSETS`` is inlined into the page head, so the tab's chrome
    reaches the browser without a stylesheet request.
    """
    return page_html(STYLE_ASSETS, (), page_body(), theme, (host_script(),))


def _payload_json(model: Any) -> str:
    """``model`` as JSON, with U+2028 and U+2029 escaped out of the page."""
    return json.dumps(model, ensure_ascii=True)


def mount_script(model: dict) -> str:
    """The statement that draws ``model`` into the page for the first time."""
    return "window.acervatorChartsMount(" + _payload_json(model) + ");"


def push_script(model: dict) -> str:
    """The statement that hands ``model`` to a drawn page and redraws it."""
    return "window.acervatorChartsPush(" + _payload_json(model) + ");"


def answer_script(ask_id: Any, model: Any) -> str:
    """The statement that settles the ask ``ask_id`` with ``model``."""
    return (
        "window.acervatorChartsAnswer("
        + json.dumps(ask_id, ensure_ascii=True)
        + ","
        + _payload_json(model)
        + ",null);"
    )


def refusal_script(ask_id: Any, reason: str) -> str:
    """The statement that refuses the ask ``ask_id`` with ``reason``."""
    return (
        "window.acervatorChartsAnswer("
        + json.dumps(ask_id, ensure_ascii=True)
        + ",null,"
        + json.dumps(str(reason), ensure_ascii=True)
        + ");"
    )


if _HAS_WEBENGINE:

    class ChartsTabPage(QWebEnginePage):
        """Routes the page's ``acervator-ask:`` console lines to its owner."""

        def __init__(self, owner) -> None:
            """Hold ``owner`` as the widget that answers the page."""
            super().__init__(owner)
            self._owner = owner

        def javaScriptConsoleMessage(self, level, message, line, source) -> None:
            """Hand a bridge ask to the owner and drop every other line."""
            del level, line, source
            if message.startswith(ASK_PREFIX):
                self._owner.run_ask(message[len(ASK_PREFIX) :])

    class ChartsTabReact(QWidget):
        """The Charts tab, drawn by ``trade_charts_tab.js`` and its chart module.

        ``build_panel`` loads the page once, on the first show, so a window
        that never opens the tab pays for no web view.
        """

        def __init__(self, parent: Optional[QWidget] = None, theme: object = None):
            """Start a tab holding no asset, with a fetcher the window drives."""
            super().__init__(parent)
            self.setAccessibleName(ACCESSIBLE_NAME)
            self._theme = theme
            self._model = surface.TradeChartsTabModel()
            self._painter = ChartPainter("")
            self._painter.set_timeframe(surface.PANEL_TIMEFRAME)
            self._fed_candles: Any = None
            self._fed_overlays: Any = None
            self._fed_call: Any = None
            self._history_asked = False
            self._history_connected = False
            self._image: dict = {}
            self._image_key_held = ""
            self._payload: dict = {}
            self._page_ready = False
            self._drawn = False
            self._web: Any = None
            self._web_page: Any = None
            self._layout = QVBoxLayout(self)
            self._layout.setContentsMargins(0, 0, 0, 0)
            self._layout.setSpacing(0)
            self._resize_settle = QTimer(self)
            self._resize_settle.setSingleShot(True)
            self._resize_settle.setInterval(RESIZE_SETTLE_MS)
            self._resize_settle.timeout.connect(self._draw_again)

            from src.exchange.chart_data import ChartDataFetcher

            self._model.fetcher = ChartDataFetcher()

            from src.core.event_bus import get_event_bus

            get_event_bus().subscribe(FILLED_TOPIC, self._on_trade_filled)

        # -- what the page is built from ---------------------------------

        @property
        def page_ready(self) -> bool:
            """True once ``_on_load_finished`` has seen a successful load."""
            return self._page_ready

        def panel_view(self):
            """The web view the tab draws in, or None before the first show."""
            return self._web

        def model(self) -> dict:
            """A copy of the last payload drawn, empty before the first draw."""
            return dict(self._payload)

        def showEvent(self, event) -> None:  # noqa: N802
            """Build the web view the first time the tab is shown."""
            super().showEvent(event)
            self.build_panel()

        def resizeEvent(self, event) -> None:  # noqa: N802
            """Re-arm the redraw, so the chart takes the width the tab now has."""
            super().resizeEvent(event)
            if self._drawn:
                self._resize_settle.start()

        def build_panel(self) -> None:
            """Create the tab's web view and load its page, once."""
            if self._web is not None:
                return
            self._web = QWebEngineView(self)
            self._web.setAccessibleName(ACCESSIBLE_NAME)
            self._web_page = ChartsTabPage(self)
            self._web.setPage(self._web_page)
            self._web.loadFinished.connect(self._on_load_finished)
            self._web.setHtml(panel_html(self._theme))
            self._layout.addWidget(self._web, 1)

        def redraw(self) -> None:
            """Build the payload from the model and draw it in the page."""
            payload = surface.build_view_model(self._model)
            self._feed_painter()
            self._payload = self._dressed(payload)
            if not self._page_ready:
                return
            if self._drawn:
                self._run(push_script(self._payload))
                return
            self._run(mount_script(self._payload))
            self._drawn = True

        # -- the painted chart -------------------------------------------

        @property
        def painter(self) -> Any:
            """The ``ChartPainter`` the chart slot's image comes from."""
            return self._painter

        def overlays_shown(self) -> dict:
            """Every overlay key and whether ``painter`` draws it."""
            return self._painter.overlays_shown()

        def set_overlay(self, key: str, on: bool) -> bool:
            """Switch one painter overlay, as a Qt ``ChartPanel`` check box does."""
            return self._painter.set_overlay(str(key), bool(on))

        def _dressed(self, payload: dict) -> dict:
            """``payload`` with each ``panel_chrome`` toggle checked and coloured as ``painter`` draws it.

            The two legend styles resolve from the painter's theme too, so the
            page's boxes and labels follow a Theme menu press.
            """
            shown = self._painter.overlays_shown()
            chrome = payload.get("panel_chrome", {})
            for toggle in chrome.get("toggles", []):
                if toggle.get("key") in shown:
                    toggle["checked"] = shown[toggle["key"]]
                field = toggle.get("color")
                if isinstance(field, str) and field:
                    toggle["color"] = self._painter.field_colour(field).name()
            chrome["legend_styles"] = [
                native_chart_surface.INDICATOR_STYLE_FORMAT.format(
                    color=self._painter.field_colour(field).name()
                )
                for field in chrome.get("legend_fields", [])
            ]
            return payload

        def set_theme(self, tokens) -> None:
            """Repaint the chart image in ``tokens`` and redraw the page from it."""
            self._painter.set_theme(tokens)
            self.redraw()

        def _on_trade_filled(self, event) -> None:
            """Record one ``trade.filled`` bus event through ``log_trade``.

            The next ``update_charts`` tick draws it as a glyph on its candle.
            """
            data = getattr(event, "data", None)
            if not isinstance(data, dict):
                return
            bot_id = str(data.get("bot_id", "") or "")
            record = self._model.assets.get(bot_id) or {}
            recorded = surface.fill_record(
                getattr(event, "timestamp", 0.0),
                data,
                record.get(surface.SYMBOL_KEY, ""),
            )
            if recorded is not None:
                self.log_trade(recorded)

        def _read_history(self) -> None:
            """Hand the window's History rows and fetch stamp to the model.

            A History that has never fetched is asked to ``refresh`` once,
            the call the window makes on activation; ``history_refreshed``
            is connected once so the landing redraws without waiting for
            the tick.
            """
            history = surface.history_of(self.window())
            state = surface.history_state(history)
            if history is not None and not self._history_connected:
                with contextlib.suppress(Exception):
                    history.history_refreshed.connect(self._on_history_refreshed)
                    self._history_connected = True
            if (
                history is not None
                and not self._history_asked
                and surface.history_never_fetched(state)
            ):
                self._history_asked = True
                with contextlib.suppress(Exception):
                    history.refresh()
            self._model.set_history(state["rows"], state["fetched_ts"])

        def _on_history_refreshed(self, rows) -> None:
            """Redraw the shown market's trade events when a History fetch lands."""
            del rows
            self._read_history()
            self._model.feed_history()
            self.redraw()

        def _feed_painter(self) -> None:
            """Give ``painter`` what ``PanelSink`` holds, as the Qt tab gives its chart.

            The candles reach ``set_candles`` once per fetch: the same list
            the panel held on the last feed is not fed again.
            """
            panel = self._model.panel
            painter = self._painter
            painter.symbol = str(panel.label)
            painter.set_timeframe(str(panel.chart_timeframe or panel.timeframe))
            if panel.candles is not self._fed_candles:
                self._fed_candles = panel.candles
                painter.set_candles(
                    [
                        Candle(
                            int(row[0]),
                            float(row[1]),
                            float(row[2]),
                            float(row[3]),
                            float(row[4]),
                            float(row[5]) if len(row) > 5 else 0.0,
                        )
                        for row in panel.candles
                    ]
                )
            if panel.error_text:
                painter.set_error(str(panel.error_text))
            painter.set_source_label(str(panel.source))
            if panel.overlays is not self._fed_overlays:
                self._fed_overlays = panel.overlays
                if panel.overlays is not None:
                    painter.show_only(list(panel.overlays))
            if panel.call is not self._fed_call:
                self._fed_call = panel.call
                self._feed_call(panel)
            painter.set_caption(str(panel.caption))
            painter.set_trade_history_markers(list(panel.markers))
            painter.set_target_balance_lines(panel.tb_anchor, panel.tb_ceiling)
            if panel.armed is not None:
                painter.set_fire_armed_state(
                    panel.armed.get(surface.SCRUM_ARMED_KEY, False),
                    panel.armed.get(surface.FOLD_ARMED_KEY, False),
                    panel.armed.get(surface.SCRUM_BLOCKERS_KEY, []),
                    panel.armed.get(surface.FOLD_BLOCKERS_KEY, []),
                )
            painter.set_landing_strip(panel.strip)
            painter.set_positions(
                []
                if panel.position is None
                else [
                    PositionMarker(
                        price=panel.position[surface.POSITION_PRICE_KEY],
                        side=panel.position[surface.POSITION_SIDE_KEY],
                        visibility=panel.position[surface.POSITION_VISIBILITY_KEY],
                        filled=True,
                        asset_held=panel.position[surface.POSITION_HELD_KEY],
                    )
                ]
            )

        def _feed_call(self, panel: Any) -> None:
            """``set_call`` on the painter from ``panel.call`` and write ``ATA_RENDERED_PIN``
            when the call names a direction.
            """
            painter = self._painter
            call = panel.call or {}
            direction = str(call.get("direction", ""))
            readings = [tuple(one) for one in call.get("readings", [])]
            painter.set_call(direction, readings)
            if not direction:
                return
            shown = sorted(key for key, on in painter.overlays_shown().items() if on)
            _pin_emit(
                surface.ATA_RENDERED_PIN,
                actual=shown,
                expected=sorted(panel.overlays or []),
                context={
                    "symbol": str(panel.symbol),
                    "timeframe": str(panel.chart_timeframe or panel.timeframe),
                    "list": surface.LIST_ATA,
                    "width": self.width(),
                    "height": self.height(),
                    "direction": direction,
                    "candles": len(panel.candles),
                    "variant": resolve_variant(),
                },
            )

        def _image_key(self, width_px: int, height_px: int, ratio: float) -> str:
            """A digest of everything the next ``chart_image`` would read."""
            panel = self._model.panel
            held = {
                "label": panel.label,
                "timeframe": panel.chart_timeframe or panel.timeframe,
                "candles": panel.candles,
                "error": panel.error_text,
                "source": panel.source,
                "markers": panel.markers,
                "tb": [panel.tb_anchor, panel.tb_ceiling],
                "armed": panel.armed,
                "strip": panel.strip,
                "position": panel.position,
                "call": panel.call,
                "caption": panel.caption,
                "asked_overlays": panel.overlays,
                "overlays": self._painter.overlays_shown(),
                "theme": self._painter.theme_name(),
                "window": [
                    self._painter._visible_start,
                    self._painter._visible_count,
                    self._painter._y_zoom_pct,
                ],
                "width": int(width_px),
                "height": int(height_px),
                "ratio": float(ratio),
            }
            digest = hashlib.sha256(
                json.dumps(held, sort_keys=True, default=str).encode("utf-8")
            )
            return digest.hexdigest()

        def chart_image(
            self, width_px: Any = None, ratio: Any = None, height_px: Any = None
        ) -> dict:
            """The chart ``painter`` paints at ``width_px`` by ``height_px`` CSS pixels and ``ratio``, as a PNG data URI.

            A measured slot height is never under the painter's minimum
            height for the overlays on, so the sub-panes shrink to the slot; an
            unmeasured slot takes the natural height. The same inputs answer
            the last image without a repaint.
            """
            width = int(width_px or 0) or FALLBACK_IMAGE_WIDTH_PX
            scale = float(ratio or 0.0) or 1.0
            asked_height = int(height_px or 0)
            key = self._image_key(width, asked_height, scale)
            if key == self._image_key_held and self._image:
                return dict(self._image, repainted=False)
            started = time.perf_counter()
            self._feed_painter()
            natural = int(self._painter._natural_height_for_panes(width))
            minimum = int(self._painter._minimum_height_for_panes(width))
            height = max(minimum, asked_height) if asked_height else natural
            image = paint_image(self._painter, width, height, scale)
            painted_ms = (time.perf_counter() - started) * 1000.0
            buffer = QBuffer()
            buffer.open(QIODevice.OpenModeFlag.WriteOnly)
            QImageWriter(buffer, PNG_FORMAT).write(image)
            png = bytes(buffer.data().data())
            buffer.close()
            self._image = {
                "data_uri": DATA_URI_PREFIX + base64.b64encode(png).decode("ascii"),
                "width_px": width,
                "height_px": height,
                "natural_height_px": natural,
                "minimum_height_px": minimum,
                "device_pixel_ratio": scale,
                "image_width_px": image.width(),
                "image_height_px": image.height(),
                "png_bytes": len(png),
                "sha256": hashlib.sha256(png).hexdigest()[:SHA_PREFIX_LENGTH],
                "candle_count": len(self._model.panel.candles),
                "overlays": self._painter.overlays_shown(),
                "legend": self._painter.legend_entries(),
                "theme": self._painter.theme_name(),
                "paint_ms": round(painted_ms, 2),
                "encode_ms": round(
                    (time.perf_counter() - started) * 1000.0 - painted_ms, 2
                ),
                "repainted": True,
                "geometry": self._painter.geometry_payload(),
            }
            self._image_key_held = key
            return dict(self._image)

        def chart_view(self, asked: dict) -> dict:
            """Answer one pointer input from the page's chart host.

            A wheel tick, a drag move and a double-click move ``painter``'s
            window through the same methods the Qt widget's handlers call;
            a press and a release bound the drag; a crosshair names the
            candle the page drew under the pointer. The answer carries the
            window and, when it moved, the repainted image with its geometry.
            """
            action = str(asked.get(surface.VIEW_ACTION_PARAM) or "")
            if action not in surface.VIEW_ACTIONS:
                raise ValueError(f"unknown chart view action {action!r}")
            painter = self._painter
            x = int(asked.get(surface.VIEW_X_PARAM) or 0)
            width = (
                int(asked.get(surface.VIEW_WIDTH_PARAM) or 0) or FALLBACK_IMAGE_WIDTH_PX
            )
            moved = False
            if action == surface.VIEW_ACTION_WHEEL:
                moved = painter.wheel_turned(
                    x,
                    float(asked.get(surface.VIEW_DELTA_PARAM) or 0.0),
                    width,
                    bool(asked.get(surface.VIEW_CONTROL_PARAM, False)),
                )
            elif action == surface.VIEW_ACTION_PRESS:
                painter.pointer_pressed(x)
            elif action == surface.VIEW_ACTION_DRAG:
                moved = painter.pan_to(x, width)
            elif action == surface.VIEW_ACTION_RELEASE:
                painter.pointer_released()
            elif action == surface.VIEW_ACTION_RESET:
                painter.view_reset()
                moved = True
            else:
                named = asked.get(surface.VIEW_CANDLE_PARAM)
                painter.crosshair_named(x, width, None if named is None else int(named))
            answer = {
                surface.VIEW_ACTION_PARAM: action,
                surface.VIEW_MOVED_KEY: moved,
                surface.VIEW_START_KEY: painter._visible_start,
                surface.VIEW_COUNT_KEY: painter._visible_count,
                surface.VIEW_IMAGE_KEY: None,
            }
            if moved:
                answer[surface.VIEW_IMAGE_KEY] = self.chart_image(
                    asked.get(surface.VIEW_WIDTH_PARAM),
                    asked.get(surface.VIEW_RATIO_PARAM),
                    asked.get(surface.VIEW_HEIGHT_PARAM),
                )
            return answer

        # -- the calls the main window makes on the tab ------------------

        @property
        def panel(self):
            """The one chart panel every asset is drawn in."""
            return self._model.panel

        @property
        def entries(self) -> list:
            """One record per chartable bot, in the order the list offers them."""
            return [
                {"bot_id": bot_id, **self._model.assets[bot_id]}
                for bot_id in self._model.order
            ]

        @property
        def ata_entries(self) -> list:
            """One record per market ATA-SMP has called, in call order."""
            return [
                {"bot_id": bot_id, **self._model.ata_assets[bot_id]}
                for bot_id in self._model.ata_order
            ]

        @property
        def list_mode(self) -> str:
            """Which of the two lists the arrows walk."""
            return self._model.list_mode

        @property
        def shown(self) -> int:
            """The index into the list on screen the panel is drawing."""
            return self._model.list_shown()

        def current_entry(self) -> dict:
            """The record the panel follows, or an empty one when none exists."""
            return self._model.current()

        def set_ata_source(self, source) -> None:
            """Take the callable answering the markets ATA-SMP has called."""
            self._model.set_ata_source(source)

        def set_ata_call_source(self, source) -> None:
            """Take the callable answering one market's ``ata_spm.ChartCall``, or None."""
            self._model.set_ata_call_source(source)

        def toggle_list(self) -> str:
            """Move the arrows to the other list and answer the mode on screen."""
            mode = self._model.toggle_list()
            self.redraw()
            return mode

        def step(self, by: int) -> int:
            """Move the shown asset by ``by`` and answer the new index."""
            at = self._model.step(by)
            self.redraw()
            return at

        def update_charts(
            self,
            bot_statuses: list,
            bot_manager=None,
            exchange_connectors: Optional[dict] = None,
        ) -> None:
            """Rebuild the asset list for one pass of bot statuses and redraw."""
            self._read_history()
            self._model.update_charts(bot_statuses, bot_manager, exchange_connectors)
            self.redraw()

        async def fetch_chart_data(
            self, exchange_connectors: Optional[dict] = None
        ) -> None:
            """Fetch the asset on screen, at most every 30 seconds, and redraw."""
            await self._model.fetch_chart_data(exchange_connectors)
            self.redraw()

        def log_trade(self, trade_data: dict) -> None:
            """Record a trade for chart markup."""
            self._model.log_trade(trade_data)

        def push_synthetic_candles(
            self,
            bot_id: str,
            symbol: str,
            candles: list,
            scenario: str = "",
            last_price: float = 0.0,
        ) -> None:
            """Draw one Nuclear Mode scenario's candles without a fetch."""
            self._model.push_synthetic_candles(
                bot_id, symbol, candles, scenario, last_price
            )
            self.redraw()

        # -- what the page asks back -------------------------------------

        def run_ask(self, payload: str) -> None:
            """Answer one bridge ask the page reported and hand it back by id."""
            try:
                ask = json.loads(payload)
            except ValueError:
                logger.warning("The React Charts page sent an ask that is not JSON")
                return
            ask_id = ask.get("id")
            try:
                answered = self._answer(str(ask.get("method") or ""), ask.get("params"))
            except Exception as exc:
                logger.warning("The React Charts page ask was refused: %s", exc)
                self._run(refusal_script(ask_id, f"{type(exc).__name__}: {exc}"))
                return
            self._run(answer_script(ask_id, answered))

        # -- internals ----------------------------------------------------

        def _answer(self, method: str, params: Any) -> Any:
            asked = params if isinstance(params, dict) else {}
            if method == surface.METHOD:
                if asked.get(TOGGLE_KEY_PARAM) is not None:
                    self.set_overlay(
                        asked[TOGGLE_KEY_PARAM], asked.get(TOGGLE_ON_PARAM, False)
                    )
                payload = surface.build_view_model(
                    self._model,
                    asked.get("statuses"),
                    asked.get("connectors"),
                    asked.get("timeframe_change"),
                    False,
                    asked.get("trades"),
                    asked.get("synthetic"),
                    asked.get("step_by"),
                    asked.get("pick_at"),
                    asked.get("toggle_list", False),
                )
                # The painter takes the model's picture before the toggles are
                # dressed, so the boxes read the overlays the image draws.
                self._feed_painter()
                self._payload = self._dressed(payload)
                return self._payload
            if method == IMAGE_METHOD:
                return self.chart_image(
                    asked.get(IMAGE_WIDTH_PARAM),
                    asked.get(IMAGE_RATIO_PARAM),
                    asked.get(IMAGE_HEIGHT_PARAM),
                )
            if method == surface.VIEW_METHOD:
                return self.chart_view(asked)
            if method == native_chart_surface.METHOD:
                return native_chart_surface.view_model(asked)
            if method == design_system_surface.METHOD:
                return design_system_surface.view_model(asked)
            return None

        def _draw_again(self) -> None:
            if self._drawn:
                self._run(push_script(self._payload))

        def _run(self, script: str) -> None:
            self._web.page().runJavaScript(script)

        def _on_load_finished(self, ok: bool) -> None:
            self._page_ready = bool(ok)
            if not ok:
                logger.warning("The React Charts tab page failed to load")
                return
            self.redraw()
