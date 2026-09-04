# Asset Charts

Reference. One candlestick panel per traded symbol.

## What builds it

`ChartsTabMixin._build_charts_tab` in `src/gui/main_tabs/charts_tab.py`
constructs `TradeChartsTab` from `src/gui/widgets/trade_charts_tab.py`.
The tab is a scroll area holding one panel per active bot.

- `update_charts` rebuilds the set from the current bot roster.
- `_on_tf_changed` changes one panel's timeframe without touching the
  others.
- `log_trade` adds a fill marker to the panel that owns the symbol.
- `push_synthetic_candles` feeds a panel whose venue returned no history.

## The chart widget

`CandlestickChart` in `src/gui/native_chart.py` paints each panel with
QPainter. No browser and no WebEngine dependency.

Four record types carry everything drawn over the candles:

| Record | Draws |
| ------ | ----- |
| `Candle` | One open, high, low, close and volume bar |
| `TradeMarker` | An executed buy or sell |
| `PositionMarker` | A holding, with a distinct icon for invisible and visible |
| `GridLine` | A buy or sell level |

The setters name what they place: `set_candles`, `add_marker`,
`set_trade_history_markers`, `set_positions`, `set_grid_lines`,
`set_tranche_floors` for the standing fold-tranche floors,
`set_target_balance_lines` for the dollar target, and
`set_fire_armed_state` for an armed manual fire. `set_source_label` names
the feed the candles arrived on and `set_error` replaces the panel body
when the fetch failed.

The mouse handlers give the panel a crosshair with a price and time
readout, drag panning and a wheel zoom bounded by
`_effective_visible_start` and `_effective_visible_count`.

## Indicators on the chart

`_compute_indicators` calls the engine rather than computing anything of
its own. The five series it reads are `BollingerBands`, `IchimokuCloud`,
`MACD`, `StochasticRSI` and `VortexIndicator` from
`src/trading/ta_engine.py`. `_natural_height_for_panes` and
`_apply_height_for_panes` grow the panel as panes switch on.

The complete voter set and the maths behind each indicator belong to
[the Indicator Voting Panel](../07-indicators.md).

## Where the candles come from

`ChartDataFetcher` in `src/exchange/chart_data.py` fetches with
redundancy: exchange OHLCV through the connected connector first, the
CoinGecko public API second, and the last successful fetch held in memory
third. Each row arrives as an `OHLCVCandle`.

## The other chart

`src/gui/tradingview_chart.py` holds the QWebEngineView chart, which runs
HTML and JavaScript inside the Chromium that PySide6 already ships. The
Asset Charts tab does not use it; the panels above are painted natively.

## Bridge

`native_chart_surface` answers `native_chart.state`,
`trade_charts_tab_surface` answers `trade_charts_tab.state`, and
`tradingview_chart_surface` answers `tradingview.chart`. The renderer
modules are `native_chart.js`, `trade_charts_tab.js` and
`tradingview_chart.js`.

Back to [the subsystem index](README.md).
