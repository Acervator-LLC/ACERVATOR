# 2026-09-09 — Live tab: the voting panel and the Activity Log register a panel

Issue #128, rows 852 and 917 of the conversion table in
[08-tabs.md](../../docs/manual/08-tabs.md). Files changed:
`src/gui/web/indicator_panel.js`, `src/gui/web/status_log.js` and
`src/gui/web/trading_tab.js`. No test file was written.

The Electron shell ran from `desktop/main.js` under the installed Electron
binary with a throwaway home, and the renderer was read over the Chrome
DevTools Protocol. The Qt Live tab was built under `PYTHONWARNINGS=error` with
`python -X dev -X faulthandler`.

The Live tab does not answer `ACERVATOR_VARIANT`. `src/_variant.py` is read by
`history_table_variant.py`, `history_qt_table.py` and `variant_surface.py` and
by nothing else, and `trading_tab.py` builds the same Qt widgets under either
name. Qt was reached by building `TradingTabMixin._build_trading_tab` on a host
carrying a tab book, and React by the Electron shell.

Pictures:

```
qt    <scratchpad>/u128trading/qt_trading_tab_128.png
react <scratchpad>/u128trading/react_trading_tab_128.png
```

The one reading both were driven with: 180 daily BTC/USD candles from CoinGecko
run through `VotingEngine.compute_all` at 15m, 1h and 1d, and eight Activity Log
messages. Every number below the React side draws was computed in Python and
served over the bridge; the module recomputes none of them.

---

## 1 — The shell named both modules as panels that draw nothing

### 1.1 the error

No traceback. The panel host names the panel and the reason, and it named both
of these:

```
indicatorReason = indicator_panel.js registered no panel to draw
statusLogReason = status_log.js registered no panel to draw
registered = 16 names, indicator_panel absent, status_log absent
```

The 16 were `bot_live_settings`, `bot_swarm_tab`, `bot_visualizer`,
`console_tab`, `header_strip`, `history_tab`, `market_inspector`,
`market_inspector_tab`, `market_inspector_topologies`, `native_chart`,
`paper_trader_tab`, `proof_of_accumulation_tab`, `simulator_tab`,
`system_status_tab`, `trade_charts_tab` and `trading_tab`.

Both panels drew anyway, 42,226 and 4,532 characters of markup, because the
Live tab called each module's own render function and the host was never asked.

### 1.2 reproduction

```
electron.exe <tree>/desktop --user-data-dir=<scratchpad> --remote-debugging-port=9341
ACERVATOR_BRIDGE_ARGV="-m src.core.desktop_bridge"
window.acervatorPanelHost.registered()
window.acervatorPanelHost.reasonFor('indicator_panel')
window.acervatorPanelHost.reasonFor('status_log')
```

`ELECTRON_RUN_AS_NODE=1` is set in this session's environment and makes the
binary start as Node, which prints `bad option: --user-data-dir` and then
`Cannot find module 'electron'`. The variable is dropped from the child
environment, so every reading below comes from a shell started without it.

### 1.3 the cause

`indicator_panel.js` published `acervatorIndicatorPanel` on the window and
`status_log.js` published `acervatorLog`, and neither called
`acervatorPanelHost.register`. The host names a module by the script tag
running, so a module that does not call it is recorded as one that draws
nothing. `trading_tab.js` then reached past the host into each module.

`src/gui/web/trading_tab.js` — how the Activity Log was drawn

```javascript
    slot.setAttribute(CHILD_ATTR, STATUS_LOG_MODULE);
    return api.renderLog(slot);
```

### 1.4 the correction

Each module registers the panel it already draws. Neither names a bridge
method, so the tab bar gives neither a tab of its own, which is what
`native_chart.js` already does for the Charts tab.

```javascript
  if (global.acervatorPanelHost) {
    global.acervatorPanelHost.register({
      render: renderPanel,
      load: loadPanel,
      loadError: loadError
    });
  }
```

The Live tab hands each slot and the view model it loaded to the host, which is
what `trade_charts_tab.js` does with the chart.

```javascript
    slot.setAttribute(CHILD_ATTR, STATUS_LOG_MODULE);
    return host.mount(STATUS_LOG_MODULE, slot, model) ? slot : null;
```

### 1.5 the rerun

```
indicatorReason = null
statusLogReason = null
registered = 18 names, indicator_panel present, status_log present
tabs = 10, unclaimed = [], faults = [], data-panel-error = null
```

The ten tabs the application reports are unchanged, no application tab went
unclaimed, and the host recorded no fault. The tab the shell settles on after
boot is still `simulator_tab`, so the two new screen names do not take the
opening tab.

---

## 2 — Constructed and drawn

### 2.1 what the run reports

```
tradingOpened   true
indicatorSlot   data-child-module=indicator_panel  data-panel-error=null  markup 43264
statusSlot      data-child-module=status_log       data-panel-error=null  markup 4532
bars 12  pillars 3  log lines 8
```

`host.mount` calls the registered panel's own `render`, so those two markup
counts are the panel being built and drawn inside the Live tab. This is the run
the React picture comes from.

### 2.2 the control

The two registrations were taken out, nothing else changed, and the same
reading was driven in.

```
indicatorReason  indicator_panel.js registered no panel to draw
statusLogReason  status_log.js registered no panel to draw
data-panel-error status_log,indicator_panel
indicatorSlot    markup 82, text "Panel indicator_panel did not draw: ..."
statusSlot       markup 72, text "Panel status_log did not draw: ..."
bars 0  pillars 0  log lines 0
```

82 characters against 43,264 and 72 against 4,532. The registered panel is the
path that draws.

---

## 3 — The React panel overflowed its slot and lost every base label

### 3.1 the error

The panel drew, and 70 pixels of it fell below the space the Live tab gives it.
The slot ends at 543.4 and the panel's own content ran on past it.

```
indicator slot     132 to 543.4
pillar floor       591.2
pillar labels      591.2 to 613.2
row-B bar labels   bottom 608.0
```

Qt at the same tab size ends its panel at 472 and its floor at 428, so
everything is inside. The three pillar labels and the six row-B bar labels were
in the picture on the Qt side and off the bottom on the React side.

### 3.2 reproduction

Both builds driven with the shared reading, the Qt tab built at 1386 by 708,
which is the space the shell gives the React tab.

```
window.acervatorTabBar.select('trading_tab')
document.querySelector('[data-part="indicator-panel"]').getBoundingClientRect()
document.querySelectorAll('[data-part="indicator-pillar-label"]')
```

### 3.3 the cause

Each mini-panel table holds three timeframe rows. Qt fixes the table to its
header plus two rows and turns both scrollbars off, so a third row is cut off.

`src/gui/indicator_panel.py` — the Qt height

```python
            table.setFixedHeight(
                table.horizontalHeader().sizeHint().height() + 28 * 2 + 4
            )
```

The surface publishes the two numbers that height is built from, and
`MiniTable` read neither, so each React table stood two rows taller than the Qt
one and the panel ran 70 pixels past its slot.

```python
            "slack_rows": TABLE_SLACK_ROWS,
            "slack_px": TABLE_SLACK_PX,
```

### 3.4 the correction

The body takes the height those two numbers give it and cuts off over it. A
body that carries a height is a block, so the head and each row are laid out as
their own fixed table, which is what keeps one column width across both.

```javascript
    var bodyStyle = {
      display: BLOCK,
      maxHeight: length(slackHeight(table)),
      overflow: HIDDEN
    };
```

### 3.5 the rerun

```
pillar          top 267.2, height 256, floor 523.2
pillar labels   523.2 to 545.2
bar areas       row A top 267.2, row B top 453.2, both 70 px
rules end at    1185.9, where the Net column starts
body cells      60, all three rows still held
```

Both tables now show their header and two rows, and both builds cut the 1d row
off the bottom. Every base label is in the picture.

---

## 4 — The two pictures

The Qt tab was built at 1386 by 708, the size the shell gives the React tab, so
the two panels get the same room. Every item below was read off both drawn
screens.

| item | Qt | React |
| --- | --- | --- |
| 1 `BB` column | NEUTRAL, 0.000, 2.00 px | the same, 2.00 px |
| 2 `VTX` column | BEARISH, 0.328, 22.96 px | the same, 22.69 px |
| 3 `MACD` column | BEARISH, 0.150, 10.50 px | the same, 10.38 px |
| 4 `SRsi` column | BEARISH, 0.200, 14.00 px | the same, 13.84 px |
| 5 `Ichi` column | BEARISH, 0.210, 14.70 px | the same, 14.53 px |
| 6 `Vol` column | NEUTRAL, 0.000, 2.00 px | the same, 2.00 px |
| 7 `Sling` column | NEUTRAL, 0.000, 2.00 px | the same, 2.00 px |
| 8 `ADX` column | BEARISH, 0.267, 18.69 px | the same, 18.48 px |
| 9 `STrd` column | BULLISH, 0.261, 18.27 px | the same, 18.05 px |
| 10 `ZSc` column | NEUTRAL, 0.000, 2.00 px | the same, 2.00 px |
| 11 `KER` column | NEUTRAL, 0.000, 2.00 px | the same, 2.00 px |
| 12 `RSI` column | NEUTRAL, 0.000, 2.00 px | the same, 2.00 px |
| 13 bar bases and labels | 12 labels under a 70 px plot, all drawn | the same 12, same order, all drawn |
| 14 `Net` pillar | BEARISH, column 8 of 10 | the same |
| 15 `Comp` pillar | NEUTRAL, column 9 of 10 | the same |
| 16 `Conf` pillar | BEARISH, column 10 of 10 | the same |
| 17 pillar bases and labels | one label each, in a 22 px strip under the floor | the same |
| 18 ceiling alignment | pillar top 171, row-A plot ceiling 171 | 267.2 and 267.2 |
| 19 no line crossing the three | rules end at 437, the Net column starts at 437 | 1185.9 and 1185.9 |
| 20 timeframe rows shown | header and two rows, the 1d row cut off | the same |
| 21 Activity Log rows | 8 rows, in arrival order | the same 8, same order |
| 22 Activity Log text | 8 messages with an `HH:MM:SS` stamp | the same 8 |
| 23 Activity Log colours | 8 colours by kind, trades at 14 px bold | the same 8 |

The bar heights differ by 0.12 to 0.27 px because the React plot puts its
1-pixel baseline inside the 70-pixel area and Qt paints its baseline on the
floor. Both fill `confidence` of the plot: 22.69 divided by 0.328 is 69.2 and
22.96 divided by 0.328 is 70.0.

The dotted increments and the baseline run over the timeframe column and the
six indicator columns and stop there, in both. Qt ends them at `right_edge`,
the x of the Net column; React draws them on the seven cells of each bar row
and on none of the three collated columns.

The Activity Log rows, read off both:

```
line                       colour            size  weight
Bot btc_core started       rgb(0,255,204)    12    normal
SCRUM PLACED               rgb(255,170,0)    14    bold
SCRUM FILLED               rgb(0,255,136)    14    bold
WIRE FLOW                  rgb(255,102,221)  12    bold
WIRE STACK                 rgb(255,204,68)   12    bold
Coinbase rate limit        rgb(255,170,0)    12    normal
Reconciliation refused     rgb(255,51,102)   12    normal
FOLD SENT                  rgb(0,255,204)    14    bold
```

No item on that list matched because both sides were empty. Every bar carries a
direction, seven of twelve carry a confidence above zero, all three pillars
carry a direction, and the log carries eight real rows.

Rows 852 and 917 read `yes` under Registers in Electron.

---

## 5 — One line drawn in one picture and not the other

The panel's locks line, `No active timeframe locks`, is in the Qt picture and
below the bottom of the React panel by 2 pixels. It is reached by scrolling the
panel, which the Qt one does not need.

The Live tab's own splitter is what differs, not the voting panel. Qt gives the
top section 472 pixels of the 708 the tab has; the React tab gives it 411. The
panel's shortest possible height is 415, because each bar graph carries a
100-pixel minimum in both builds.

```
                Qt      React
top section     472     411
panel content   444     415
locks line      inside  2 px below
```

Changing the split is a change to `trading_tab.js`, which draws neither of the
two widgets this unit registers, so it is recorded here and not changed.
