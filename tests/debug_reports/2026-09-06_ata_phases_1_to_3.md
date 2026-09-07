# ATA-SPM phases one to three

The ATA-SPM zone scans. A field names a sector, a box beside it names the asset
class, four check boxes name the timeframes, and Scan Now runs phases one, two
and three. Each phase leaves something to read: the sectors scanned and what
each returned, the asset and its vote, and the chart with every confirming
indicator explained in one standardised sentence.

Renders:

```
docs/audits/2026-09-06_units/ata_phases_qt.png
docs/audits/2026-09-06_units/ata_phases_react.png
docs/audits/2026-09-06_units/ata_phases_electron.png
docs/audits/2026-09-06_units/ata_phases_expanded_react.png
```

## Edits

`src/trading/ata_spm.py` — new, and the whole engine. `Sector` holds a name, an
asset class and the timeframes ticked on it. `timeframes_for` gives crypto
`5m 1h 1d 1w` and every other class `1h 1d 1w 1M`; `TIMEFRAME_LABELS` carries
the operator's wording for each. `evaluate` runs `VotingEngine.compute_all` on
every asset of every ticked timeframe and answers a `SectorScan`, which carries
the assets scanned, the votes cast and the symbols that held no candles.
`identify` keeps the votes whose `is_reversal` is true, strongest first. `pull`
answers a `ChartPull`: the candle count, the last close, the three Bollinger
band values, and one `IndicatorMessage` per confirming voter. `run` is the three
in order. `SectorBoard` holds the sectors, the typed text, the chosen class and
the last run, so the Qt tab and the screen model share one implementation of the
field, the class box, the four boxes and Scan Now. No indicator maths is written
here; every direction, confidence and reading comes off the voter that produced
it.

`src/trading/market_inspector.py` — the analyzer keeps the candles it scanned as
`last_candles`, keyed by symbol then timeframe. Scan Now charts each sector asset
off those, so it costs no second fetch.

`src/gui/main_tabs/market_inspector_surface.py` — `zone_entry` gains `detail` and
`method_text`, and `zone_view` uses them when an entry names them, so the one
stepper draws a phase readback as well as a verdict. `sector_entry` turns one
`SectorScan` into the entry the zone steps through, and `phase_one_rows`,
`phase_two_rows` and `phase_three_rows` write the expanded lines. `phase_row`
names each line for its phase and for the thing it reports on, so two lines of
one phase never share a name. `ata_spm_zone_text` gives the zone its own empty
sentence. `left_module_rows` takes the sector count. `sector_assets` reads the
shipped sector map and `inspector_candles` reads the analyzer.
`MarketInspectorScreenModel` gains `board`, `scan_now`, `toggle_timeframe`,
`set_sector_text`, `set_sector_class`, `ata_entries` and `ata_row`, and its
bridge handler reads `sector_text`, `sector_class`, `toggle_timeframe` and
`scan_now`. `FIELD_PADDING_PX`, `FIELD_BORDER_PX`, `CHECK_INDICATOR_PX` and
`CHECK_LABEL_SPACING_PX` publish the theme's own input metrics.

`src/gui/market_inspector.py` — `_build_ata_row` builds the Qt row inside the
ATA-SPM group: the sector field, the class box, the four check boxes and Scan
Now. `_on_scan_now`, `_on_class_changed` and `_on_timeframe_toggled` drive the
board, and `_render_ata_row` writes the class box and the boxes back from it.
Stepping the zone redraws the row, because the boxes belong to the sector on
screen. The file's own copies of `_ata_spm_text`, `_opposing_trades_text`,
`_arbitrage_text` and `_left_module_rows` are gone; it imports the surface's
`left_module_rows` instead, so the three module lines have one implementation.

`src/gui/react_market_inspector_tab.py` — the page's presses reach the model:
`sector-field`, `class-box`, `timeframe-box` and `scan-now`. The tab's board and
the screen model's board are one object.

`src/gui/web/market_inspector.js` — `AtaRow` is the React half of the same row,
built from `SectorField`, `ClassBox`, `TimeframeBox` and `ScanNowButton`.
`fieldStyle` gives the field and the class box the theme's padding and border,
and the check box takes the theme's indicator size and label spacing.
`zoneContent` puts the row in the ATA-SPM zone and the Refresh row in Opposing
Trades. The default action takes each new press to the bridge and redraws.

`src/gui/web/market_inspector.css` — the sector field, the class box, the check
boxes and Scan Now take the same colour rules the Refresh button already takes.

`docs/manual/08-tabs.md` — the Market Inspector page gains the control row, the
four timeframes per asset class, the three phases, the reversal test and the
standardised message. No sentence was deleted or reworded.

## Errors detected

### 1 Scan Now found no reversal on a tape that had one

The first run of the engine under the strictest interpreter mode returned five
votes and no call:

```
PYTHONWARNINGS=error python -X dev -X faulthandler ata_engine_drive.py
=== phase 1 Evaluate ===
l1 (crypto) 3 asset(s) · 5 vote(s) · 0 reversal call(s)
     vote BTC 1d bearish net=-0.3908 conf=0.0334 bb=-0.5019 band=bullish reversal=False
     vote ETH 1d bullish net=2.7514 conf=0.2352 bb=1.5208 band=bearish reversal=False
=== phase 2 Identify ===
no call
EXIT=0
```

The refusals are correct. On both rows the band voter and the panel point
opposite ways: the price is outside a band and the other eleven voters still
read the trend that took it there. The defect was the test tape, which drove a
single-bar spike far past the band instead of a dip inside a trend. Corrected by
building the tape the platform actually trades — a rising series whose last
close drops toward the lower band. The same run then answers a call:

```
=== phase 2 Identify ===
BTC on 1wk: bullish reversal net +0.9473 · confidence 8% · band position 0.3381
=== phase 3 Pull ===
200 1wk candles, last close 217.224
   Bands: lower 209.514 · middle 220.915 · upper 232.315
    Bollinger Bands: band position 0.3381. Votes bullish at 20% confidence.
EXIT=0
```

The control is the same run with no candle source. It answers no vote and lists
every symbol as unread, so the count of zero is a fact about the market and not
about the instrument:

```
=== control: the same run with no candle source ===
scans 2 calls 0
   1d votes 0 unread ['BTC', 'ETH', 'SOL']
```

### 2 Every indicator line printed its own name twice

Read off the running Qt widgets:

```
detail  Bollinger Bands: Bollinger Bands: band position 0.3381. Votes bullish at 20% confidence.
detail  Vortex: Vortex: VI+ less VI- at +0.2000. Votes bullish at 40% confidence.
```

The expanded line was built by the helper that writes `name: value`, and the
standardised message already opens with the indicator's name. Corrected by
letting an indicator's own sentence be the whole line. The same run afterwards:

```
detail  Bollinger Bands: band position 0.3381. Votes bullish at 20% confidence.
detail  Vortex: VI+ less VI- at +0.2000. Votes bullish at 40% confidence.
```

### 3 Four expanded lines of one phase shared one name

Every phase-one line was named `Phase 1 Evaluate`. Each host reads a line back
by its name, so four lines under one name cannot be told apart. Corrected by
naming each line for its phase and for the thing it reports on:

```
Phase 1 Evaluate 5m: 0 vote(s), 2 without candles
Phase 1 Evaluate 1hr: 0 vote(s), 2 without candles
Phase 1 Evaluate 1d: 2 vote(s), 0 without candles
Phase 1 Evaluate 1wk: 1 vote(s), 1 without candles
```

### 4 The React tab crashed on a method the Qt tab owns

```
File "src/gui/market_inspector.py", in _zone_views
    self._pairs_tbl.rowCount(),
AttributeError: 'MarketInspectorReactTab' object has no attribute '_pairs_tbl'
```

The React tab inherits the Qt tab and builds no Qt table. Nothing in the running
program calls that method on the React tab; the driver did. The driver was
pointed at the payload the page is drawn from instead, which is what the page
actually reads.

### 5 The React field, class box and check boxes ignored the theme

Read off the real widgets and off the page's own elements, both sized 1400 by
860, with the theme applied to each:

```
sector_field   qt=[16, 56, 130, 37]   react=[15.8, 63.4, 130, 20]
class_box      qt=[152, 56, 110, 38]  react=[151.8, 63.8, 110, 19.2]
box_0          qt=[268, 64, 49, 22]   react=[267.8, 64.4, 34.8, 18]
scan_now       qt=[488, 57, 103, 36]  react=[412.7, 55.8, 106.9, 35.2]
```

The theme gives an input 8 px of padding above and below, 12 px each side and a
1 px border. It draws a check box indicator at 22 px with 8 px between it and
its text. Measured on the running widget:

```
PM_IndicatorWidth  22
PM_CheckBoxLabelSpacing 8
```

Corrected by publishing those four numbers and drawing the page from them. The
same four boxes afterwards:

```
sector_field   qt=[16, 56, 130, 37]   react=[15.8, 56.2, 130, 34.4]
class_box      qt=[152, 56, 110, 38]  react=[151.8, 55.8, 110, 35.2]
box_0          qt=[268, 64, 49, 22]   react=[267.8, 62.4, 46.8, 22]
scan_now       qt=[488, 57, 103, 36]  react=[480.7, 55.8, 106.9, 35.2]
```

### 6 The React controls drew in the browser's own colours

The Refresh button in the same zone draws dark, and Scan Now drew light grey
beside it. The field drew white and the check boxes drew blue. Corrected by
adding the four new part names to the colour rules the Refresh button already
uses, which is the same handling the screen already has for its own switch.

### 7 The picture of the React tab did not follow the page

The page held twelve expanded lines and the picture kept showing none:

```
before toggle, detail lines 0.0
after toggle, detail lines 12.0
```

Both pictures came back with the same 154 colours. A web view composites into a
surface the screen grab reads stale. Corrected in the driver by hiding and
showing the window before each grab, which forces a fresh surface. The expanded
picture then reported 163 colours and carries the five indicator sentences.

### The debugger, and what it printed

Both variants build and run clean under the strictest interpreter mode:

```
PYTHONWARNINGS=error python -X dev -X faulthandler ata_qt_drive.py
=== ACERVATOR_VARIANT=qt ===
variant qt class MarketInspectorTab
EXIT=0

=== ACERVATOR_VARIANT=react ===
variant react class MarketInspectorReactTab
EXIT=0
```

The Electron shell was started with the backend redirected to the bridge under a
throwaway home. `ELECTRON_RUN_AS_NODE` was removed from the child's environment
and the shell was started from its own executable, which needs no node on the
path. Its own log holds nothing but the debugging address:

```
DevTools listening on ws://127.0.0.1:9333/devtools/browser/...
```

## Resolution

### The three phases, driven and read back

Qt, read off the real widgets after pressing Scan Now on the `l1` sector:

```
sector field    'l1'
class box       crypto
boxes           [['5m', True], ['1hr', True], ['1d', True], ['1wk', True]]
position        1 of 1
headline        l1 (crypto)
meta            2 asset(s) · 3 vote(s) · 1 reversal call(s)
method          BTC on 1wk: bullish reversal
   detail       Phase 1 Evaluate 5m: 0 vote(s), 2 without candles
   detail       Phase 1 Evaluate 1hr: 0 vote(s), 2 without candles
   detail       Phase 1 Evaluate 1d: 2 vote(s), 0 without candles
   detail       Phase 1 Evaluate 1wk: 1 vote(s), 1 without candles
   detail       Phase 2 Identify BTC 1wk: bullish reversal · net +0.9473 · confidence 8% · band position 0.3381
   detail       Phase 3 Pull BTC 1wk: 200 candles, last close 217.224
   detail       Phase 3 Pull BTC bands: lower 209.514 · middle 220.915 · upper 232.315
   detail       Bollinger Bands: band position 0.3381. Votes bullish at 20% confidence.
   detail       Vortex: VI+ less VI- at +0.2000. Votes bullish at 40% confidence.
   detail       Ichimoku Cloud: price above the cloud. Votes bullish at 79% confidence.
   detail       ADX: ADX 93.54. Votes bullish at 100% confidence.
   detail       Supertrend: +0.288% from the Supertrend line. Votes bullish at 21% confidence.
after untick 5m [['5m', False], ['1hr', True], ['1d', True], ['1wk', True]]
sector ticked   ('1h', '1d', '1w')
```

React, read off the page's own elements, the same twelve lines and the same
seven values. Unticking a box moves the sector, not the screen:

```
sector field    'l1'
class box       crypto
classes         ['crypto', 'stocks', 'metals', 'derivatives', 'forex']
boxes           [['5m', '5m', True], ['1h', '1hr', True], ['1d', '1d', True], ['1w', '1wk', True]]
position        1 of 1
headline        l1 (crypto)
meta            2 asset(s) · 3 vote(s) · 1 reversal call(s)
method          BTC on 1wk: bullish reversal
after untick 5m [['5m', '5m', False], ['1h', '1hr', True], ['1d', '1d', True], ['1w', '1wk', True]]
```

The Electron shell, with the backend redirected to the bridge. The sector name
is resolved against the shipped sector map, which answers eighteen assets for
`l1`:

```
selected   market_inspector
faults     null
sector_value  'l1'
headline   l1 (crypto)
position   1 of 1
meta       18 asset(s) · 0 vote(s) · 0 reversal call(s)
method     No chart carried a reversal vote.
detail     Phase 1 Evaluate 5m: 0 vote(s), 18 without candles
           Phase 1 Evaluate 1hr: 0 vote(s), 18 without candles
           Phase 1 Evaluate 1d: 0 vote(s), 18 without candles
           Phase 1 Evaluate 1wk: 0 vote(s), 18 without candles
           Phase 2 Identify: No chart carried a reversal vote.
zones      ["ATA-SPM","Opposing Trades","Multi-Exchange Arbitrage",
            "ATA-SPM Ready to Send","Bot Swarm Topologies",
            "Phantom Bot HTF Signals"]
```

**What the shell can and cannot show, and why.** Phase one runs there for real
against the real sector map. Phases two and three have nothing to show, because
the bridge process holds no candles: Scan Now charts each asset off the candles
the Market Inspector's own Refresh fetched, and Refresh in the bridge has no
exchange connector to fetch from. The zone says exactly that on every timeframe
line rather than drawing nothing. No market data call was made in this unit.

### The indicators, and where each formula comes from

Every direction, confidence and reading is produced by the voter that owns it.
The engine is `VotingEngine.compute_all`; the consensus and its deadband are
`VotingSummary.consensus_direction`. All twelve are described in
`docs/manual/07-indicators.md` under **Indicator formulae**, and the aggregate
under **Net, Comp and Conf** and **The deadband**.

```
Bollinger Bands          Bollinger Bands      bb_position
Vortex                   Vortex Indicator     separation
MACD                     MACD                 histogram
Stochastic RSI           Stochastic RSI       k
Ichimoku Cloud           Ichimoku Cloud       price_vs_cloud
Volume                   Volume               mfi
Slingshot                Slingshot            momentum
ADX                      ADX and DMI          adx
Supertrend               Supertrend           dist_pct
Z-Score                  Z-Score              z
Kaufman Efficiency Ratio Kaufman Efficiency Ratio  er
RSI                      RSI                  rsi
```

The five that confirmed the call above are Bollinger Bands, Vortex, Ichimoku
Cloud, ADX and Supertrend. Each message names the indicator, the reading that
indicator published, its direction and its confidence, in one format, so the
same condition always reads the same way.

### The reversal test, and why it is this one

A chart carries a reversal when the Bollinger Bands voter and the panel's
consensus name the same direction. The band voter is the one that reads where
the close sits between the bands, so its vote is the price being at a band. The
consensus is the twelve-voter reading the manual describes under **The
deadband**. A neutral consensus is not a reversal, and a band voter pointing
against the consensus is not one either. No score, threshold or coefficient was
invented for this unit, and no value produced by one indicator is read by
another.

### Dimensions

Read off the Qt widgets and off the page's own elements, both sized 1400 by 860,
with the theme applied to each. A row matches when every number in it is within
1.5 px.

```
MATCH   tab                  qt=[1400, 860]        react=[1400, 860]
MATCH   zone ata_spm         qt=[6, 6, 685, 278]   react=[6, 6, 684.5, 278.66]
MATCH   zone opposing_trades qt=[6, 290, 685, 278] react=[6, 290.66, 684.5, 278.66]
MATCH   zone arbitrage       qt=[6, 574, 685, 278] react=[6, 575.33, 684.5, 278.66]
MATCH   zone ready_to_send   qt=[710, 6, 684, 278] react=[709.5, 6, 684.5, 278.66]
MATCH   zone topologies      qt=[710, 290, 684, 278] react=[709.5, 290.66, 684.5, 278.66]
MATCH   zone phantom_htf     qt=[710, 574, 684, 278] react=[709.5, 575.33, 684.5, 278.66]
DIFFER  sector field         qt=[16, 56, 130, 37]  react=[15.8, 56.2, 130, 34.4]
DIFFER  class box            qt=[152, 56, 110, 38] react=[151.8, 55.8, 110, 35.2]
DIFFER  box 5m               qt=[268, 64, 49, 22]  react=[267.8, 62.4, 46.81, 22]
DIFFER  box 1hr              qt=[323, 64, 49, 22]  react=[320.6, 62.4, 47.44, 22]
DIFFER  box 1d               qt=[378, 64, 45, 22]  react=[374.05, 62.4, 43.54, 22]
DIFFER  box 1wk              qt=[429, 64, 53, 22]  react=[423.59, 62.4, 51.11, 22]
DIFFER  Scan Now             qt=[488, 57, 103, 36] react=[480.7, 55.8, 106.9, 35.2]
DIFFER  stepper              qt=[16, 100, 665, 174] react=[15.8, 97, 664.9, 177.86]
DIFFER  back button          qt=[16, 100, 26, 24]  react=[15.8, 97, 26, 24]

rows 26 rows matched 17
numbers 62 numbers matched 45
```

Text, read off both sides:

```
MATCH   box count
MATCH   box wording
MATCH   box ticked state
MATCH   position line
MATCH   headline
MATCH   meta line
MATCH   method line
MATCH   twelve expanded lines
MATCH   sector field value
MATCH   class box value
text rows 10 matched 10
```

**The six zone boxes match and every value matches.** The seventeen numbers that
differ are one cause: the text box the two font stacks produce. The theme's
padding and border are now identical on both sides — 12 px each side, 8 px above
and below, a 1 px border — and what is left is the line the font draws inside
them, 19 px in Qt against 16.4 px in the page. That gives the field 2.6 px of
height and the class box 2.8 px, which pushes the stepper below them by 3 px and
lengthens it by 3.9 px. The same font stack renders the four box words about
2.2 px narrower each, and those four widths add up to the 7.3 px Scan Now sits
left by; its own bold text accounts for its 3.9 px of width. Line height and
glyph width following from font metrics are font differences.

Stage C's forty-five of forty-nine and the topology list's fifty-three of
fifty-eight are not regressed. The six zone rows both units measured all match
here, and the twelve rows this unit adds are new surface.

### Gate

Fixture controls first, each exit code read from the run itself and never
through a pipe:

```
coding_archetype known_good.py           exit=0    known_bad.py           exit=1
gui_archetype    known_good_widget.py    exit=0    known_bad_widget.py    exit=1
gui_archetype    known_good_screen.js    exit=0    known_bad_screen.js    exit=1
docs_archetype   known_good.md           exit=0    known_bad.md           exit=1
ta_archetype     known_good_ta001.py     exit=0    known_bad_ta001.py     exit=1
ta_archetype     known_good_ta003.py     exit=0    known_bad_ta004.py     exit=1
control failures 0
```

Every file this unit touched:

```
coding_archetype  src/trading/ata_spm.py                                   passed=True
ta_archetype      src/trading/ata_spm.py                                   passed=True
coding_archetype  src/trading/market_inspector.py                          passed=True
ta_archetype      src/trading/market_inspector.py                          passed=True
coding_archetype  src/gui/main_tabs/market_inspector_surface.py            passed=True
ta_archetype      src/gui/main_tabs/market_inspector_surface.py            passed=True
coding_archetype  src/gui/market_inspector.py                              passed=True
gui_archetype     src/gui/market_inspector.py                              passed=True
ta_archetype      src/gui/market_inspector.py                              passed=True
coding_archetype  src/gui/react_market_inspector_tab.py                    passed=True
gui_archetype     src/gui/react_market_inspector_tab.py                    passed=True
gui_archetype     src/gui/web/market_inspector.js                          passed=True
docs_archetype    docs/manual/08-tabs.md                                   passed=True
subjects not passing 0
```

Every tool reported `ok`. `black --check` and `flake8` both exit 0 on the five
Python files.

**One file has no archetype, and the gate says so rather than passing it.**

```
gui_archetype src/gui/web/market_inspector.css
  no analyzer for css - this file type was NOT examined, which is not the
  same as clean
  exit=1
```

The eighteen lines added to that file are colour rules for four new part names,
written against the rules the Refresh button in the same file already uses. No
style sheet is checked by any archetype today. That is a proposed rule for the
operator, not something this unit changes.

### The manual

The Market Inspector page gains the control row, the four timeframes per asset
class, the three phases, the reversal test and the standardised message. The
six-zone layout is not written there. Nothing was removed:

```
git diff purge-non-canon-tests -- docs/ | grep "^-" | grep -v "^---" | grep -v "^-|"
REMOVED-LINE-COUNT=0
```

### Dependencies

Nothing was installed. Electron 44.2.0, debugpy 1.8.21, statsmodels 0.15.0,
playwright and scipy were already present.

### Safety

Every run used a throwaway home. `~/.acervator/settings.json` is unchanged:

```
before   f366f42f0e49b4b3468f301b4f2f701669cc13005cfe1ebac7a56988ec376423
after    f366f42f0e49b4b3468f301b4f2f701669cc13005cfe1ebac7a56988ec376423
```

No network call, no credential, no exchange order and no test run. The running
platform was never started, stopped or queried.

### Size against time

```
source lines produced   1508
wall clock              3792 s
seconds per source line 2.51
```

Stage B measured 5.62, Stage C 5.39 and the topology list 4.80.

### What the operator sees differently

The ATA-SPM zone is no longer a sentence saying nothing is wired. He types a
sector, picks its asset class, ticks the timeframes he wants and presses Scan
Now. The zone then names the sector, how many assets it scanned, how many votes
came back and how many of those are reversal calls. Clicking it opens the whole
run: what each timeframe returned, which asset carried a reversal and on which
timeframe, and the chart it was called on with each confirming indicator
explained in the same words every time. Phases four to eight are not built, so
nothing leaves the machine and Ready to Send still holds nothing.
