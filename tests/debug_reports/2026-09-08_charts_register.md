# 2026-09-08 — Charts: `native_chart.js` registers a panel in the shell

Issue #128, row 773 of the conversion table in
[08-tabs.md](../../docs/manual/08-tabs.md). File changed:
`src/gui/web/native_chart.js`. No test file was written.

The Electron shell ran from `desktop/main.js` under the installed Electron
binary with a throwaway home, and the renderer was read over the Chrome
DevTools Protocol. The Qt Charts tab was built offscreen under
`PYTHONWARNINGS=error` with `python -X dev -X faulthandler`.

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
electron.exe --user-data-dir=<scratchpad> --remote-debugging-port=9333 <tree>/desktop
ACERVATOR_BRIDGE_ARGV="-m src.core.desktop_bridge"
window.acervatorPanelHost.registered()
window.acervatorPanelHost.reasonFor('native_chart')
```

Electron exits with status 0x80000003 and prints nothing when it is given no
`--user-data-dir` under this session, so the switch is part of the run.

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

## 2 — The chart draws its empty state, and the registration is not what draws it

### 2.1 the error

The chart is constructed and drawn inside the Charts tab, and what it draws is
the empty view.

```
chartMountCount   1
chartMountDrawn   1
chartMountMarkup  716
chartMountText    1dWaiting for data...
chartMountSymbol  ""
chartMountCandleAttr 180
```

The same run with the registration removed reports the same six values. The
draw does not come from the registration.

### 2.2 reproduction

The Charts tab was mounted on one payload: the 38 running bots of the saved
fleet in `~/.acervator/bot_state.json`, and 180 real daily BTC/USD candles from
`ChartDataFetcher`.

```
assetCount 38  shownSymbol BTC/USD  selectorPosition "6 of 38"
panelCandles 180  panelSource "CoinGecko (30d)"  panelChartTimeframe 1d
```

### 2.3 the cause

Two values the Charts tab holds do not reach the chart.

`src/gui/web/trade_charts_tab.js` — the request each chart slot sends

```javascript
          return global.acervator.call(api.method, {
            reset: true,
            symbol: symbol,
            timeframe: mount.getAttribute(CHART_TF_ATTR)
          });
```

The model carries `panel.candles` with 180 rows and the request carries none,
so `native_chart.state` builds a chart with no candles. The symbol is read from
`panel.built_with`, and `trade_charts_tab_surface.py` line 733 builds the panel
as `PanelSink("")` and renames it through `label`, so `data-symbol` is empty for
the life of the panel.

### 2.4 the correction

None here. Both values live in `src/gui/web/trade_charts_tab.js` and
`src/gui/main_tabs/trade_charts_tab_surface.py`, which are row 811 of the
conversion table and not this unit.

### 2.5 the rerun

Not applicable. The chart draws the empty view before and after the change.

---

## The two pictures

The Qt tab and the React tab were driven with the same payload, the same asset
and the same 180 candles.

| item | Qt picture | React picture |
| --- | --- | --- |
| list toggle `Live` | drawn | drawn |
| selector, `BTC/USD`, `6 of 38` | drawn | drawn |
| panel header | `BTC/USD 1d • CoinGecko (30d) • 180 candles` | `BTC/USD` only |
| OHLC row | `O 78,451.00 H 78,905.00 L 78,446.00 C 78,623.00 +172 (+0.22%) VOL 0.00` | absent |
| candle series | 180 candles, index 0 to 179 | absent |
| high and low extremes | 82,108.00 and 62,525.00 | absent |
| Bollinger bands (`bb`) | drawn | absent |
| Ichimoku cloud (`ichimoku`) | drawn | absent |
| Vortex (`vortex`) | drawn, sub-pane labelled `Vortex (14)` | absent |
| MACD (`macd`) | on, pane clipped | absent |
| Stochastic RSI (`stochrsi`) | on, pane clipped | absent |
| Volume (`volume`) | strip drawn, axis label `Vol 1` | absent |
| Slingshot (`slingshot`) | off | off |
| BB Bullseye (`bbullseye`) | off | off |
| price axis | `78,623.00` boxed, `75,000.00`, `70,000.00`, `65,000.00` | absent |
| time axis | drawn | absent |
| toggle row, eight boxes | drawn | absent |
| legend `Invisible` / `On Book` | drawn | absent |
| source label | `CoinGecko (30d)` | `CoinGecko (30d)` |
| chart status line | absent | `Waiting for data...` |

The roll call is `CHART_OVERLAYS` in `src/gui/native_chart.py`, one entry per
overlay the chart can draw, read off the live widget:

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

The pictures do not match, so row 773 keeps `no` under Registers in Electron.

Two figures the pictures carry that are not defects in this change. The Qt chart
was given 250 pixels and asks for 492 for its six switched-on panes, so the MACD
and Stochastic RSI panes are clipped at 1400 by 900. Every candle carries a
volume of 0, because the CoinGecko OHLC endpoint serves no volume, so the volume
strip is empty on both sides.

## One value the chart cannot fall back on

`COINGECKO_DAYS` in `src/exchange/chart_data.py` maps the `1h` timeframe to
`days=2`, and the endpoint answers `HTTP 400` for that value. `15m`, `1d` and
`1w` answered with 48, 180 and 45 candles in the same run. `1h` is the chart's
default timeframe. Changing the number changes the window every 1h chart falls
back to, which is a figure the operator reads, so it is recorded and not
changed here.
