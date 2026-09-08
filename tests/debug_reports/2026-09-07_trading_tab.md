# Trading tab, with the Indicator Voting Panel restyle folded in

The screens:

```
docs/audits/2026-09-07_units/trading_tab_qt.png
docs/audits/2026-09-07_units/trading_tab_react.png
docs/audits/2026-09-07_units/trading_tab_electron.png
docs/audits/2026-09-07_units/indicator_panel_restyled_react.png
```

Every run used a throwaway home. `~/.acervator/settings.json` hashed the same
before and after:

```
before  f366f42f0e49b4b3468f301b4f2f701669cc13005cfe1ebac7a56988ec376423
after   f366f42f0e49b4b3468f301b4f2f701669cc13005cfe1ebac7a56988ec376423
```

## The nine rows

Each row was read off the running page: the box the element drew into, and the
text it drew. A widget a parent panel draws needs no shell panel of its own, so
the second column names how its content reaches the shell.

| Unit | Reaches the shell | What it drew, quoted from the page |
| --- | --- | --- |
| 8 `indicator_panel.py` | through `trading_tab.js` | 758,132 626x411 — `Indicator Voting PanelBot:(select a bot)BTC — ETH — (currency rates pending)TFBBVTXMACDSRsiIchiVolNetCompConf1h▲ 72%▼ 41%▲ 55%─ 12%▲ 66%▼ 33%` |
| 26 `native_chart.py` | through `trade_charts_tab.js` | 12,164 1362x265 — `BTC/USD1hWaiting for data...` |
| 33 `widgets/bot_status_table.py` | through `exchange_tab.js` | 2,222 751x44 — `● Bot ID● Symbol● Mode● Trades● Target● Target BTC● Target ETH● Ammo● FireBOT-SCRUM-1BTC/USDscrumming7$250.0000pendingpending…FireDetail` |
| 34 `widgets/dashboard_stat_card.py` | through `header_strip.js` | 611,4 142x87 — `Scrummed$0.00●` |
| 35 `widgets/exchange_tab.py` | through `trading_tab.js` | 2,154 751x197 — `Privacy Mode: OFFFetching crypto news…+ New BotNext data pull: — Scrumming Bots` |
| 36 `widgets/extractor_bot_table.py` | through `exchange_tab.js` | 2,293 751x39 — `Bot IDSymbolModeTradesPoolLiquidFireBOT-EXTRACT-1ETH/USDextractor3------FireDetail` |
| 37 `widgets/privacy_dot.py` | through `spendable_profits.js` and `dashboard_stat_card.js` | 654,64 55x20 — `●` |
| 38 `widgets/spendable_profits.py` | through `header_strip.js` | 6,4 601x87 — `SPENDABLE—●|REALISED—●|LOCKED—●|MATURE—●|EXCH—●` |
| 39 `widgets/status_log.py` | through `trading_tab.js` | 4,574 685x260 — `Activity log...` |

Six of the nine already had a path: `trading_tab.js`, `exchange_tab.js` and
`trade_charts_tab.js` each mount their children into a named slot. Three did
not. `header_strip.js` drew its own spendable strip, its own five stat cards
and its own dot glyphs, so `spendable_profits.js`, `dashboard_stat_card.js` and
`privacy_dot.js` were loaded, registered nowhere and drew nothing.

Controls driven and read back off the real object:

```
mode button        Crypto Mode -> Stock Mode, data-mode crypto -> stock,
                   data-window-title CRYPTO WING -> STOCK WING
bot statuses       one scrumming and one extractor bot routed into the two
                   tables, each drawing its own row
exchange selection  coinbase named as the layer's current exchange, the
                   exchange pane drawn under its tab button
```

## Edits

`src/gui/web/header_strip.js` — `SpendablePanel` and `CounterCard` keep the box
Qt gives the child widget and draw nothing inside it. `mountSpendable` asks
`acervatorLoadProfits` and hands the space to `acervatorProfits.renderStrip`.
`mountCounters` asks `dashboard_stat_card.state` once per counter, with that
counter's label, value, field id and clickable flag, and hands each answer to
`acervatorStatCard.renderCard`. `mountChildren` runs both, and `renderStrip`
calls it. `modePressed` asks `header.strip` for the wing `next_mode` names and
`redraw` draws every host again.

`src/gui/main_tabs/header_strip_surface.py` — `next_mode` answers the wing the
button moves to and `mode_card` publishes it with `MODE_PARAM`, so a frontend
spells no mode name of its own.

`src/gui/web/dashboard_stat_card.js` — `dotSpan` draws the dot through
`acervatorDot.Dot` when `privacy_dot.js` is loaded, which is what
`attach_privacy_dot` builds in Qt.

`src/gui/indicator_panel.py` — the header puts the bot selector and its privacy
dot in the right corner and builds no `_symbol_label` or `_summary_label`. The
timeframe lock row, `_tf_lock_combo`, `lock_timeframe` and
`_on_tf_lock_changed` are gone. `_make_indicator_row` pads every table to
`_PANEL_COLUMN_COUNT`, so both rows share one grid. `CollatedPillarsWidget`
hosts the two mini-panels and paints one pillar per collated column behind
them; `_pillar_span` gives it the row-A plot ceiling and the row-B plot floor,
and `_sync_pillars` gives it the column each pillar stands in.
`RuledCellDelegate` draws the row partition for `_RULED_COLUMNS` only.
`PANEL_GROUND_RGB`, `BARS_MARGIN_TOP_PX`, `BARS_MARGIN_BOTTOM_PX` and the
baseline colour are read from `indicator_panel_surface`.

`src/gui/main_tabs/indicator_panel_surface.py` — `PANEL_COLUMN_COUNT`,
`RULED_COLUMNS`, `PANEL_GROUND_RGB`, `PILLAR_PAD_FRACTION` and
`PILLAR_GLOW_ALPHA` are the constants both hosts read. `column_titles` pads to
the shared grid and names no aggregate, so `AGGREGATE_TITLES` reads once, at a
pillar's base. `collated_pillars` answers one pillar per aggregate with its own
sign. Every `TF_LOCK` constant, `tf_lock_options`, `tf_lock_status`,
`set_lock`, `lock_timeframe`, `summary_text` and `symbol_payload` are gone,
along with the `tf_lock`, `symbol_text` and `summary_text` payload fields.

`src/gui/web/indicator_panel.js` — `HeaderRow` closes on the selector and draws
no symbol or summary span; `LockRow` is gone. `MiniTable` lays its columns
fixed, as Qt stretches its sections. `BarsPane` divides its row into one cell
per column so a bar lands under the head cell that names it, and each cell
carries a bar area and a label strip the size of the graph's own margins.
`PanelBody` is a grid of nine rows and `PANEL_COLUMN_COUNT` columns: the two
tables and the two graphs take their rows, a pillar spans the row-A plot row to
the row-B plot row, and its label sits in the strip under that floor.
`ruleStyle` puts the row partition on the ruled columns only, and `barArea`
carries the plot baseline and the dotted increments for those columns.

## Errors detected

Every run was `python -X dev -X faulthandler` with `PYTHONWARNINGS=error`, and
the Electron shell ran the repository's own `desktop/main.js` with the backend
pointed at `-m src.core.desktop_bridge`.

### 1 Electron would not start

```
exit=-2147483645
```

Repeated with a window that loads nothing but a data URL, so the shell's own
code was not involved. `--version` answered `v44.2.0` and exited 0.

### 2 The backend could not be reached as a value

```
[page] Uncaught (in promise) Error: An object could not be cloned.
```

### 3 The shell drew no card

`mountCounters` drew nothing and `[data-child-module="dashboard_stat_card"]`
matched no element.

### 4 The React panel overflowed its own width

The bar cells measured 166 to 186 px each inside a 626 px graph, so the row ran
to 2150 px and the panel grew a horizontal scrollbar the Qt panel does not
have.

### 5 The GUI archetype refused an inert control and an absolute placement

```
gui-js:GUIJS002 <button> carries none of ['onClick', 'onKeyDown',
'onMouseDown', 'onPointerDown']; the control draws and answers no
interaction, so it is inert.

gui-js:GUIJS004 position: absolute takes the element out of flow, so the
screen does not follow a resize or a text-scaling setting.
```

### 6 Qt reported a missing font face on every run

```
qt.qpa.fonts: DirectWrite: CreateFontFaceFromHDC() failed (Indicates an error
in an input file such as a font file.) for QFontDef(Family="MS Sans Serif",
pointsize=8, pixelsize=13, styleHint=5, weight=700, stretch=100,
hintingPreference=0) LOGFONT("MS Sans Serif", lfWidth=0, lfHeight=-13) dpi=96
```

### 7 The backend read no state, twice per run

```
bot_state loader: file not found at <throwaway home>\.acervator\bot_state.json
```

## Resolution

### 1 Chromium had no profile directory it could resolve

The throwaway home broke Chromium's own profile path. `--user-data-dir` under
the scratch directory fixed it: the shell then started, loaded all its modules
and drew, and the Python child still saw the throwaway home. The environment
also carried `ELECTRON_RUN_AS_NODE=1`, which makes `electron.exe` behave as
`node` and refuses `require("electron")`; the run clears it.

### 2 A function was sent where a method name belonged

`acervatorStatCard.methodName` is the accessor, not the string.
`acervatorStatCard.method` carries `dashboard_stat_card.state`, which is what
`trade_charts_tab.js` already passes for `native_chart.js`. With the string,
the five cards answer and draw.

### 3 Fixed by 2

Five cards, one spendable strip and five dots now draw, each named by its
`data-child-module`.

### 4 A flex item will not shrink below its content

`minWidth: 0` on every bar cell lets it take its share of the row. The bar body
then took `column_body_fraction`, which the surface publishes as
`1 - 2 * BARS_COLUMN_PAD_FRACTION`, rather than a percentage padding, because a
percentage padding resolves against the row's width and not the cell's.

### 5 The mode button now answers, and the pillars sit on a grid

`ModeButton` carries an `onClick` that asks the surface for the wing
`next_mode` names, sets the answer and redraws. The pillars are grid items
placed by `gridColumn` and `gridRow`, so nothing leaves the flow and the panel
still follows a resize.

### 6 and 7 Left as they are

Both are true statements about the run, not defects in it. The font face is a
fact about this machine's `MS Sans Serif`, and the absent `bot_state.json` is
the throwaway home doing its job.

## The three hosts

The Qt widget reports its own geometry and the page reports each element's box.
Both variants of the Qt build were measured against the same page reading.

```
ACERVATOR_VARIANT=qt     vs the Electron page   162 of 162 dimensions matched
ACERVATOR_VARIANT=react  vs the Electron page   162 of 162 dimensions matched
```

The set covers, per mini-panel: the column count, every column's title, every
column's x and width as a share of the table, every bar's name, every bar's
fill against its own plot area, and every bar sitting on that plot floor. Per
pillar: its name, its direction, its x and width as a share of the body, its
ceiling one graph margin below the row-A graph edge and its floor one graph
margin above the row-B graph edge. Plus the panel carrying no timeframe lock,
no symbol label and no summary label on either side.

## What #414 changes about the readings above

The panel draws what the voting engine hands it. Eight indicator
implementations depart from their published formulae, and four of the twelve
columns above show a reading from one of them: `ZSc` from `zscore`, `KER` from
`kaufman_er`, `ADX` from `adx` and `RSI` from `rsi`. `MACD`, `Vol`, `Ichi`,
`STrd` and `VTX` carry the other four. Net, Comp and Conf are sums over all
twelve, so every one of them is downstream of the eight.

This unit repaired none of them. The restyle changes where a value is drawn and
never what it reads, so no indicator file was touched and none had to be. The
eight stay on #414, in the repair order that issue sets.

## Size against time

```
source lines produced   847 in src/
wall clock              6091 s
seconds per source line 7.19
```

## What the operator sees differently

The Trading tab draws in the Electron shell with its exchange pane, its two bot
tables, its activity log and the restyled Indicator Voting Panel, and the
header strip above it draws its spendable strip and its five stat cards through
the modules that own them. The panel carries seven columns on each row, aligned
under each other, with Net, Comp and Conf standing as one pillar each behind
both rows and labelled once at the base. The timeframe lock, the pair symbol
and the vote tally are gone from it.
