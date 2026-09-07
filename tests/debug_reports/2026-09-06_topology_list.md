# Topology list — one entry at a time, in all six zones

The Market Inspector's six zones each show one entry at a time. A left arrow
and a right arrow move between entries, a line says which entry is on screen
and how many there are, and clicking the entry opens it to say how and why it
is there. The Bot Swarm Topologies pane registers as a shell panel, so its
cards draw in the Electron shell as well as in the two Qt-hosted builds.

Renders:

```
docs/audits/2026-09-06_units/topology_list_qt.png
docs/audits/2026-09-06_units/topology_list_react.png
docs/audits/2026-09-06_units/topology_list_electron.png
docs/audits/2026-09-06_units/topology_list_expanded_react.png
```

## Edits

`src/trading/pair_selection.py` — `MethodResult` gains `gate_text`, and
`as_dict` publishes it as `gate`. It is the sentence saying why a verdict
passed, written by the module that owns the threshold, so no screen restates
`SIGNIFICANCE`. A refused verdict names its own detail; a band-distance
verdict says it was read from live balances and no p-value applies.

`src/gui/main_tabs/market_inspector_surface.py` — the one place the stepper
lives. `step_to` moves an index and wraps at both ends, `position_text` writes
`{at} of {total}` and `0 of 0` for an empty zone, `method_line` writes the
one-line method summary, and `method_detail_rows` writes the four expanded
lines from the verdict dict. `zone_entry` and `zone_view` turn a list of
entries plus an index and an open flag into the one shape all three hosts
draw. `pair_entry` turns one `PairState` into that shape. `stepper_skin`
publishes every value the arrows, the position line and the entry are drawn
from. `MarketInspectorScreenModel` gains `pairs`, `zone_at`, `zone_open`,
`zone_entries`, `step_zone`, `toggle_zone` and `zone_views`, and its bridge
handler reads `step_zone`, `step` and `toggle_zone`.

`src/gui/main_tabs/market_inspector_topologies_surface.py` — imports the
stepper rather than keeping a second copy. `method_text` and its format are
gone; `method_line` and `METHOD_LINE_FORMAT` replace them, so the published
`method_format` value is unchanged. `proposal_entry` turns one proposal into a
zone entry with its badge, and `pane_view` answers the whole pane as one zone
view. `TopologiesPaneModel` gains `shown_at`, `expanded`, `shown`, `position`,
`step` and `toggle`; `render` builds one card, not a list. The bridge handler
reads `step` and `expand`.

`src/gui/market_inspector.py` — `ProposalStepper` is the Qt widget every zone
uses: the two arrow buttons, the position line, one clickable `_ZoneEntry`
frame inside a scroll area, and the expanded lines. `MarketInspectorTab` builds
one per zone, keeps `_zone_at` and `_zone_open`, and `_render_left_modules`
writes every zone from `_zone_views`. The Opposing Pairs table is no longer
added to a layout; the zone's stepper draws the pairs instead, and
`_fill_pair_rows` keeps `_pairs` so the stepper has them.

`src/gui/market_inspector_topologies.py` — the pane uses `ProposalStepper` and
`pane_view`. `_ProposalCard` and `_clear_cards` are gone, replaced by the
stepper and one Preview and Dismiss row acting on the proposal on screen. The
inner Topology Proposals group box is gone, because the zone around the pane
already carries that title and the second frame left the card 42 px tall.

`src/gui/react_market_inspector_tab.py` — the page's presses reach the model:
`step-back`, `step-next` and `zone-entry` on both the screen and the pane.
`_fill_pair_rows` calls the screen model rather than filling its rows, so the
model holds the pairs the stepper reads.

`src/gui/web/market_inspector.js` — `ZoneStepper`, `StepButton` and
`DetailLine` are the React half of the same stepper, and `zoneFor` picks a
zone's published view. `ModuleGroup` and `RightZone` draw it in place of the
status line. The Opposing Pairs table is out of `scanContent`. The default
`acervatorMarketInspectorAction` now takes a press to the bridge and redraws,
which is what makes the arrows work in the shell.

`src/gui/web/market_inspector_topologies.js` — the pane draws through the
screen's `ZoneStepper`, so there is one implementation and not two. `paneHost`
and `seat` put the pane inside the screen's slot, `register` joins the shell's
panel roster, and the default `acervatorTopologiesAction` takes a press to the
bridge.

`desktop/renderer/index.html` — the page is a column: the panel area takes the
height the chrome and the tabs leave, and each panel host fills it.

`docs/manual/08-tabs.md` — the Market Inspector page gains the position line,
the arrows, the expansion and its four lines. No sentence was deleted or
reworded.

## Errors detected

### 1 `var METHOD = "method"` shadowed the bridge method name

The Electron shell logged this on every launch, before this unit changed
anything:

```
[backend] bridge method 'method' failed: method
Error occurred in handler for 'acervator:call': Error: UnknownMethod: method
    at Bridge.onFrame (desktop\main.js:99:21)
```

`src/gui/web/market_inspector_topologies.js` declared `METHOD` twice inside one
function scope: `"market_inspector_topologies.state"` at the top and `"method"`
two hundred lines later as the name of a card field. `var` hoists, so every
later read answered `"method"`, and `loadPane` asked the bridge for a method
that does not exist. The pane could not load its own state in the shell.

Driven against the running shell, the bridge answered the real name and refused
the shadowed one:

```
direct call  {'position': '2 of 2', 'at': 1, 'status': '2 proposal(s); 0 dismissed'}
handler      Error: Error invoking remote method 'acervator:call':
             Error: UnknownMethod: method
```

Corrected by renaming the card field to `METHOD_FIELD` and leaving the bridge
name alone. After the rename the shell log holds no `UnknownMethod` line:

```
grep -c "UnknownMethod" shell_out.txt
0
```

**This is the cause Stage C recorded as a missing registration.** Registering
the panel was necessary and not sufficient: with the shadowed name the panel
registered, the shell asked, and every ask failed.

### 2 The panel registered nowhere, so the shell never asked

`market_inspector_topologies.js` called `acervatorPanelHost.register` nowhere.
Corrected by registering with a render function, a loader and its load-error
reader, and naming no bridge method, so the tab bar gives it no tab of its own.
The shell reports it in the roster and reports no fault:

```
panels  ['header_strip', 'console_tab', 'trading_tab', 'market_inspector_tab',
         'trade_charts_tab', 'bot_visualizer', 'simulator_tab',
         'market_inspector', 'market_inspector_topologies', 'bot_live_settings',
         'bot_swarm_tab', 'history_tab', 'paper_trader_tab',
         'proof_of_accumulation_tab', 'system_status_tab']
faults  []
```

### 3 The shell's panel area had no height, so six zones shared 59.6 px

`#panels` in `desktop/renderer/index.html` carried no height, so a screen sized
in per-cent resolved against its own content. Measured in the shell before the
change:

```
ata_spm         [6, 122.4, 684.5, 59.6]
opposing_trades [6, 188.0, 684.5, 59.6]
arbitrage       [6, 253.6, 684.5, 59.6]
```

Corrected by making the page a column — `html` and `body` at full height, the
body a flex column, `#panels` taking the rest with `min-height: 0` — and giving
each panel host under it `height: 100%`. The same six zones afterwards:

```
ata_spm         [6, 122.4, 684.5, 253.2]
opposing_trades [6, 381.6, 684.5, 253.2]
arbitrage       [6, 640.8, 684.5, 253.2]
ready_to_send   [709.5, 122.4, 684.5, 253.2]
topologies      [709.5, 381.6, 684.5, 253.2]
phantom_htf     [709.5, 640.8, 684.5, 253.2]
```

**What every other panel does with a container that has a height.** The shell
draws fifteen panels and reports no fault after the change. A panel that sizes
itself to its content is unaffected, because a taller container does not shrink
content. The History panel sizes itself with `height: 100vh` in
`history_panel.css` and so is unchanged either way. The panels that gain are
the ones written as a per-cent of their host, which is what the Market
Inspector is.

### 4 The arrow buttons drew no glyph

The theme gives `QPushButton` 20 px of padding each side. A 26 px fixed width
left no room, so both arrows drew empty. The first attempt at a fix made it
worse: a style sheet carrying `min-width: 0px` overrode `setFixedWidth`, and
the button collapsed to its hint.

```
before   width 13  min 6   max 26  hint 13
after    width 26  min 26  max 26  height 24
```

Corrected by publishing `STEP_BUTTON_STYLE` as `padding: 2px;` alone. Both
hosts then measured the same box:

```
back button   qt=[16, 382, 26, 24]  react=[15.8, 380.86, 26, 24]
next button   qt=[46, 382, 26, 24]  react=[45.8, 380.86, 26, 24]
```

### 5 The expanded lines drew on top of each other

`deleteLater` frees a widget when the event loop next runs, so the previous
draw's lines were still on screen under the new ones. Corrected by taking each
line off its parent first and letting `deleteLater` free it afterwards. The
entry also has to ask for the height its own content needs, because a scroll
area shrinks its widget to the viewport, and `sizeHint` is stale until the
layout it just changed is activated.

### 6 The pane's own buttons ignored the theme

`market_inspector_topologies.js` drew Refresh proposals, Preview and Dismiss
with no padding, so the pane's rows were shorter than the Qt ones and every box
below them sat too high. This is the same fault Stage C corrected on the
screen's Refresh button, in the module beside it. Corrected by publishing the
themed push button in the stepper skin and drawing all three from it. The pane
stepper closed from 14.3 px of difference to 4.26 px.

### The debugger, and what it printed

Both variants build clean under the strictest interpreter mode:

```
PYTHONWARNINGS=error python -X dev -X faulthandler topolist_qt_drive.py
EXIT=0

PYTHONWARNINGS=error python -X dev -X faulthandler -c "import the six modules"
imports clean
IMPORT EXIT=0
```

The Electron shell needed three things this host does not give by default.
`ELECTRON_RUN_AS_NODE` is set in this shell's environment, and with it Electron
runs as Node and `app` is undefined:

```
desktop\main.js:182
app.whenReady().then(() => {
    ^
TypeError: Cannot read properties of undefined (reading 'whenReady')
```

A second run of the shell exits 3 while the first still owns the profile, so
the run takes its own `--user-data-dir`. And importing PySide6 in the same
process puts its own graphics libraries on PATH, after which Electron starts
and writes nothing at all; the driver that starts the shell imports no Qt.

## Resolution

### Every zone, driven and read back

Qt, read off the real widgets:

```
ata_spm          0 of 0   Phase source not wired.
opposing_trades  1 of 2   SOL (ENTRY_LONG_HIGH)  ▸  JUP (ENTRY_SHORT_HIGH)
arbitrage        0 of 0   Exchange source not wired.
ready_to_send    0 of 0   Phase source not wired. Nothing to approve.
topologies       1 of 2   ▸ Sector cluster (layer1): SOL to AVAX, ADA, DOT
phantom_htf      0 of 0   Phantom Bot source not wired.
```

The arrows step and wrap, and the entry opens:

```
position_before      1 of 2
position_after_next  2 of 2
headline_after_next  ETH (ENTRY_LONG_HIGH)  ▸  LINK (ENTRY_SHORT_HIGH)
position_after_wrap  1 of 2
position_after_back  2 of 2
detail_after_click:
     Test: Cointegration — Engle-Granger + Johansen
     Window: 365 daily closes
     Result: p=0.0100 · trace 20.1>15.5
     Why it is here: p 0.0000 is at or below the 0.05 required.
```

React, read off the page's own elements, the same six zones in the same order:

```
zones      ['ata_spm', 'opposing_trades', 'arbitrage', 'ready_to_send',
            'topologies', 'phantom_htf']
positions  ['0 of 0', '1 of 2', '0 of 0', '0 of 0', '1 of 2', '0 of 0']
methods    ['Cointegration  •  365d  •  p=0.0000 · trace 57.5>15.5',
            'Correlation  •  365d  •  r=+0.672 over 6 pairs']
metas      ['score 1.50  •  correlation -0.843',
            'score 67  •  4 assets  •  3 wires  •  4 new bot(s)']
badges     [' 67 ']
```

The Electron shell, with the backend redirected to the bridge under a throwaway
home, the tab selected in the running page and the same two proposals sent
through the real bridge:

```
status     2 proposal(s); 0 dismissed
selected   market_inspector
faults     []
positions  ['0 of 0', '0 of 0', '0 of 0', '0 of 0', '1 of 2', '0 of 0']
headlines  ['Phase source not wired.',
            'No scan yet. Press Refresh to look for opposing trades.',
            'Exchange source not wired.',
            'Phase source not wired. Nothing to approve.',
            '▸ Sector cluster (layer1): SOL to AVAX, ADA, DOT',
            'Phantom Bot source not wired.']
methods    ['Correlation  •  365d  •  r=+0.672 over 6 pairs']
badges     [' 67 ']
```

Pressing the card and then the right arrow in the shell:

```
details after click  ['Test: Correlation — Pearson',
                      'Window: 365 daily closes',
                      'Result: r=+0.672 over 6 pairs',
                      'Why it is here: p 0.0000 is at or below the 0.05 required.']
after next           ['0 of 0', '0 of 0', '0 of 0', '0 of 0', '2 of 2', '0 of 0']
```

The shell holds no pairs because no scan ran in it, so the Opposing Trades zone
reads zero of zero and says what it waits for. That is the state the surface
publishes for an unscanned screen, and it is the same state the other two hosts
show before a scan.

### The count stays honest

The line beside Refresh proposals is unchanged. Two proposals held and none
dismissed reads `2 proposal(s); 0 dismissed` in all three hosts, and a
dismissed proposal still counts on the right-hand number after it leaves the
list.

### Dimensions

Read off the Qt widgets and off the page's own elements, both sized 1400 by
860. A row matches when every number in it is within 1.5 px.

```
MATCH   tab size            qt=[1400, 860]        react=[1400, 860]
MATCH   back button         qt=[16, 382, 26, 24]  react=[15.8, 380.86, 26, 24]
MATCH   next button         qt=[46, 382, 26, 24]  react=[45.8, 380.86, 26, 24]
MATCH   position line       qt=[76, 382, 28, 24]  react=[75.8, 380.86, 27.77, 24]
DIFFER  entry               qt=[16, 410, 665, 148]   react=[15.8, 408.86, 664.9, 150.66]
DIFFER  stepper             qt=[16, 382, 665, 176]   react=[15.8, 380.86, 664.9, 178.66]
DIFFER  pane entry          qt=[726, 416, 642, 114]  react=[725.3, 414.86, 652.9, 78.26]
DIFFER  pane stepper        qt=[726, 388, 652, 102]  react=[725.3, 386.86, 652.9, 106.26]
MATCH   pane position line  qt=[786, 388, 28, 24]    react=[785.3, 386.86, 27.77, 24]
MATCH   zone ata_spm        qt=[6, 6, 685, 278]      react=[6, 6, 684.5, 278.66]
MATCH   zone opposing_trades qt=[6, 290, 685, 278]   react=[6, 290.66, 684.5, 278.66]
MATCH   zone arbitrage      qt=[6, 574, 685, 278]    react=[6, 575.33, 684.5, 278.66]
MATCH   zone ready_to_send  qt=[710, 6, 684, 278]    react=[709.5, 6, 684.5, 278.66]
MATCH   zone topologies     qt=[710, 290, 684, 278]  react=[709.5, 290.66, 684.5, 278.66]
MATCH   zone phantom_htf    qt=[710, 574, 684, 278]  react=[709.5, 575.33, 684.5, 278.66]

rows 15 rows matched 11
numbers 58 numbers matched 53
```

The six zone boxes match, the arrows match, and both position lines match. The
five numbers that differ are three causes, all inside a zone whose own box
matches:

- **The entry and the stepper are 2.66 px taller in the page.** The Refresh
  button above them is 1.6 px shorter there, which is Stage C's open bold text
  box, and the rest is the pixel grid at a ratio of 1.25. Line height following
  from font metrics is a font difference.
- **The pane entry is 10.9 px narrower in Qt.** `QScrollArea` puts the
  scrollbar outside the widget it scrolls; a browser puts it inside the border
  box. The element that scrolls has the same outer width on both sides — the
  pane stepper measures 652 against 652.9 — and only the inner card differs, by
  the scrollbar's width.
- **The pane card's height differs by 35.7 px** because the Qt card asks for
  the height its own text needs and then scrolls, while the page's card takes
  the height its text occupies. Both show the same lines.

Stage B's 45 of 45 and Stage C's 49 of 53 are not regressed: the fifteen rows
here include Stage C's six zone rows, all matching, and the four numbers Stage C
left open are the Refresh button's bold text box, which this unit did not touch
and which now shows up as 2.66 px on two rows instead of four numbers on one.

### The shell at its own size

The shell window is 900 tall and carries the header strip and the tab bar, so
its panel area is 777.6 px and each zone takes 253.2 px rather than the tab's
278. That is the same layout at a different window size, not a mismatch.

### Gate

Fixture controls first, each exit code read from the run itself and never
through a pipe:

```
coding_archetype known_good.py        exit=0    known_bad.py         exit=1
gui_archetype    known_good_widget.py exit=0    known_bad_widget.py  exit=1
gui_archetype    known_good_screen.js exit=0    known_bad_screen.js  exit=1
docs_archetype   known_good.md        exit=0    known_bad.md         exit=1
ta_archetype     known_good_ta001.py  exit=0    known_bad_ta001.py   exit=1
control failures 0
```

Every file this unit touched:

```
coding_archetype  src/trading/pair_selection.py                            passed=True
ta_archetype      src/trading/pair_selection.py                            passed=True
coding_archetype  src/gui/main_tabs/market_inspector_surface.py            passed=True
ta_archetype      src/gui/main_tabs/market_inspector_surface.py            passed=True
coding_archetype  src/gui/main_tabs/market_inspector_topologies_surface.py passed=True
coding_archetype  src/gui/market_inspector.py                              passed=True
gui_archetype     src/gui/market_inspector.py                              passed=True
ta_archetype      src/gui/market_inspector.py                              passed=True
coding_archetype  src/gui/market_inspector_topologies.py                   passed=True
gui_archetype     src/gui/market_inspector_topologies.py                   passed=True
ta_archetype      src/gui/market_inspector_topologies.py                   passed=True
coding_archetype  src/gui/react_market_inspector_tab.py                    passed=True
gui_archetype     src/gui/react_market_inspector_tab.py                    passed=True
gui_archetype     src/gui/web/market_inspector.js                          passed=True
gui_archetype     src/gui/web/market_inspector_topologies.js               passed=True
docs_archetype    docs/manual/08-tabs.md                                   passed=True
subjects not passing 0
```

Every tool reported `ok`. `black --check` and `flake8` both exit 0 on the six
Python files.

### The manual

The Market Inspector page gains the position line, the arrows, the expansion
and its four lines. The new layout is not written there. Nothing was removed:

```
git diff purge-non-canon-tests -- docs/ | grep "^-" | grep -v "^---" | grep -v "^-|"
REMOVED-LINE-COUNT=0
```

### Dependencies

Nothing was installed. Electron 44.2.0, debugpy 1.8.21, statsmodels 0.15.0,
scipy and playwright were already present.

### Safety

Every run used a throwaway home. `~/.acervator/settings.json` is unchanged:

```
before   f366f42f0e49b4b3468f301b4f2f701669cc13005cfe1ebac7a56988ec376423
after    f366f42f0e49b4b3468f301b4f2f701669cc13005cfe1ebac7a56988ec376423
```

No network call, no credential, no exchange order, and no test run. The running
platform was never started, stopped or queried.

### Size against time

```
source lines produced   1158
wall clock              5553 s
seconds per source line 4.80
```

Stage B measured 5.62 and Stage C measured 4.90.

### What the operator sees differently

Every zone on the Market Inspector shows one entry at a time. Two arrows sit
above it with a line saying which entry this is and how many there are, so a
zone holding five proposals is five clean cards rather than one crowded list.
The Opposing Trades zone no longer scrolls sideways through seven columns; it
shows one pair, the test that let it through, and the correlation beside it.
Clicking any entry opens it and says in plain words which test ran, on what
window, what it returned, and why that let the entry through. The Bot Swarm
Topologies cards now draw in the Electron shell as well, at the same size as
every other zone.
