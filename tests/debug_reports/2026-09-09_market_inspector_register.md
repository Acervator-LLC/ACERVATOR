# 2026-09-09 — Market Inspector: the shell draws the screen and its proposals pane

Issue #128, rows 878 and 879 of the conversion table in
[08-tabs.md](../../docs/manual/08-tabs.md). Files changed:
`src/gui/web/market_inspector.js`, `src/gui/web/market_inspector.css`,
`desktop/renderer/index.html`, `src/gui/design_system.py` and
`src/gui/main_tabs/design_system_surface.py`. No test file was written.

The Electron shell ran from `desktop/main.js` under the installed Electron
binary with a throwaway home, and the renderer was read over the Chrome
DevTools Protocol. The Qt tab was built offscreen under `PYTHONWARNINGS=error`
with `python -X dev -X faulthandler`.

The Market Inspector answers `ACERVATOR_VARIANT`. `variant_surface.py`
registers `MARKET_INSPECTOR` and `surface_class` returns `MarketInspectorTab`
under `qt` and `MarketInspectorReactTab` under `react`, so the Qt side was
reached by building the class that switch selects.

Pictures:

```
qt    <scratchpad>/u128/qt_market_inspector_128.png
react <scratchpad>/u128/react_market_inspector_128.png
```

Both sides ran on one payload: 54 Coinbase USD markets, 300 daily candles
each, one `MarketInspector.scan_universe` call, and the three proposals
`detect_all_topologies` ranked from that scan.

---

## 1 — The table says neither module registers, and both already did

### 1.1 the error

No traceback. The shell was read before any edit and named both panels:

```
registered = bot_live_settings, bot_swarm_tab, bot_visualizer, console_tab,
             header_strip, history_tab, market_inspector, market_inspector_tab,
             market_inspector_topologies, native_chart, paper_trader_tab,
             proof_of_accumulation_tab, simulator_tab, system_status_tab,
             trade_charts_tab, trading_tab
reasonFor('market_inspector')              null
reasonFor('market_inspector_topologies')   null
```

### 1.2 reproduction

```
electron.exe <tree>/desktop --user-data-dir=<scratchpad> --remote-debugging-port=9346
ACERVATOR_BRIDGE_ARGV="-m src.core.desktop_bridge"
window.acervatorPanelHost.registered()
```

### 1.3 the cause

`market_inspector.js` and `market_inspector_topologies.js` both call
`acervatorPanelHost.register` at load. The cells read `no` from a measurement
taken before those calls landed.

### 1.4 the correction

The cells now read `yes`. Nothing was added to either module to make them
register.

### 1.5 the rerun

The same list, after every change in this report, still names both panels and
`faults` stays empty.

---

## 2 — The proposals pane drew around the panel host

### 2.1 the error

`market_inspector_topologies` was registered and its registration drew nothing.
`fillSlot` called the module's own renderer, so removing the registration
changed no pixel.

```
renderScreen -> fillSlot -> acervatorTopologies.renderTab(slot, null)
```

### 2.2 reproduction

The shell mounted `market_inspector` on the shared payload and the slot was
read back.

```
document.querySelector('[data-slot="market-inspector-topologies"]').innerHTML.length
```

### 2.3 the cause

`src/gui/web/market_inspector.js` — the slot filler reached the module direct

```javascript
    pane.renderTab(slot, null);
```

A module that draws that way needs no registration, so the row could flip on a
draw the panel host never made.

### 2.4 the correction

The panel host draws the pane, under the name the module registered.

```javascript
    host.mount(TOPOLOGY_PANEL, slot, null);
    if (typeof global.acervatorLoadTopologies === FUNCTION_KIND) {
      global.acervatorLoadTopologies().then(function (model) {
        host.mount(TOPOLOGY_PANEL, slot, model);
      });
    }
```

### 2.5 the rerun

```
mount('market_inspector_topologies', slot, model)   true
slot markup   3512 characters
slot text     Refresh  Auto-refresh: every 10 min · Adopt: live (Bot Wizard
              handoff)  3 proposal(s); 0 dismissed  1 of 3
              Momentum funnel: PEPE -> SHIB, DOGE, XRP, ADA, GRT, LINK, ETC 81
```

The control run removes the registration and drives the same payload:

```
mount('market_inspector_topologies', slot, model)   false
slot markup   106 characters
slot text     Panel market_inspector_topologies did not draw:
              market_inspector_topologies.js registered no panel to draw
reasonFor     market_inspector_topologies.js registered no panel to draw
```

3512 characters against 106. The registered panel is the path that draws.

The same control on the screen itself removes `market_inspector` from the
register call:

```
tab count            9, and the application's Inspector tab is gone
select('market_inspector')   false
host element                 none, so the mount records "no host element"
reasonFor('market_inspector') market_inspector.js registered no panel to draw
```

---

## 3 — The shell never loaded the screen's own stylesheet

### 3.1 the error

Every button on the screen drew in the browser default.

```
[data-part="scan-now"] background   rgb(239, 239, 239)
```

### 3.2 reproduction

The Electron shell drew the tab and the computed background of the Scan Now
button was read.

### 3.3 the cause

`src/gui/web/market_inspector.css` carries the colour, border and type of every
`data-part` the two modules stamp, and `desktop/renderer/index.html` linked
`history_panel.css` and `tab_bar.css` and not this one. The file shipped and
nothing loaded it.

### 3.4 the correction

```html
    <link rel="stylesheet" href="../../src/gui/web/market_inspector.css" />
```

The button ground the stylesheet named resolved to `--btn-bg`, `#12121a`, where
the theme gives `QPushButton` `bg_tertiary`, `#1a1a28`. The rule now reads the
published token that carries that value.

```css
  background: var(--SURFACE_2, var(--btn-bg));
```

### 3.5 the rerun

```
[data-part="scan-now"] background   rgb(26, 26, 40)
theme QPushButton background-color  #1a1a28
```

`--btn-bg` in `src/gui/web/history_panel.css` is `#12121a`, which is the
theme's `bg_secondary` and not its button ground. Every panel reading that
variable draws a button one step darker than Qt. That file belongs to the
History row and was not changed here.

---

## 4 — The check boxes drew as the browser's own control

### 4.1 the error

```
[data-part="switch-box"] appearance=auto background=rgba(0, 0, 0, 0) size=13x13
```

Qt paints the same control from `QCheckBox::indicator`: an 18 pixel box, a two
pixel `border_primary` edge, a three pixel radius and a `bg_input` ground.

### 4.2 reproduction

The Electron shell drew the tab and the computed style of the Include active
markets box was read.

### 4.3 the cause

`market_inspector.css` set `accent-color` and nothing else, which colours a
checked native box and leaves the unchecked one white. The ground the indicator
needs, `#0e0e1a`, was in no design-system token: `SURFACE_0` is `#0a0a0f`,
`SURFACE_CONTROL` is `#1a1a2e` and `VIZ_INPUT_SURFACE` is `#142244`.

### 4.4 the correction

The token was added under the name of the role it fills, beside
`SURFACE_CONTROL` in the surfaces family, on both sides of the table.

```python
SURFACE_INPUT = "#0e0e1a"  # Check box, radio and text field ground
```

`design_system_surface.TOKEN_NAMES` now carries 196 names against 195, and the
stylesheet names the token rather than the value.

```css
  border: 2px solid var(--OUTLINE, var(--border));
  background: var(--SURFACE_INPUT, var(--bg));
```

### 4.5 the rerun

```
[data-part="switch-box"] appearance=none background=rgb(14, 14, 26)
                         border=rgb(122, 122, 156) size=18px x 18px
```

The picture agrees: the box measures `#0e0e1a` with a `#7a7a9c` edge in the Qt
PNG and `#0e0e19` with a `#7b7a99` edge in the React PNG, the one-step drift
every near-grey shows between the two capture paths.

---

## 5 — Three readings came from an Electron the run had already finished with

### 5.1 the error

The check box read `appearance=auto` on three consecutive runs after the
stylesheet already carried `appearance: none`, and two expressions added in the
same edit answered nothing at all.

```
switchStyle = "auto bg=rgba(0, 0, 0, 0)"
sheets      = null
switchRule  = null
```

### 5.2 reproduction

```
tasklist | grep electron   ->  4 processes, all naming this run's user-data-dir
```

### 5.3 the cause

`proc.terminate()` ends the process the run started and leaves the GPU,
network and renderer children alive. Those children keep the debugging port
open, so the next run attached to a page still holding the previous copy of
the stylesheet.

### 5.4 the correction

The run kills every `electron.exe` before it launches and again after it
finishes, and the profile directory is removed between runs.

### 5.5 the rerun

```
sheets      = history_panel.css, market_inspector.css, tab_bar.css, 13 inline
switchRule  = [data-part="switch-box"], [data-part="timeframe-box"] {
              appearance: none; ... }
switchStyle = part=switch-box appearance=none bg=rgb(14, 14, 26)
```

Every reading in this report that came from a stale page is replaced above. The
readings that discriminated — the register lists, the two control runs and the
three button grounds `#efefef`, `#12121a`, `#1a1a28` — each changed when the
code changed, so none of them came from a page that could not see the edit.

---

## The two pictures

Both were driven with the same scan and the same three proposals.

| # | item | Qt picture | React picture |
| --- | --- | --- | --- |
| 1 | zone count and titles | ATA-SPM, Opposing Trades, Multi-Exchange Arbitrage, ATA-SPM Ready to Send, Bot Swarm Topologies, Phantom Bot HTF Signals | the same six, same order |
| 2 | left and right halves | two columns, three zones each | two columns, three zones each |
| 3 | filter row | Sector box, `crypto`, 5m 1hr 1d 1wk, Scan Now, Settings | the same seven |
| 4 | Opposing Trades controls | Refresh, Include active markets | the same two |
| 5 | status line | `Snapshot 12s old  ·  54 markets` | the same |
| 6 | Opposing Trades note | `Scan finished. No opposing trades found.` | the same |
| 7 | Arbitrage note | `No exchange connected.` | the same |
| 8 | ATA-SPM note | `No sector added. Name one and press Scan Now.` | the same |
| 9 | Ready to Send note | `Phase source not wired. Nothing to approve.` | the same |
| 10 | Ready to Send buttons | Post Selected, Post All, Send Bucket Full Auto | the same three, one line each |
| 11 | Phantom Bot note | `Phantom Bot source not wired.` | the same |
| 12 | topologies status | `3 proposal(s); 0 dismissed` | the same |
| 13 | topologies footer | `Auto-refresh: every 10 min  ·  Adopt: live (Bot Wizard handoff)` | the same |
| 14 | steppers, left to right | 0 of 0, 0 of 0, 0 of 0, 0 of 0, 1 of 3, 0 of 0 | the same six |
| 15 | card title | `▸ Momentum funnel: PEPE → SHIB, DOGE, XRP, ADA, GRT, LINK, ETC` | the same |
| 16 | card badge | `81` on `#00cccc` | `81` on `rgb(0, 204, 204)` |
| 17 | card meta | `score 81  •  8 assets  •  7 wires  •  8 new bot(s)` | the same |
| 18 | card method line | `Correlation  •  300d  •  r=+0.806 over 28 pairs · p≤0.0000` | the same |
| 19 | card hint | `Click the entry for how and why it is here.` | the same |
| 20 | HTF Signals columns | Asset, Signal, Score, Daily, Weekly, Active | the same six |
| 21 | HTF Signals rows | 5 rows, ZEC ZK ZETA GRT IMX, cell for cell | the same 5 rows, cell for cell |
| 22 | Opposing Pairs columns | Long side, Short side, Method, Window, Statistic, Correlation, Score (Long+Short) | the same seven |
| 23 | Opposing Pairs rows | 0 | 0 |
| 24 | zone legend colour | `#00ffcc` | `rgb(0, 255, 204)` |
| 25 | button ground | `#1a1a28` | `rgb(26, 26, 40)` |
| 26 | page ground | `#0a0a0f` | `#0a0a0f` |
| 27 | Include active markets box | 18px box, `#7a7a9c` edge, `#0e0e1a` ground | 18px box, `#7b7a99` edge, `#0e0e19` ground |

Twenty-seven of twenty-seven match. Item 23 matches with nothing in it: this
market carried one short-side signal at or above the score floor and no long
side, so `_find_opposing_pairs` returned nothing and both tables are empty. It
proves the column set and not the rows.

## Two notes on the comparison itself

The screenshot the DevTools Protocol returns is colour managed, so a saturated
fill reads wide of its own value: the badge measures `#6cc9cb` in the PNG and
`rgb(0, 204, 204)` in the page, and the zone legend measures `#85fbcf` and
`rgb(0, 255, 204)`. Near-greys are unaffected — the page ground measures
`#0a0a0f` in both pictures.

The Qt tab holds a settings page behind its Settings button: seven venue
fields, Save credentials, and four numbered settings. Neither picture shows
it, and it is reached the same way on both sides.

## Where this page carries the dated block

The block belongs under `## Market Inspector Tab`. Placed there it fails
`docs_archetype`, because `tools/build_product_manual.backward_update_rows`
walks every dated heading on the page against one running maximum, and the
Market Inspector section sits above Asset Charts, whose blocks are stamped
earlier.

```
line 623: the update stamped 2026-09-08 23:40 follows the one stamped
          2026-09-09 23:05 at line 442. Updates under a tab run forward.
line 652: the update stamped 2026-09-09 01:20 follows the one at line 442.
line 695: the update stamped 2026-09-09 03:05 follows the one at line 442.
line 1517: the update stamped 2026-09-09 22:12 follows the one at line 442.
```

The block is at the page's end, where the check is green. Grouping the walk by
tab section would let it sit under the tab, and that is a change to what the
rule allows, not a hardening of it.
