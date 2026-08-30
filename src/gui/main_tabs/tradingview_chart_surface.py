"""tradingview_chart_surface.py -- the candlestick chart page, without Qt.

Describes every part of the TradingView chart the shipped widget shows:
the whole page it hands the browser, the five colour themes, the seven
timeframe buttons, the candle, volume and Bollinger series, the trade
markers, the grid price lines and the five data calls the widget makes
into that page.

The page is one HTML document with eight named holes in it. The holes
are filled from a theme table and from the symbol the chart was built
with. Every colour, every layout number, every button label and every
call format is written out here rather than read from
``src.gui.tradingview_chart``, so a value changed on one side alone is
reported.

The page names one asset it does not carry: the charting library at
``SCRIPT_URL``. Nothing here fetches it. The address is held as text,
exactly as the shipped page holds it, so the frontend decides for
itself what to do about an asset that lives on the internet.

``TradingViewChartModel`` holds the symbol and the theme the chart was
built with, the page text those two produce, and every call made into
that page since it was built. ``src.core.desktop_bridge`` registers
``view_model`` as the handler for the ``tradingview.chart`` method,
which is how the Electron renderer reaches it. Nothing here imports Qt.
"""

from __future__ import annotations

import json
from typing import Any

METHOD = "tradingview.chart"

WIDGET_ACCESSIBLE_NAME = "Trading View Chart"
LOGGER_NAME = "acervator.gui"
MISSING_WEBENGINE_WARNING = "TradingView charts require PySide6-WebEngine"

DEFAULT_SYMBOL = "BTC/USDT"
DEFAULT_THEME = "cyberpunk_dark"
FALLBACK_THEME = "cyberpunk_dark"
SYMBOL_KEY = "symbol"

SCRIPT_URL = (
    "https://unpkg.com/lightweight-charts@4.1.0/dist/"
    "lightweight-charts.standalone.production.js"
)

CHART_HTML = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { background: %(bg)s; overflow: hidden; }
  #chart { width: 100%%; height: 100vh; }
  #toolbar {
    position: absolute; top: 8px; right: 8px; z-index: 10;
    display: flex; gap: 6px;
  }
  .tf-btn {
    background: %(btn_bg)s; color: %(text)s; border: 1px solid %(border)s;
    padding: 4px 10px; border-radius: 4px; cursor: pointer; font-size: 12px;
  }
  .tf-btn:hover { background: %(btn_hover)s; }
  .tf-btn.active { background: %(accent)s; color: %(bg)s; border-color: %(accent)s; }
</style>
</head>
<body>
<div id="toolbar">
  <button class="tf-btn" onclick="setTimeframe('1')">1m</button>
  <button class="tf-btn" onclick="setTimeframe('5')">5m</button>
  <button class="tf-btn" onclick="setTimeframe('15')">15m</button>
  <button class="tf-btn active" onclick="setTimeframe('60')">1H</button>
  <button class="tf-btn" onclick="setTimeframe('240')">4H</button>
  <button class="tf-btn" onclick="setTimeframe('D')">1D</button>
  <button class="tf-btn" onclick="setTimeframe('W')">1W</button>
</div>
<div id="chart"></div>

<script src="https://unpkg.com/lightweight-charts@4.1.0/dist/lightweight-charts.standalone.production.js"></script>
<script>
// --- Chart initialisation ---
const chart = LightweightCharts.createChart(document.getElementById('chart'), {
  layout: {
    background: { type: 'solid', color: '%(bg)s' },
    textColor: '%(text)s',
  },
  grid: {
    vertLines: { color: '%(grid)s' },
    horzLines: { color: '%(grid)s' },
  },
  crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
  rightPriceScale: { borderColor: '%(border)s' },
  timeScale: {
    borderColor: '%(border)s',
    timeVisible: true,
    secondsVisible: false,
  },
  watermark: {
    visible: true,
    text: '%(symbol)s',
    color: '%(watermark)s',
    fontSize: 48,
  },
});

// --- Series ---
const candleSeries = chart.addCandlestickSeries({
  upColor: '#00ff88',
  downColor: '#ff3366',
  borderDownColor: '#ff3366',
  borderUpColor: '#00ff88',
  wickDownColor: '#ff3366',
  wickUpColor: '#00ff88',
});

const volumeSeries = chart.addHistogramSeries({
  color: '#26a69a',
  priceFormat: { type: 'volume' },
  priceScaleId: '',
});
volumeSeries.priceScale().applyOptions({
  scaleMargins: { top: 0.85, bottom: 0 },
});

// Bollinger Bands overlay
const bbUpper = chart.addLineSeries({ color: 'rgba(0, 170, 255, 0.4)', lineWidth: 1 });
const bbLower = chart.addLineSeries({ color: 'rgba(0, 170, 255, 0.4)', lineWidth: 1 });
const bbMiddle = chart.addLineSeries({ color: 'rgba(0, 170, 255, 0.2)', lineWidth: 1, lineStyle: 2 });

// Trade markers storage
let markers = [];

// --- Data update functions (called from Python via JS bridge) ---

window.setCandles = function(data) {
  // data = [{time, open, high, low, close, volume}, ...]
  const parsed = JSON.parse(data);
  candleSeries.setData(parsed.map(d => ({
    time: d.time, open: d.open, high: d.high, low: d.low, close: d.close,
  })));
  volumeSeries.setData(parsed.map(d => ({
    time: d.time,
    value: d.volume,
    color: d.close >= d.open ? 'rgba(0, 255, 136, 0.3)' : 'rgba(255, 51, 102, 0.3)',
  })));
};

window.updateCandle = function(data) {
  const d = JSON.parse(data);
  candleSeries.update({ time: d.time, open: d.open, high: d.high, low: d.low, close: d.close });
  volumeSeries.update({
    time: d.time, value: d.volume,
    color: d.close >= d.open ? 'rgba(0, 255, 136, 0.3)' : 'rgba(255, 51, 102, 0.3)',
  });
};

window.setBollingerBands = function(data) {
  const parsed = JSON.parse(data);
  bbUpper.setData(parsed.map(d => ({ time: d.time, value: d.upper })));
  bbMiddle.setData(parsed.map(d => ({ time: d.time, value: d.middle })));
  bbLower.setData(parsed.map(d => ({ time: d.time, value: d.lower })));
};

window.addTradeMarker = function(data) {
  const d = JSON.parse(data);
  markers.push({
    time: d.time,
    position: d.side === 'buy' ? 'belowBar' : 'aboveBar',
    color: d.side === 'buy' ? '#00ff88' : '#ff3366',
    shape: d.side === 'buy' ? 'arrowUp' : 'arrowDown',
    text: d.side.toUpperCase() + ' ' + d.amount.toFixed(4),
  });
  candleSeries.setMarkers(markers.sort((a, b) => a.time - b.time));
};

window.setGridLevels = function(data) {
  const levels = JSON.parse(data);
  // Remove old grid lines (re-create approach)
  levels.forEach(l => {
    const color = l.side === 'buy' ? 'rgba(0, 255, 136, 0.15)' : 'rgba(255, 51, 102, 0.15)';
    candleSeries.createPriceLine({
      price: l.price,
      color: color,
      lineWidth: 1,
      lineStyle: 2,
      axisLabelVisible: true,
      title: l.side.toUpperCase() + ' ' + l.level,
    });
  });
};

window.setTimeframe = function(tf) {
  document.querySelectorAll('.tf-btn').forEach(b => b.classList.remove('active'));
  event.target.classList.add('active');
  // Signal Python to fetch new data for this timeframe
  if (window.qtBridge) {
    window.qtBridge.timeframeChanged(tf);
  }
};

// Responsive resize
window.addEventListener('resize', () => {
  chart.applyOptions({ width: window.innerWidth, height: window.innerHeight });
});
chart.applyOptions({ width: window.innerWidth, height: window.innerHeight });
</script>
</body>
</html>"""

CYBERPUNK_DARK: dict[str, str] = {
    "bg": "#0a0a0f",
    "text": "#e0e0f0",
    "grid": "#1a1a28",
    "border": "#2a2a44",
    "accent": "#00ffcc",
    "btn_bg": "#12121a",
    "btn_hover": "#1e1e35",
    "watermark": "rgba(0,255,204,0.07)",
}

NEON_LIGHT: dict[str, str] = {
    "bg": "#f5f5fa",
    "text": "#1a1a2e",
    "grid": "#e5e5f0",
    "border": "#ccccdd",
    "accent": "#6600cc",
    "btn_bg": "#eeeef5",
    "btn_hover": "#e0e0f0",
    "watermark": "rgba(102,0,204,0.07)",
}

CLASSIC_TERMINAL: dict[str, str] = {
    "bg": "#0a0a0a",
    "text": "#00ff00",
    "grid": "#181818",
    "border": "#003300",
    "accent": "#00ff00",
    "btn_bg": "#111111",
    "btn_hover": "#1a1a1a",
    "watermark": "rgba(0,255,0,0.05)",
}

MINIMAL_MODERN: dict[str, str] = {
    "bg": "#fafafa",
    "text": "#1a1a1a",
    "grid": "#e8e8e8",
    "border": "#e0e0e0",
    "accent": "#2563eb",
    "btn_bg": "#f0f0f0",
    "btn_hover": "#eeeeee",
    "watermark": "rgba(37,99,235,0.05)",
}

GLASS_METAL: dict[str, str] = {
    "bg": "#1c1c24",
    "text": "#d0d0e0",
    "grid": "#2c2c3a",
    "border": "#3a3a50",
    "accent": "#88ccff",
    "btn_bg": "#242430",
    "btn_hover": "#30303f",
    "watermark": "rgba(136,204,255,0.07)",
}

CHART_THEMES: dict[str, dict[str, str]] = {
    "cyberpunk_dark": CYBERPUNK_DARK,
    "neon_light": NEON_LIGHT,
    "classic_terminal": CLASSIC_TERMINAL,
    "minimal_modern": MINIMAL_MODERN,
    "glass_metal": GLASS_METAL,
}

THEME_ORDER = (
    "cyberpunk_dark",
    "neon_light",
    "classic_terminal",
    "minimal_modern",
    "glass_metal",
)

THEME_KEYS = (
    "bg",
    "text",
    "grid",
    "border",
    "accent",
    "btn_bg",
    "btn_hover",
    "watermark",
)

PAGE: dict[str, Any] = {
    "layout": "vertical",
    "margins_px": [0, 0, 0, 0],
    "children": ["web_view"],
}

WEB_VIEW: dict[str, Any] = {
    "kind": "web_view",
    "html_source": "set_html",
    "script_url": SCRIPT_URL,
    "carries_script": False,
}

TOOLBAR: dict[str, Any] = {
    "position": "absolute",
    "top_px": 8,
    "right_px": 8,
    "z_index": 10,
    "display": "flex",
    "gap_px": 6,
}

BUTTON_SKIN: dict[str, Any] = {
    "class_name": "tf-btn",
    "active_class_name": "tf-btn active",
    "padding_px": [4, 10],
    "radius_px": 4,
    "font_size_px": 12,
    "border_width_px": 1,
    "cursor": "pointer",
    "handler": "setTimeframe",
}

TIMEFRAME_BUTTONS = (
    {"label": "1m", "value": "1", "enabled": True},
    {"label": "5m", "value": "5", "enabled": True},
    {"label": "15m", "value": "15", "enabled": True},
    {"label": "1H", "value": "60", "enabled": True},
    {"label": "4H", "value": "240", "enabled": True},
    {"label": "1D", "value": "D", "enabled": True},
    {"label": "1W", "value": "W", "enabled": True},
)

ACTIVE_TIMEFRAME = "60"

UP_COLOR = "#00ff88"
DOWN_COLOR = "#ff3366"
VOLUME_COLOR = "#26a69a"
VOLUME_UP_COLOR = "rgba(0, 255, 136, 0.3)"
VOLUME_DOWN_COLOR = "rgba(255, 51, 102, 0.3)"
BB_EDGE_COLOR = "rgba(0, 170, 255, 0.4)"
BB_MIDDLE_COLOR = "rgba(0, 170, 255, 0.2)"
GRID_BUY_COLOR = "rgba(0, 255, 136, 0.15)"
GRID_SELL_COLOR = "rgba(255, 51, 102, 0.15)"

CANDLE_SERIES: dict[str, str] = {
    "up": UP_COLOR,
    "down": DOWN_COLOR,
    "border_up": UP_COLOR,
    "border_down": DOWN_COLOR,
    "wick_up": UP_COLOR,
    "wick_down": DOWN_COLOR,
}

VOLUME_SERIES: dict[str, Any] = {
    "color": VOLUME_COLOR,
    "price_format": "volume",
    "price_scale_id": "",
    "scale_margin_top": 0.85,
    "scale_margin_bottom": 0,
    "up": VOLUME_UP_COLOR,
    "down": VOLUME_DOWN_COLOR,
}

BOLLINGER_SERIES: dict[str, Any] = {
    "upper_color": BB_EDGE_COLOR,
    "lower_color": BB_EDGE_COLOR,
    "middle_color": BB_MIDDLE_COLOR,
    "line_width_px": 1,
    "middle_line_style": 2,
    "fields": ["upper", "middle", "lower"],
}

MARKER_SKIN: dict[str, Any] = {
    "buy_position": "belowBar",
    "sell_position": "aboveBar",
    "buy_color": UP_COLOR,
    "sell_color": DOWN_COLOR,
    "buy_shape": "arrowUp",
    "sell_shape": "arrowDown",
    "amount_decimals": 4,
    "sorted_by": "time",
}

GRID_LINE_SKIN: dict[str, Any] = {
    "buy_color": GRID_BUY_COLOR,
    "sell_color": GRID_SELL_COLOR,
    "line_width_px": 1,
    "line_style": 2,
    "axis_label_visible": True,
    "cleared_before_draw": False,
}

WATERMARK: dict[str, Any] = {
    "visible": True,
    "font_size_px": 48,
    "text_source": SYMBOL_KEY,
}

TIME_SCALE: dict[str, Any] = {
    "time_visible": True,
    "seconds_visible": False,
}

BUY_SIDE = "buy"
SELL_SIDE = "sell"

CANDLE_FIELDS = ("time", "open", "high", "low", "close")
VOLUME_FIELD = "volume"
MARKER_FIELDS = ("time", "side", "amount")
GRID_LEVEL_FIELDS = ("price", "side", "level")

BRIDGE_OBJECT = "qtBridge"
BRIDGE_CALLBACK = "timeframeChanged"

SET_CANDLES_FORMAT = "setCandles('{payload}')"
UPDATE_CANDLE_FORMAT = "updateCandle('{payload}')"
SET_BOLLINGER_BANDS_FORMAT = "setBollingerBands('{payload}')"
ADD_TRADE_MARKER_FORMAT = "addTradeMarker('{payload}')"
SET_GRID_LEVELS_FORMAT = "setGridLevels('{payload}')"

CALL_FORMATS: dict[str, str] = {
    "set_candles": SET_CANDLES_FORMAT,
    "update_candle": UPDATE_CANDLE_FORMAT,
    "set_bollinger_bands": SET_BOLLINGER_BANDS_FORMAT,
    "add_trade_marker": ADD_TRADE_MARKER_FORMAT,
    "set_grid_levels": SET_GRID_LEVELS_FORMAT,
}

CALL_ORDER = (
    "set_candles",
    "update_candle",
    "set_bollinger_bands",
    "add_trade_marker",
    "set_grid_levels",
)

NO_CALLS: tuple = ()
ACTIONS: dict[str, str] = {}
TIMERS: dict[str, int] = {}
TIMER_DELAYS_MS: tuple[int, ...] = ()
BUS_TOPICS: tuple[str, ...] = ()
SKIN: dict[str, str] = {}


def theme_colors(theme: Any) -> dict:
    """The eight chrome colours of one theme, or the fallback theme's.

    A name the theme table does not carry falls back to
    ``cyberpunk_dark``, which is what the shipped chart shows for an
    unknown theme. A name the table cannot look up at all, such as a
    list, is refused. The answer is a copy, so a caller that adds the
    symbol to it leaves the theme table as it was.
    """
    return dict(CHART_THEMES.get(theme, CHART_THEMES[FALLBACK_THEME]))


def page_colors(symbol: Any, theme: Any) -> dict:
    """The nine values the page fills its holes from: eight plus the symbol."""
    colors = theme_colors(theme)
    colors[SYMBOL_KEY] = symbol
    return colors


def page_html(symbol: Any = DEFAULT_SYMBOL, theme: Any = DEFAULT_THEME) -> str:
    """The whole page for one symbol on one theme."""
    return CHART_HTML % page_colors(symbol, theme)


def call_text(name: str, payload: Any) -> str:
    """One call into the page: its name and its payload as JSON text.

    The payload is quoted inside a single-quoted JavaScript string, the
    way the shipped chart quotes it.
    """
    return CALL_FORMATS[name].format(payload=json.dumps(payload))


def marker_payload(time: Any, side: Any, amount: Any) -> dict:
    """The three values one trade marker carries."""
    return {"time": time, "side": side, "amount": amount}


def marker_position(side: Any) -> str:
    """Below the bar for a buy, above it for anything else."""
    if side == BUY_SIDE:
        return MARKER_SKIN["buy_position"]
    return MARKER_SKIN["sell_position"]


def marker_color(side: Any) -> str:
    """Green for a buy, red for anything else."""
    if side == BUY_SIDE:
        return MARKER_SKIN["buy_color"]
    return MARKER_SKIN["sell_color"]


def marker_shape(side: Any) -> str:
    """An up arrow for a buy, a down arrow for anything else."""
    if side == BUY_SIDE:
        return MARKER_SKIN["buy_shape"]
    return MARKER_SKIN["sell_shape"]


def grid_line_color(side: Any) -> str:
    """The wash one grid price line is drawn in, by its side."""
    if side == BUY_SIDE:
        return GRID_LINE_SKIN["buy_color"]
    return GRID_LINE_SKIN["sell_color"]


def volume_bar_color(open_price: Any, close_price: Any) -> str:
    """Green when the candle closed at or above its open, red below."""
    if close_price >= open_price:
        return VOLUME_UP_COLOR
    return VOLUME_DOWN_COLOR


def button_class(active: Any) -> str:
    """The class name one timeframe button carries, active or not."""
    if active:
        return BUTTON_SKIN["active_class_name"]
    return BUTTON_SKIN["class_name"]


def buttons(active: Any = ACTIVE_TIMEFRAME) -> list[dict]:
    """The seven timeframe buttons, with the one named here marked active."""
    return [
        dict(
            one,
            active=one["value"] == active,
            class_name=button_class(one["value"] == active),
        )
        for one in TIMEFRAME_BUTTONS
    ]


class TradingViewChartModel:
    """Holds the symbol, the theme and every call made into the page."""

    def __init__(
        self, symbol: Any = DEFAULT_SYMBOL, theme: Any = DEFAULT_THEME
    ) -> None:
        self._symbol = symbol
        self._theme = theme
        self._calls: list[str] = []
        self._html = page_html(symbol, theme)

    @property
    def symbol(self) -> Any:
        return self._symbol

    @property
    def theme(self) -> Any:
        return self._theme

    @property
    def html(self) -> str:
        return self._html

    @property
    def calls(self) -> list[str]:
        return list(self._calls)

    def run_js(self, js: str) -> str:
        """Record one call into the page and return it."""
        self._calls.append(js)
        return js

    def set_candles(self, ohlcv: Any) -> str:
        """Replace every candle and every volume bar the chart shows."""
        return self.run_js(call_text("set_candles", ohlcv))

    def update_candle(self, candle: Any) -> str:
        """Add or replace the newest candle and its volume bar."""
        return self.run_js(call_text("update_candle", candle))

    def set_bollinger_bands(self, data: Any) -> str:
        """Replace the three Bollinger lines drawn over the candles."""
        return self.run_js(call_text("set_bollinger_bands", data))

    def add_trade_marker(self, time: Any, side: Any, amount: Any) -> str:
        """Add one buy or sell arrow at one candle time."""
        return self.run_js(
            call_text("add_trade_marker", marker_payload(time, side, amount))
        )

    def set_grid_levels(self, levels: Any) -> str:
        """Draw one horizontal price line for each grid level given."""
        return self.run_js(call_text("set_grid_levels", levels))

    def set_theme(self, theme: Any) -> str:
        """Rebuild the whole page on another theme and return it.

        The page is replaced, so every call made into the old page is
        gone from the chart the operator sees.
        """
        self._theme = theme
        self._html = page_html(self._symbol, theme)
        return self._html


def build_view_model(
    symbol: Any = DEFAULT_SYMBOL,
    theme: Any = DEFAULT_THEME,
    active: Any = ACTIVE_TIMEFRAME,
) -> dict:
    """Return every part of the TradingView chart as one dict."""
    return {
        "accessible_name": WIDGET_ACCESSIBLE_NAME,
        "page": dict(PAGE),
        "web_view": dict(WEB_VIEW),
        "symbol": symbol,
        "theme": theme,
        "default_symbol": DEFAULT_SYMBOL,
        "default_theme": DEFAULT_THEME,
        "fallback_theme": FALLBACK_THEME,
        "symbol_key": SYMBOL_KEY,
        "script_url": SCRIPT_URL,
        "html": page_html(symbol, theme),
        "colors": page_colors(symbol, theme),
        "themes": {name: dict(one) for name, one in CHART_THEMES.items()},
        "theme_order": list(THEME_ORDER),
        "theme_keys": list(THEME_KEYS),
        "toolbar": dict(TOOLBAR),
        "button_skin": dict(BUTTON_SKIN),
        "buttons": buttons(active),
        "active_timeframe": active,
        "candle_series": dict(CANDLE_SERIES),
        "volume_series": dict(VOLUME_SERIES),
        "bollinger_series": dict(BOLLINGER_SERIES),
        "marker_skin": dict(MARKER_SKIN),
        "grid_line_skin": dict(GRID_LINE_SKIN),
        "watermark": dict(WATERMARK),
        "time_scale": dict(TIME_SCALE),
        "candle_fields": list(CANDLE_FIELDS),
        "volume_field": VOLUME_FIELD,
        "marker_fields": list(MARKER_FIELDS),
        "grid_level_fields": list(GRID_LEVEL_FIELDS),
        "buy_side": BUY_SIDE,
        "sell_side": SELL_SIDE,
        "bridge_object": BRIDGE_OBJECT,
        "bridge_callback": BRIDGE_CALLBACK,
        "call_formats": dict(CALL_FORMATS),
        "call_order": list(CALL_ORDER),
        "calls": list(NO_CALLS),
        "logger_name": LOGGER_NAME,
        "missing_webengine_warning": MISSING_WEBENGINE_WARNING,
        "actions": dict(ACTIONS),
        "timers": dict(TIMERS),
        "timer_delays_ms": list(TIMER_DELAYS_MS),
        "bus_topics": list(BUS_TOPICS),
        "skin": dict(SKIN),
    }


def view_model(params: dict) -> dict:
    """Bridge handler for ``tradingview.chart``.

    Reads ``symbol``, ``theme`` and ``active`` from the request
    parameters. Nothing is held between calls, so two calls with the
    same parameters answer the same.
    """
    return build_view_model(
        params.get("symbol", DEFAULT_SYMBOL),
        params.get("theme", DEFAULT_THEME),
        params.get("active", ACTIVE_TIMEFRAME),
    )
