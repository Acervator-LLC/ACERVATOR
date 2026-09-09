# 2026-09-08 — Charts: `native_chart.js` registers a panel in the shell

Issue #128, row 773 of the conversion table in
[08-tabs.md](../../docs/manual/08-tabs.md). Files changed:
`src/gui/web/native_chart.js`, `src/gui/web/trade_charts_tab.js`,
`src/gui/main_tabs/trade_charts_tab_surface.py` and
`src/gui/main_tabs/native_chart_surface.py`. No test file was written.

The Electron shell ran from `desktop/main.js` under the installed Electron
binary with a throwaway home, and the renderer was read over the Chrome
DevTools Protocol. The Qt Charts tab was built offscreen under
`PYTHONWARNINGS=error` with `python -X dev -X faulthandler`.

The Charts tab does not answer `ACERVATOR_VARIANT`. `variant_surface.py`
registers sixteen screens and Charts is not one of them, and
`charts_tab.py` builds `TradeChartsTab` under either name. Qt was reached
by building that widget, and React by the Electron shell.

Pictures:

```
qt    <scratchpad>/u128/qt_charts_tab_128.png
react <scratchpad>/u128/react_charts_tab_128.png
```

---

## 1 — The shell reported the chart as a module that draws no panel

### 1.1 the error

No traceback. The panel host names the panel and the reason, and it named this
one:

```
nativeChartReason = native_chart.js registered no panel to draw
registered = 15 names, native_chart absent
```

The 15 were `bot_live_settings`, `bot_swarm_tab`, `bot_visualizer`,
`console_tab`, `header_strip`, `history_tab`, `market_inspector`,
`market_inspector_tab`, `market_inspector_topologies`, `paper_trader_tab`,
`proof_of_accumulation_tab`, `simulator_tab`, `system_status_tab`,
`trade_charts_tab` and `trading_tab`.

### 1.2 reproduction

```
electron.exe --user-data-dir=<scratchpad> --remote-debugging-port=9334 <tree>/desktop
ACERVATOR_BRIDGE_ARGV="-m src.core.desktop_bridge"
window.acervatorPanelHost.registered()
window.acervatorPanelHost.reasonFor('native_chart')
```

Electron exits with status 0x80000003 and prints nothing when it is given no
`--user-data-dir` under this session, so the switch is part of the run. A
reload does not always take a changed module, so every reading below comes
from a shell started after the edit.

### 1.3 the cause

`native_chart.js` published `acervatorChart` on the window and never called
`acervatorPanelHost.register`. The host names a module by the script tag
running, so a module that does not call it is recorded as one that draws
nothing.

### 1.4 the correction

The module registers the chart it already draws. It names no bridge method, so
the tab bar gives it no tab of its own, which is what
`market_inspector_topologies.js` and `bot_live_settings.js` already do.

```javascript
  if (global.acervatorPanelHost) {
    global.acervatorPanelHost.register({
      render: renderChart,
      load: loadChart,
      loadError: loadError
    });
  }
```

### 1.5 the rerun

```
nativeChartReason = null
registered = 16 names, native_chart present
tabs = 10, unclaimed = [], faults = []
```

The ten tabs the application reports are unchanged, no application tab went
unclaimed, and the host recorded no fault.

---

## 2 — The chart drew its empty state, and the registration was not the draw path

### 2.1 the error

The chart was constructed and drawn inside the Charts tab, and what it drew was
the empty view.

```
chartMountCount   1
chartMountDrawn   1
chartMountMarkup  716
chartMountText    1dWaiting for data...
chartMountSymbol  ""
chartMountCandleAttr 180
```

The same run with the registration removed reported the same six values, so the
draw did not come from the registration.

### 2.2 reproduction

The Charts tab was mounted on one payload: the 38 running bots of the saved
fleet in `~/.acervator/bot_state.json`, and 180 real daily BTC/USD candles from
`ChartDataFetcher`.

```
assetCount 38  shownSymbol BTC/USD  selectorPosition "6 of 38"
panelCandles 180  panelSource "CoinGecko (30d)"  panelChartTimeframe 1d
```

### 2.3 the cause

Three values the Charts tab holds did not reach the chart, and the chart was
drawn around the panel host rather than through it.

`src/gui/web/trade_charts_tab.js` — the request each chart slot sent

```javascript
          return global.acervator.call(api.method, {
            reset: true,
            symbol: symbol,
            timeframe: mount.getAttribute(CHART_TF_ATTR)
          });
```

The model carries `panel.candles` with 180 rows and the request carried none,
so `native_chart.state` built a chart with no candles. The symbol came from
`panel.built_with`, and the panel is built once as `PanelSink("")` and renamed
through `label`, so that value was empty for the life of the panel. No width or
height was sent either, so the panes laid out at zero and the header and the
OHLC row drew on top of each other. The draw itself called
`acervatorChart.renderChart` directly, which needs no registration.

### 2.4 the correction

The panel carries the symbol it follows, under a name that says so.

```python
    def set_symbol_property(self, symbol: Any) -> None:
        """Rename the chart through its public setter, which repaints."""
        self.symbol = symbol
        self.label = symbol
```

The chart slot sends the panel's symbol, its source, its candles and the pixel
size of the mount, and the panel host does the drawing.

```javascript
          return global.acervator.call(api.method, {
            reset: true,
            symbol: symbol,
            timeframe: mount.getAttribute(CHART_TF_ATTR),
            source: text(panel[SOURCE]),
            candles: candles,
            width: mount.clientWidth,
            height: mount.clientHeight
          });
```

```javascript
          host.mount(CHART_SLOT, mount, model);
```

`native_chart.state` reads a candle row of six numbers as well as a mapping,
because the tab holds its candles as rows, and it reads a `source`.

```python
def candle_of(given: dict | Sequence) -> "Candle":
    if isinstance(given, dict):
        return Candle(
            given["time"],
            given["open"],
            given["high"],
            given["low"],
            given["close"],
            given.get("volume", 0.0),
        )
    return Candle(*given)
```

### 2.5 the rerun

```
chartMountSymbol  BTC/USD
chartMountMarkup  101014
chartMountText    BTC/USD 1d - CoinGecko (30d) - 180 candles
                  O 78,451.00 H 78,905.00 L 78,446.00 C 78,623.00 +172 (+0.22%)
                  VOL 0.00  65,000.00 70,000.00 75,000.00 80,000.00 Vol 1
                  78,623.00  08-10 08-15 08-20 08-25 08-30 09-04
```

The control run discriminates now. With the registration removed and nothing
else changed, the same drive answers:

```
nativeChartReason  native_chart.js registered no panel to draw
pageFault          native_chart
chartMountMarkup   76
chartMountText     Panel native_chart did not draw: native_chart.js registered
                   no panel to draw
```

76 characters against 101,014. The registered panel is the path that draws.

---

## The two pictures

The Qt tab and the React tab were driven with the same payload, the same asset
and the same 180 candles. The roll call is `CHART_OVERLAYS` in
`src/gui/native_chart.py`, one entry per overlay the chart can draw, read off
the live widget.

| item | Qt picture | React picture |
| --- | --- | --- |
| list toggle `Live` | drawn | drawn |
| selector, `BTC/USD`, `6 of 38` | drawn | drawn |
| header | `BTC/USD 1d - CoinGecko (30d) - 180 candles` | the same |
| OHLC row | `O 78,451.00 H 78,905.00 L 78,446.00 C 78,623.00 +172 (+0.22%) VOL 0.00` | the same |
| candle series | 180 candles, index 0 to 179 | 180 candles, index 0 to 179 |
| high and low in the window | 82,108.00 and 62,525.00 | 82,108.00 and 62,525.00 |
| last-price line and box | `78,623.00` | `78,623.00` |
| price axis ticks | `75,000.00` `70,000.00` `65,000.00` | the same |
| volume axis label | `Vol 1` | `Vol 1` |
| time axis | clipped, the widget has 250 of the 492 pixels it asks for | `08-10` to `09-04` |
| `bb` Bollinger bands | drawn | absent |
| `ichimoku` cloud | drawn | absent |
| `vortex` sub-pane | drawn, `Vortex (14)`, `0.8761` | absent |
| `macd` sub-pane | on, clipped | absent |
| `stochrsi` sub-pane | on, clipped | absent |
| `volume` bars | none, every candle carries volume 0 | none, the same |
| `slingshot` | off | off |
| `bbullseye` | off | off |
| toggle row, eight boxes | drawn | absent |
| legend `Invisible` / `On Book` | drawn | absent |

```
bb         starts_on=True  shown=True
vortex     starts_on=True  shown=True
macd       starts_on=True  shown=True
stochrsi   starts_on=True  shown=True
ichimoku   starts_on=True  shown=True
volume     starts_on=True  shown=True
slingshot  starts_on=False shown=False
bbullseye  starts_on=False shown=False
```

Eight of the eighteen items differ, so row 773 keeps `no` under Registers in
Electron.

## What is left

Nothing fills the chart's overlay series. `ChartModel.set_indicator_series` is
never called, so `native_chart.state` answers with every series empty and
`active_sub_panes` finds none.

```
flags     show_bb true, show_vortex true, show_macd true, show_stochrsi true,
          show_ichimoku true, show_volume true
sub_panes []
bb_data 0  vortex_data 0  macd_data 0  stochrsi_data 0  ichimoku_data 0
```

`CandlestickChart._compute_indicators` fills the Qt side from the engine
classes and runs on every `set_candles`. The React side has no caller for the
same five series. `native_chart.js` also draws no toggle row and no position
legend, which the Qt panel draws around the chart.

## One value the chart cannot fall back on

`COINGECKO_DAYS` in `src/exchange/chart_data.py` maps the `1h` timeframe to
`days=2`, and the endpoint answers `HTTP 400` for that value. `15m`, `1d` and
`1w` answered with 48, 180 and 45 candles in the same run. `1h` is the chart's
default timeframe. Changing the number changes the window every 1h chart falls
back to, which is a figure the operator reads, so it is recorded and not
changed here.
