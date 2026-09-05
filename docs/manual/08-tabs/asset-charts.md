# Asset Charts

Reference. One candlestick panel per traded symbol.

## What builds it

The builder mixin makes the tab and adds it to the row. The tab is a scroll
area holding one panel per active bot.

`src/gui/main_tabs/charts_tab.py` — `ChartsTabMixin._build_charts_tab`

```python
def _build_charts_tab(self) -> None:
    """Build the Asset Charts tab and add it to the main tab widget."""
    # --- Tab 2: Charts ---
    self._charts_tab = TradeChartsTab()
    self._main_tabs.addTab(self._charts_tab, "Asset Charts")
```

One method rebuilds that panel set from the current roster.

`src/gui/widgets/trade_charts_tab.py` — `TradeChartsTab.update_charts`

```python
def update_charts(
    self,
    bot_statuses: list[dict],
    bot_manager=None,
    exchange_connectors: dict = None,
) -> None:
    """Create or update chart panels for each bot.
```

Three more methods keep a panel current.

| Method | What it does |
| ------ | ------------ |
| `_on_tf_changed` | Changes one panel's timeframe, leaving the others alone |
| `log_trade` | Adds a fill marker to the panel that owns the symbol |
| `push_synthetic_candles` | Feeds a panel whose venue returned no history |

## The chart widget

`CandlestickChart` in `src/gui/native_chart.py` paints each panel with
QPainter. No browser and no WebEngine dependency.

Four record types carry everything drawn over the candles.

| Record | Draws |
| ------ | ----- |
| `Candle` | One open, high, low, close and volume bar |
| `TradeMarker` | An executed buy or sell |
| `PositionMarker` | A holding, with a distinct icon for invisible and visible |
| `GridLine` | A buy or sell level |

The position record is the one that carries the visibility mode, which is what
tells an invisible holding from one resting on the book.

`src/gui/native_chart.py` — `PositionMarker`

```python
@dataclass
class PositionMarker:
    """Active position shown on chart with visibility mode icon."""

    price: float
    side: str  # "buy" or "sell"
    visibility: str  # "internal" (invisible) or "orderbook" (visible)
    level: int = 0  # Grid level index
    filled: bool = False
    asset_held: float = 0.0
```

The setters name what they place.

| Setter | Places |
| ------ | ------ |
| `set_candles` | The candle series |
| `add_marker` | One executed fill |
| `set_trade_history_markers` | The fills already on record |
| `set_positions` | The holdings, invisible and on book |
| `set_grid_lines` | The buy and sell levels |
| `set_tranche_floors` | The standing fold-tranche floors |
| `set_target_balance_lines` | The dollar target |
| `set_fire_armed_state` | An armed manual fire |
| `set_source_label` | The feed the candles arrived on |
| `set_error` | A failure message in place of the panel body |

The mouse handlers give the panel a crosshair with a price and time readout,
drag panning and a wheel zoom bounded by `_effective_visible_start` and
`_effective_visible_count`.

## Indicators on the chart

The chart calls the engine rather than computing anything of its own. Five
series arrive that way, and an entry with no value is skipped when the panel
paints.

`src/gui/native_chart.py` — `CandlestickChart._compute_indicators`

```python
def _compute_indicators(self):
    """Fill ``_bb_data``, ``_vortex_data``, ``_macd_data``,
    ``_stochrsi_data`` and ``_ichimoku_data`` from the engine
    classes. A ``None`` entry marks a candle with no value, and
    ``paintEvent`` skips it.
    """
```

The toolbar under each panel holds the timeframe picker and eight toggles.

`src/gui/main_tabs/native_chart_surface.py` — `INDICATOR_TOGGLES`

```python
INDICATOR_TOGGLES = (
    ("bb", "BB", "#50a0f0"),
    ("vortex", "Vortex", "#00ff88"),
    ("macd", "MACD", "#ffcc00"),
    ("stochrsi", "SRsi", "#ff9060"),
    ("ichimoku", "Ichi", "#c080ff"),
    ("volume", "Vol", "#80ffcc"),
    ("slingshot", "Sling", "#ff4488"),
    ("bbullseye", "BBull", "#ff00aa"),
)
```

Volume starts on and the other seven start off.

`src/gui/main_tabs/native_chart_surface.py` — `INDICATOR_DEFAULTS`

```python
INDICATOR_DEFAULTS = {
    "bb": False,
    "vortex": False,
    "macd": False,
    "stochrsi": False,
    "ichimoku": False,
    "volume": True,
    "slingshot": False,
    "bbullseye": False,
}
```

Sling and BBull paint a placeholder shape rather than the indicator, and each
says as much in its own tooltip. Issue #430 carries one further disagreement
between a tooltip on this toolbar and what the chart paints.

The complete voter set and the maths behind each indicator belong to
[the Indicator Voting Panel](../07-indicators.md).

## Where the candles come from

Three sources in order: the connected exchange first, a public API second, and
the last successful fetch third. Each source that fails is recorded and the
next one runs.

`src/exchange/chart_data.py` — `ChartDataFetcher.fetch`

```python
# --- Source 1: Exchange OHLCV via CCXT ---
if exchange is not None:
    try:
        candles, source = await self._fetch_exchange(
            exchange, symbol, timeframe, limit
        )
        if candles:
            self._set_cache(symbol, timeframe, candles)
            return candles, source
```

With every source exhausted the fetcher returns an empty list and a label
naming what failed, and the panel draws that label rather than an empty grid.

`src/exchange/chart_data.py` — `ChartDataFetcher.fetch`

```python
# All sources failed
error_detail = " | ".join(errors) if errors else "No sources available"
```

Each row arrives as an `OHLCVCandle`.

## The other chart

`src/gui/tradingview_chart.py` holds the QWebEngineView chart, which runs HTML
and JavaScript inside the Chromium that PySide6 already ships. The Asset Charts
tab does not use it; the panels above are painted natively. Its one
construction site is the stock window, and the application builds no stock
window, so no screen draws it today.

`src/gui/stock_main_window.py` — the one construction site

```python
from .tradingview_chart import TradingViewChart

self._chart = TradingViewChart(symbol="AAPL", theme="dark")
```

## Bridge

Three methods serve this screen.

| Bridge method | Renderer module |
| ------------- | --------------- |
| `native_chart.state` | `native_chart.js` |
| `trade_charts_tab.state` | `trade_charts_tab.js` |
| `tradingview.chart` | `tradingview_chart.js` |

Back to [the subsystem index](README.md).
