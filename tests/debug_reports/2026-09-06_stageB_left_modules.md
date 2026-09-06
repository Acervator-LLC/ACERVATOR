# Stage B — the three left modules

Stage B of issue #407. The Market Inspector carries three modules down its left
side, above the row that holds Refresh: ATA-SPM, Opposing Trades and
Multi-Exchange Arbitrage. Each is built here as a screen region. No ATA-SPM
phase is built; its phases, its Ready to Send bucket and its Settings page are
later stages.

Renders:

```
docs/audits/2026-09-06_units/stageB_left_modules_qt.png
docs/audits/2026-09-06_units/stageB_left_modules_react.png
docs/audits/2026-09-06_units/stageB_left_modules_electron.png
```

## Edits

`src/gui/main_tabs/market_inspector_surface.py` — the three regions, without
Qt. `left_module_rows` answers a key, a title and a status line for each, in
screen order. `ata_spm_text`, `opposing_trades_text` and `arbitrage_text` build
one line each. `MarketInspectorScreenModel` gains `set_ata_run_source`,
`ata_run`, `connectors_now` and `left_modules`; `ata_run` and `connectors_now`
answer `None` when no source is wired and a dict when one answers, so a source
that is missing never reads the same as a source that found nothing. That is
the rule unit 24 used for the two proposal states. Three layout values are
published, each measured off the running Qt widget: `MODULE_FRAME_PX`,
`MODULE_MARGINS_PX` and `MODULE_TITLE_PADDING_PX`.

`src/gui/market_inspector.py` — the Qt side of the same three regions.
`_build_ui` builds one `QGroupBox` per module above the filter row, each
holding one status label. `_render_left_modules` writes the three lines from
the state the tab can read, and runs from `_build_ui`, `set_exchange_source`,
`_start_fetch` and `_render_signals`. `set_ata_run_source` takes the phase
source. `_ata_run` and `_connectors_now` answer `None` on a missing or refusing
source.

`src/gui/react_market_inspector_tab.py` — `build_model` carries
`_ata_run_source` onto the screen model, and `_render_left_modules` pushes the
payload instead of writing labels.

`src/gui/web/market_inspector.js` — `ModuleGroup` draws one region and
`moduleGroups` draws the three at the top of `LeftPane`. `checkModules` refuses
a module entry that is not a key, a title and a line, or one whose key is not
the key the surface published at that place. `moduleOrder` reports the keys the
page drew.

`src/gui/web/market_inspector.css` — colour only. The module group takes the
theme's border colour and the module title takes the accent colour, which is
what the Qt group box and its title already carry.

`docs/manual/08-tabs.md` — the Market Inspector page gains the three modules,
what each reads and what each says while it is waiting. No sentence was deleted
or reworded.

## Errors detected

### 1 My own instrument built the tab with no theme

The first Qt run built `MarketInspectorTab` with no style sheet applied. The
splitter then reported a 5 px drag handle where the shipped theme gives 7:

```
qt handle 5 sizes [698, 697]
```

Unit 24 measured 7 and the surface publishes 7, so every Qt number in that run
was a fact about my setup rather than about the product. `main.py` applies
`ThemeManager().apply_theme("cyberpunk_dark", app)` before any tab is built.
Applying the same theme in the driver moved the reading to `handle 7 sizes
[697, 696]`, which is unit 24's measurement. Every number below is from a
themed run.

### 2 The React module group drew 19 px shorter than the Qt group

Read off the Qt widgets and off the page's own elements, tab sized 1400 by 860:

```
Qt     module 1 box [6, 6, 685, 75]    status line inside it [10, 50, 665, 15]
React  module 1 box [6, 6, 685.29, 55.8]  status line inside it [12.6, 27.8, 660.09, 15.4]
```

`ModuleGroup` used `GROUP_MARGINS_PX`, 11 px on every side, and let its title
take a row of its own. The themed `QGroupBox` does neither. Read off the
running widget:

```
group box       [6, 6, 685, 75]
contentsRect    [1, 41, 683, 33]
layout margins  [9, 9, 9, 9]
```

The frame takes 1 px, the band the title is drawn in takes 41 px from the
widget edge, and the layout keeps 9 px inside that. The theme puts the title in
the group's own margin, so it takes no row at all:

```
QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left;
                   padding: 4px 12px; }
```

Corrected by publishing `MODULE_MARGINS_PX` as `[9, 49, 9, 9]` and
`MODULE_TITLE_PADDING_PX` as `[12, 4, 12, 4]`, both measured above, and drawing
the title out of the flow at the group's own edge.

### 3 The default fieldset border is 1.6 px where the Qt frame is 1 px

After the correction above the React group drew 78.6 px against Qt's 75, and
every inset was 1.6 px deeper than the published margin. The computed style
says why:

```
borderTopWidth 1.6px   borderStyle groove   paddingTop 50px   boxSizing border-box
devicePixelRatio 1.25
```

The group carried no border rule of its own, so it kept the browser's default
`2px groove`, which computes to 1.6 CSS px at this pixel ratio. The Qt group
frame is 1 px, which is what `contentsRect` starting at x 1 reports. Corrected
by publishing `MODULE_FRAME_PX` as 1 and setting the border width and style
from it, which also reaches the Electron shell, where no style sheet for this
panel is loaded.

### 4 The React module title drew in the page's text colour

`market_inspector.css` colours `group-legend` and `card-legend` with the accent
colour. The new `module-legend` matched no rule, so the three titles drew white
against the themed Qt titles in teal. Corrected by naming the new part in the
same rule.

### The debugger, and what it printed

Both variants build clean under the strictest interpreter mode:

```
PYTHONWARNINGS=error python -X dev -X faulthandler ...
=== ACERVATOR_VARIANT=qt ===
variant qt class MarketInspectorTab
modules ['ata_spm', 'opposing_trades', 'arbitrage']
module box heights [75, 75, 75]
EXIT=0
=== ACERVATOR_VARIANT=react ===
variant react class MarketInspectorReactTab
modules ['ata_spm', 'opposing_trades', 'arbitrage']
module box heights [75, 75, 75]
EXIT=0
```

Under `debugpy`, asking the bridge for the screen the shell draws:

```
COMMAND: python -m debugpy --listen 5678 -m src.core.desktop_bridge
STDERR:
0.01s - Debugger warning: It seems that frozen modules are being used, which may
0.00s - make the debugger miss breakpoints. Please pass -Xfrozen_modules=off
0.00s - to python to disable frozen modules.
0.00s - Note: Debugging will proceed. Set PYDEVD_DISABLE_FILE_VALIDATION=1 to disable this validation.
EXIT: 0
ok=True
left_modules=[["ata_spm", "ATA-SPM", "Phase source not wired."], ["opposing_trades", "Opposing Trades", "No scan yet. Press Refresh to look for opposing trades."], ["arbitrage", "Multi-Exchange Arbitrage", "Exchange source not wired."]]
module_frame_px=1
module_margins_px=[9, 49, 9, 9]
module_title_padding_px=[12, 4, 12, 4]
```

The Electron shell refused to start until one environment value was removed.
The shell exited at once with this, and no window:

```
TypeError: Cannot read properties of undefined (reading 'whenReady')
    at Object.<anonymous> (desktop\main.js:182:5)
```

`ELECTRON_RUN_AS_NODE` is set to 1 in this shell, which makes
`require("electron")` answer a path rather than the module, so `app` is
undefined. Removing it from the child's environment starts the shell. Unit 25
recorded the neighbouring case, where `USERPROFILE` alone kills the shell and
`--user-data-dir` revives it; both overrides are in place here.

## Resolution

### Dimensions, after the corrections

Read off the Qt widgets and off the page's own elements, both sized 1400 by
860. A row matches when every number in it is within 1.5 px.

```
MATCH   tab size                          qt=[1400, 860]  react=[1400, 860]
MATCH   split size                        qt=[1400, 860]  react=[1400, 860]
MATCH   left pane box                     qt=[0, 0, 697, 860]  react=[0, 0, 697.29, 860]
MATCH   right pane box                    qt=[704, 0, 696, 860]  react=[704.29, 0, 695.71, 860]
MATCH   module 1 box (ata_spm)            qt=[6, 6, 685, 75]  react=[6, 6, 685.29, 75]
MATCH   module 1 status inside its group  qt=[10, 50, 665, 15]  react=[9.8, 49.8, 665.69, 15.4]
MATCH   module 2 box (opposing_trades)    qt=[6, 87, 685, 75]  react=[6, 87, 685.29, 75]
MATCH   module 2 status inside its group  qt=[10, 50, 665, 15]  react=[9.8, 49.8, 665.69, 15.4]
MATCH   module 3 box (arbitrage)          qt=[6, 168, 685, 75]  react=[6, 168, 685.29, 75]
MATCH   module 3 status inside its group  qt=[10, 50, 665, 15]  react=[9.8, 49.8, 665.69, 15.4]
MATCH   gap module 1 to 2                 qt=[6]  react=[6]
MATCH   gap module 2 to 3                 qt=[6]  react=[6]
MATCH   gap module 3 to Refresh           qt=[6]  react=[6]
MATCH   Refresh button x, y               qt=[6, 249]  react=[6, 249]
MATCH   HTF group x, width                qt=[6, 685]  react=[6, 685.29]
MATCH   Pairs group x, width              qt=[6, 685]  react=[6, 685.29]

rows 16 rows matched 16
numbers 45 numbers matched 45
```

The largest remaining gap is 0.69 px, on the status line's width, and 0.4 px on
its height. The 0.2 px on the line's own corner is the browser holding a 1 px
border to the device grid at a pixel ratio of 1.25. The 0.4 px of height is the
line box the same 11 px text sits in on each side.

### The split is unchanged

Units 24 and 25 measured the split at 697 and 696 either side of a 7 px handle.
The three regions did not move it:

```
left pane   qt [0, 0, 697, 860]     react [0, 0, 697.29, 860]
right pane  qt [704, 0, 696, 860]   react [704.29, 0, 695.71, 860]
```

The left column below the regions is intact. The Qt left pane holds 837 px of
content inside 860, so 23 px of the stretch it carried before is left over and
nothing is squeezed. The two tables keep the widths unit 24 gave them, 685 on
both sides.

### Values, driven and read back

Each module's source was wired in turn on the real tab, and the three lines
read back off the real Qt labels and off the page's own elements. Nine states,
twenty-seven lines, every one identical on both sides.

```
nothing wired
   ata_spm          Phase source not wired.
   opposing_trades  No scan yet. Press Refresh to look for opposing trades.
   arbitrage        Exchange source not wired.
exchange wired, no venue
   arbitrage        No exchange connected.
one venue
   arbitrage        1 venue connected: coinbase. A second venue is needed to compare.
two venues
   arbitrage        2 venues connected: coinbase, kraken.
ata wired, no run
   ata_spm          No run yet. Ready to Send holds 0.
ata run
   ata_spm          2 Identify. Ready to Send holds 3.
scan running
   opposing_trades  Scanning for opposing trades…
scan finished, no pair
   opposing_trades  Scan finished. No opposing trades found.
scan finished, two pairs
   opposing_trades  2 opposing trades. 50% of profit goes to the opposite side.

lines 27 identical 27
```

An ATA-SPM source that raises answers as no source, so the region says it is
unwired rather than showing a run nobody can read back.

```
surface, ata source refuses -> Phase source not wired.
```

No region draws a fixed caption. Every line above came from a value the tab
read: the scan state, the pair count, the exchange connectors, or the phase
report.

### The Electron shell

Reached by clicking the Market Inspector tab in the running shell, with the
backend redirected to `python -m src.core.desktop_bridge` under a throwaway
home:

```
module boxes [[6, 122.4, 670.99, 75], [6, 203.4, 670.99, 75], [6, 284.4, 670.99, 75]]
keys   ['ata_spm', 'opposing_trades', 'arbitrage']
titles ['ATA-SPM', 'Opposing Trades', 'Multi-Exchange Arbitrage']
texts  ['Phase source not wired.',
        'No scan yet. Press Refresh to look for opposing trades.',
        'Exchange source not wired.']
```

The panel starts 116.4 px down the window, so the three regions sit at 6, 87
and 168 inside it, which is where the Qt and the React regions sit. Each is
75 px tall, the Qt height. The panel is narrower than the tab, so the regions
are 670.99 wide rather than 685.

The shell loads no style sheet for this panel, which unit 24 recorded, so the
title colour does not reach it. The frame width and every inset do, because
they are written on the element itself.

### The conversion table

No row changes. The three regions add no module file, no bridge method and no
manifest entry: they are drawn by `market_inspector.js`, which row 24 already
names, through `market_inspector.state`, which row 24 already names. The totals
block is untouched. The proof that no manual sentence was touched:

```
git diff purge-non-canon-tests -- docs/ | grep "^-" | grep -v "^---" | grep -v "^-|"
REMOVED-LINE-COUNT=0
```

### Gate

```
coding_archetype  src/gui/market_inspector.py                    exit=0 passed=True
coding_archetype  src/gui/main_tabs/market_inspector_surface.py  exit=0 passed=True
coding_archetype  src/gui/react_market_inspector_tab.py          exit=0 passed=True
gui_archetype     src/gui/market_inspector.py                    exit=0 passed=True
gui_archetype     src/gui/react_market_inspector_tab.py          exit=0 passed=True
gui_archetype     src/gui/web/market_inspector.js                exit=0 passed=True
ta_archetype      src/gui/market_inspector.py                    exit=0 passed=True
ta_archetype      src/gui/main_tabs/market_inspector_surface.py  exit=0 passed=True
docs_archetype    docs/manual/08-tabs.md                         exit=0 passed=True
```

Every tool reported `ok`. Each exit code was read from the run itself, never
through a pipe. The fixture controls ran first:

```
coding_archetype known_good exit=0    known_bad exit=1
gui_archetype    known_good_widget.py exit=0   known_bad_widget.py exit=1
gui_archetype    known_good_screen.js exit=0   known_bad_screen.js exit=1
docs_archetype   known_good.md exit=0          known_bad.md exit=1
ta_archetype     known_good_ta001.py exit=0    known_bad_ta001.py exit=1
```

`black --check` and `flake8` both exit 0 on the three Python files.

One file this unit touched has no archetype that reads it:

```
gui_archetype src/gui/web/market_inspector.css exit=1
  "passed": false, "scanned": false
  no analyzer for css - this file type was NOT examined
```

The change to that file is two colour rules. No archetype owns a style sheet,
so this is a missing rule rather than a finding, and it is for the operator to
decide who should own it.

### Safety

Every run used a throwaway home. `~/.acervator/settings.json` is unchanged, and
its last write predates this unit by sixteen hours:

```
before   f366f42f0e49b4b3468f301b4f2f701669cc13005cfe1ebac7a56988ec376423
after    f366f42f0e49b4b3468f301b4f2f701669cc13005cfe1ebac7a56988ec376423
modified 2026-09-06T07:33:11Z
```

No network call, no credential, no test run, and no exchange order. The running
platform was never started, stopped or queried.

### Size against time

```
source lines produced   452
wall clock              2540 s
seconds per source line 5.62
```

### What the operator sees differently

The Market Inspector's left side now carries ATA-SPM, Opposing Trades and
Multi-Exchange Arbitrage above the Refresh row, in the Qt build, the React
build and the Electron shell. Each names what it can read: how many venues are
connected, how many opposing trades the last scan found and the share the
bullish side feeds across. Where a module has no source, it names the source it
is waiting for instead of showing nothing.
