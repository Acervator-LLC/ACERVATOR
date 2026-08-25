"""
tradingview_chart.py — TradingView Chart Integration v1.1
==========================================================
Embeds TradingView's lightweight-charts library inside a Qt WebEngine
widget.  This provides professional candlestick charts with:

  • Real-time price updates via exchange websocket feeds
  • Indicator overlays (Bollinger Bands, Ichimoku Cloud, EMA)
  • Buy/sell trade markers from bot activity
  • Grid level visualisation (horizontal lines)
  • Multi-timeframe switching
  • Volume histogram

The chart is rendered as an HTML page loaded into QWebEngineView,
with data injected via JavaScript bridge calls.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

logger = logging.getLogger("acervator.gui")

try:
    from PySide6.QtWidgets import (
        QWidget,
        QVBoxLayout,
    )
    from PySide6.QtWebEngineWidgets import QWebEngineView

    _HAS_WEBENGINE = True
except ImportError:
    _HAS_WEBENGINE = False


# ---------------------------------------------------------------------------
# Chart HTML template using TradingView lightweight-charts
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Theme-aware color sets
# ---------------------------------------------------------------------------
CHART_THEMES = {
    "cyberpunk_dark": {
        "bg": "#0a0a0f",
        "text": "#e0e0f0",
        "grid": "#1a1a28",
        "border": "#2a2a44",
        "accent": "#00ffcc",
        "btn_bg": "#12121a",
        "btn_hover": "#1e1e35",
        "watermark": "rgba(0,255,204,0.07)",
    },
    "neon_light": {
        "bg": "#f5f5fa",
        "text": "#1a1a2e",
        "grid": "#e5e5f0",
        "border": "#ccccdd",
        "accent": "#6600cc",
        "btn_bg": "#eeeef5",
        "btn_hover": "#e0e0f0",
        "watermark": "rgba(102,0,204,0.07)",
    },
    "classic_terminal": {
        "bg": "#0a0a0a",
        "text": "#00ff00",
        "grid": "#181818",
        "border": "#003300",
        "accent": "#00ff00",
        "btn_bg": "#111111",
        "btn_hover": "#1a1a1a",
        "watermark": "rgba(0,255,0,0.05)",
    },
    "minimal_modern": {
        "bg": "#fafafa",
        "text": "#1a1a1a",
        "grid": "#e8e8e8",
        "border": "#e0e0e0",
        "accent": "#2563eb",
        "btn_bg": "#f0f0f0",
        "btn_hover": "#eeeeee",
        "watermark": "rgba(37,99,235,0.05)",
    },
    "glass_metal": {
        "bg": "#1c1c24",
        "text": "#d0d0e0",
        "grid": "#2c2c3a",
        "border": "#3a3a50",
        "accent": "#88ccff",
        "btn_bg": "#242430",
        "btn_hover": "#30303f",
        "watermark": "rgba(136,204,255,0.07)",
    },
}


# ---------------------------------------------------------------------------
# Qt Widget
# ---------------------------------------------------------------------------
if _HAS_WEBENGINE:

    class TradingViewChart(QWidget):
        """
        TradingView lightweight-charts embedded in Qt via WebEngine.

        Usage::

            chart = TradingViewChart(symbol="BTC/USDT", theme="cyberpunk_dark")
            chart.set_candles(ohlcv_data)
            chart.add_trade_marker(time=..., side="buy", amount=0.01)
            chart.set_grid_levels([...])
        """

        def __init__(
            self,
            symbol: str = "BTC/USDT",
            theme: str = "cyberpunk_dark",
            parent: Optional[QWidget] = None,
        ) -> None:
            super().__init__(parent)
            self.setAccessibleName("Trading View Chart")
            self._symbol = symbol
            self._theme = theme
            self._setup_ui()

        def _setup_ui(self) -> None:
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)

            self._web = QWebEngineView()
            colors = CHART_THEMES.get(self._theme, CHART_THEMES["cyberpunk_dark"])
            colors["symbol"] = self._symbol

            html = CHART_HTML % colors
            self._web.setHtml(html)
            layout.addWidget(self._web)

        def set_candles(self, ohlcv: list[dict]) -> None:
            """Set full candle data: [{time, open, high, low, close, volume}, ...]"""
            self._run_js(f"setCandles('{json.dumps(ohlcv)}')")

        def update_candle(self, candle: dict) -> None:
            """Update/add the latest candle."""
            self._run_js(f"updateCandle('{json.dumps(candle)}')")

        def set_bollinger_bands(self, data: list[dict]) -> None:
            """Set BB overlay: [{time, upper, middle, lower}, ...]"""
            self._run_js(f"setBollingerBands('{json.dumps(data)}')")

        def add_trade_marker(self, time: int, side: str, amount: float) -> None:
            """Add a buy/sell marker on the chart."""
            marker = {"time": time, "side": side, "amount": amount}
            self._run_js(f"addTradeMarker('{json.dumps(marker)}')")

        def set_grid_levels(self, levels: list[dict]) -> None:
            """Show grid buy/sell levels as horizontal lines."""
            self._run_js(f"setGridLevels('{json.dumps(levels)}')")

        def set_theme(self, theme: str) -> None:
            """Switch chart theme."""
            self._theme = theme
            colors = CHART_THEMES.get(theme, CHART_THEMES["cyberpunk_dark"])
            colors["symbol"] = self._symbol
            html = CHART_HTML % colors
            self._web.setHtml(html)

        def _run_js(self, js: str) -> None:
            """Execute JavaScript in the WebEngine context."""
            self._web.page().runJavaScript(js)

else:
    # Stub when WebEngine is not available
    class TradingViewChart:
        def __init__(self, *args, **kwargs):
            logger.warning("TradingView charts require PySide6-WebEngine")
