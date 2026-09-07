# Stage C — the selection method

Stage C of issue #407. Every proposal on the Market Inspector now names the
method that produced it, the window it ran on and the statistic that passed. A
proposal with no method behind it is not built. The screen also carries the
six-zone layout the operator set on 2026-09-06: ATA-SPM, Opposing Trades and
Multi-Exchange Arbitrage down the left, ATA-SPM Ready to Send above Bot Swarm
Topologies on the right.

Renders:

```
docs/audits/2026-09-06_units/stageC_cointegration_qt.png
docs/audits/2026-09-06_units/stageC_cointegration_react.png
docs/audits/2026-09-06_units/stageC_cointegration_electron.png
```

## Edits

`src/trading/pair_selection.py` — new. The published tests, as thin wrappers
over installed libraries. `cointegration_test` runs
`statsmodels.tsa.stattools.coint` for the Engle-Granger two-step and
`statsmodels.tsa.vector_ar.vecm.coint_johansen` for the Johansen trace test.
`correlation_test` runs `scipy.stats.pearsonr` for the coefficient and its
two-sided t test. `band_distance_result` records the distance a bot sits from
its target balance. No formula is written here. Each answers a `MethodResult`
carrying the method, the observations, the statistic, the p-value and the text
the screen prints. `score_from_p_value` and `score_from_correlation` are the
only two score rules, and both read the statistic the test returned.

`src/trading/market_inspector.py` — `_find_opposing_pairs` keeps the 30-day
correlation window as the candidate filter and then runs `cointegration_test`
on the full close series. A pair the test refuses never reaches the table.
`OpposingPair` gains `method`. `MarketInspector` keeps `last_tested`, every
candidate the gate ran on with its verdict, and `last_closes`, the daily
closes the scan tested, which is what lets the topology detectors run a test at
all. The ranking is by p-value ascending, so the strongest equilibrium sits
first, where it used to be by correlation.

`src/trading/topology_proposals.py` — `make_proposal` takes a `MethodResult`
and writes it onto every proposal. `detect_momentum_funnel` and
`detect_sector_cluster` build a cluster only from pairs `correlation_test`
passes, through `_cluster_correlation`. `detect_mean_reversion_pair` carries
the cointegration verdict the Market Inspector already ran, or runs it, and
drops a row that fails. `detect_distance_to_band` records
`band_distance_result`. `detect_all_topologies` reads `closes_by_asset` from
the context in place of the `correlations` dict.

`src/gui/main_window.py` — `_build_topology_proposals` puts the analyzer's
daily closes into the detector context and carries each opposing pair's method
with it. The comment `# Left empty: no correlation source is assembled here.`
and the empty `correlations` dict are gone, because the closes are now
assembled.

`src/gui/main_tabs/market_inspector_surface.py` — `PAIR_COLUMNS` grows from
four to seven: Long side, Short side, Method, Window, Statistic, Correlation,
Score. `PAIRS_GROUP_TITLE` names the method instead of Pearson. `fill_pair_row`
writes the three new cells. `PairState` gains `method`. `right_zone_rows` and
`ready_to_send_text` publish the two right-side zones, and the screen model
answers `right_zones`. `BUTTON_PADDING_PX` and `BUTTON_FONT_WEIGHT` publish the
themed push button, measured off the running widget.

`src/gui/market_inspector.py` — the Qt side of the same. The pairs table takes
its columns and its title from the surface rather than a second copy. The
three left zones now hold the Refresh row and both tables inside Opposing
Trades. The right pane is a column of two zones, and the topology pane sits
inside the lower one.

`src/gui/main_tabs/market_inspector_topologies_surface.py` — `method_text`
builds the card's method line and `CARD_METHOD_FORMAT` sets its shape. The card
payload carries `method`.

`src/gui/market_inspector_topologies.py` — the Qt card draws that line under
its counts.

`src/gui/web/market_inspector.js` — `groupFrame` and `groupTitleStyle` are one
set of themed group-box metrics both group kinds now use. `scanContent` puts
the Refresh row and the two tables inside the Opposing Trades zone.
`TopologySlot` draws the two right zones and `RightZone` draws each, the lower
one carrying the slot the proposals pane is moved into. `RefreshButton` takes
the theme's padding and weight.

`src/gui/web/market_inspector_topologies.js` — the card draws its method line
from the payload, and `checkMarkup` refuses one carrying markup.

`docs/manual/08-tabs.md` — the Market Inspector page gains the method, the
window and the significance. No sentence was deleted or reworded. The new
layout is not written there; the operator accepts the design after running it.

## Errors detected

### 1 No price series reached the topology detectors, so no test could run

`_build_topology_proposals` in `src/gui/main_window.py` assembled the ticker
snapshot, the bot snapshot and the opposing pairs, then handed the detectors an
empty correlations dict under its own comment:

```python
# Left empty: no correlation source is assembled here.
correlations: dict[tuple[str, str], float] = {}
```

`detect_momentum_funnel` reads `correlations.get(key, 0.0)`, so every pair
scored 0.0 against a floor of 0.75 and no cluster could ever reach three
members. Measured on the shipped code path, the momentum funnel could produce
nothing at all, and the only detector that could fire without a series was the
sector cluster, which used no statistic. That is the screen the operator saw:
`Sector cluster: layer1` and `Momentum funnel: memes` with no method named.

Corrected by keeping the scan's daily closes on the analyzer as `last_closes`
and passing them into the detector context as `closes_by_asset`. Driven with
five meme-tagged assets that share no movement and four layer-1 assets that do:

```
=== sector clusters, sector map alone versus the t test ===
with no closes to test: 0 proposals
  Sector cluster (layer1): SOL → AVAX, ADA, DO   score=67 method=Correlation
    window=365d statistic=r=+0.672 over 6 pairs · p≤0.0000
sectors that reached the screen: ['Sector cluster (layer1)']
```

The `memes` sector no longer reaches the screen. Five assets sharing a tag and
nothing else produce no proposal, because no pair inside the sector clears the
Pearson t test. That is the "oh, these are all meme coins" case being refused.

### 2 The React table group grew past the pane instead of scrolling

With three more columns the Opposing Pairs columns sum to 873 px inside a
665 px table. Qt shows a horizontal scrollbar; React grew the group instead.
Read off the real objects:

```
Qt     pairs group box [6, 570, 685, 240]
React  pairs group box [6, 538.4, 838.475, 219.6]
```

`TableGroup` sets the grid to `max-content` under the Qt resize mode, and a
flex item refuses to shrink below its content by default. Corrected with
`minWidth: 0` on the group and on the scrolling body, which puts the overflow
inside the body where Qt puts it. The group then measured 685.29 against Qt's
685.

### 3 The React table groups drew their title in flow, 22 px shallower than Qt

After the width fix the group heights still disagreed by 20 px, on both tables.
Read off the running widget and off the page:

```
Qt     signals group [6, 291, 685, 273]   table inside it at y 50
React  signals group [6, 279.4, 685.29, 253]   body inside it at y 27.8
```

The themed `QGroupBox` draws its title inside the group's own margin and
reserves a 41 px band; the React fieldset let its legend take a row of 16.8 px.
Unit 12 corrected exactly this for the three left modules and published
`MODULE_FRAME_PX`, `MODULE_MARGINS_PX` and `MODULE_TITLE_PADDING_PX`, but
`TableGroup` was never moved onto them and no earlier unit compared a table
group's height. Corrected by giving both group kinds one helper, `groupFrame`
with `groupTitleStyle`, reading the same three published measurements. Both
groups then measured 273 and 239.6 against Qt's 273 and 240.

### 4 The React Refresh button ignored the theme's padding

```
Qt     refresh button [6, 249, 88, 36]
React  refresh button [6, 249, 64.79, 24.4]
```

`market_inspector.css` gave the button `padding: 3px 12px`; the theme gives
`QPushButton` `padding: 8px 20px` and a bold face. The 11.6 px of height
difference pushed every group below it out of place. Corrected by publishing
`BUTTON_PADDING_PX` and `BUTTON_FONT_WEIGHT` and setting them on the element,
which also reaches the Electron shell, where no style sheet for this panel is
loaded. The button's computed box afterwards:

```
paddingLeft 20px  paddingTop 8px  paddingRight 20px  paddingBottom 8px
borderTopWidth 0.8px  fontWeight 700
```

### 5 The TA archetype refused two comparisons for mixed units

```
ta-quant TA004 src/trading/market_inspector.py line 175
  units mismatch: 'z' (dimensionless) compared against 'self._z_threshold'
  (absolute)
ta-quant TA004 src/trading/topology_proposals.py line 561
  units mismatch: 'dist_pct' (dimensionless) compared against 'deep_pct'
  (absolute)
```

Both predate this unit: the same two verdicts come back `passed=False` on
`purge-non-canon-tests` in a detached worktree. Both are the same shape — a
value produced by a division compared against a threshold that was not.
Corrected by comparing the two sides in the same units. `_analyze_tf` now
compares `price - sma` against `self._z_threshold * std`, and
`detect_distance_to_band` compares `pos - tgt` against `tgt * deep_pct / 100.0`.
Both rewrites are the earlier ratio test multiplied through by a positive
number the code already guards, so nothing changes. Driven on 3000 timeframe
analyses across a random walk, a flat window, a gap and a spike, and on 4000
bot snapshots at target balances from a hundredth of a cent to a million
dollars:

```
_analyze_tf: 3000 analyses, 587 at an extreme, 0 mismatched
detect_distance_to_band: 4000 snapshots, 1647 deep, 0 mismatched
```

The 587 extremes and 1647 deep snapshots are the positive control: the check
had something to report and reported no difference.

### 6 The docs archetype refuses `docs/manual/05-novel-concepts.md`

```
vale docs/manual/05-novel-concepts.md line 19
  Don't start a sentence with 'So '.
```

Line 19 is the operator's own account of 2017, and the brief forbids rewording
any existing sentence. The verdict is the same on `purge-non-canon-tests`, so
it predates this unit. The passage this unit had added to that page was
reverted, which takes the file out of this unit's subject list. The
`_find_opposing_pairs` excerpt on that page now shows only the correlation
step, which still runs; it does not show the cointegration gate that follows.

### The debugger, and what it printed

Both variants build clean under the strictest interpreter mode:

```
PYTHONWARNINGS=error python -X dev -X faulthandler stageC_variants.py <variant>
=== ACERVATOR_VARIANT=qt ===
EXIT=0
variant qt class MarketInspectorTab
tested 3 passed 1
proposals 1
=== ACERVATOR_VARIANT=react ===
EXIT=0
variant react class MarketInspectorReactTab
tested 3 passed 1
proposals 1
```

`coint_johansen` emits a `ComplexWarning` from its own eigenvalue routine on
every call, which `PYTHONWARNINGS=error` turns into an exception.
`johansen_trace` holds `warnings.catch_warnings()` round the library call so
the warning stays inside statsmodels, which is why the runs above exit 0.

Under `debugpy`, against the desktop bridge:

```
COMMAND: python -m debugpy --listen 5678 --log-to-stderr ...
STDERR:
0.01s - Debugger warning: It seems that frozen modules are being used, which may
0.00s - make the debugger miss breakpoints. Please pass -Xfrozen_modules=off
0.00s - to python to disable frozen modules.
0.00s - Note: Debugging will proceed. Set PYDEVD_DISABLE_FILE_VALIDATION=1 to disable this validation.
EXIT: 0
```

The Electron shell was reached by starting `desktop/` with the backend
redirected to the bridge under a throwaway home, then selecting the tab through
the running page:

```
tabs: ["trading_tab","market_inspector","bot_visualizer","trade_charts_tab",
       "history_tab","simulator_tab","console_tab","paper_trader_tab",
       "system_status_tab","proof_of_accumulation_tab"]
selected: market_inspector
```

`ELECTRON_RUN_AS_NODE` had to be removed from the child's environment, and
`electron.cmd` needs `node` on PATH, which this shell does not carry;
`node_modules/electron/dist/electron.exe` starts without it.

## Resolution

### The decisions, and why

**Which test gates a pair.** Cointegration, and both of its published forms
must reject. Engle-Granger two-step at a significance of 0.05, and the Johansen
trace statistic for rank zero above its 95% critical value. Engle-Granger
depends on which series is the dependent one; Johansen does not. Requiring both
was measured on 200 pairs a side at a 365-day window:

```
                                    false accepts    true relationships found
engle-granger alone                     7 / 100                  100 / 100
engle-granger and johansen              2 / 100                  100 / 100
```

Requiring both cuts the rate at which unrelated markets slip through from 7% to
2% and finds every genuine relationship either way. It costs nothing, so both
run.

**The window, and why that length.** 365 daily closes. That is the twelve-month
formation period the pairs-trading literature uses, and it is exactly what
`market_inspector_fetcher.DAILY_BARS` already pulls, so no new data is needed.
Length is the choice that matters most here. Measured over 200 pairs a side:

```
window   false accepts / 200   true relationships found / 200
   30           16                        25
   60           10                        67
   90           15                       128
  120            7                       176
  180            7                       195
  365           10                       200
```

The false-accept rate is flat, near the 5% the test is set to. The power is
not: at a year the pair of tests finds every genuine relationship, and at 90
days it finds under two thirds. A pair with fewer than 120 closes is not tested
and is not shown, because below that a refusal describes the window rather than
the markets. `MIN_OBSERVATIONS = 120` is that floor.

**A pair that passes correlation and fails cointegration.** It is not shown.
The candidate is recorded on `last_tested` with its verdict, so a scan that
found nothing reads differently from a scan that tested nothing.

**Correlation on screen.** It stays, as a reported number, in its own column,
computed on the same 30-day window it always used. It decides nothing. The
group title no longer calls the table a Pearson list; it names the test that
does decide.

**Scores.** No scheme is invented. A cointegration-gated proposal scores
`100 * (1 - p)`, so a gated card sits between 95 and 100 by construction,
because the gate is 5%. A correlation-gated proposal scores `100 * |r|`, which
is what the momentum funnel already did. A distance handoff scores the two band
distances added together, which is what it already did. Each is the statistic
its own test returned.

**Why the sector cluster is gated on correlation and not cointegration.** A
sector card routes a hub bot's profit to its spokes, so its claim is that the
assets move together. Pearson with its t test is the published test for that.
A mean-reversion pair claims a divergence will revert, so it is gated on
cointegration. A distance handoff has the same asset on both sides, where
cointegration is meaningless, so it names the band distance it measured. Every
card says which of the three it used.

### The two measured pairs, before and after

Rebuilt on 365 daily closes, with the same 30-day correlation the screen
reported. Every number below came from the real `MarketInspector`:

```
BTC (ENTRY_LONG_HIGH) / DOGE (ENTRY_SHORT_HIGH)
   before   30-day Pearson -0.812, shown, ranked first
   after    cointegration p=0.8560, Johansen trace 3.8 against 15.5 — REJECTED

ETH (ENTRY_LONG_HIGH) / PEPE (ENTRY_SHORT_HIGH)
   before   30-day Pearson -0.744, shown, ranked second
   after    cointegration p=0.1018, Johansen trace 15.5 against 15.5 — REJECTED

SOL (ENTRY_LONG_HIGH) / JUP (ENTRY_SHORT_HIGH)
   30-day Pearson -0.843
   cointegration p=0.0000, Johansen trace 57.5 against 15.5 — KEPT
```

Driven through the shipped function:

```
candidates the 30-day correlation window raised: 3
  REJECTED BTC/DOGE  r=-0.812  p=0.8560 · trace 3.8>15.5
  REJECTED ETH/PEPE  r=-0.744  p=0.1018 · trace 15.5>15.5
  KEPT     SOL/JUP   r=-0.843  p=0.0000 · trace 57.5>15.5
rows that reach the table: 1
  SOL (ENTRY_LONG_HIGH)  JUP (ENTRY_SHORT_HIGH)  method=Cointegration
  window=365d  statistic=p=0.0000 · trace 57.5>15.5  r=-0.843
```

The control, which proves the gate is what removed them. Widening the
significance to 1.0 brings ETH/PEPE back; BTC/DOGE stays out because the
Johansen half still refuses it:

```
rows with significance widened to 1.0: 2
  SOL/JUP  r=-0.843
  ETH/PEPE r=-0.744
rows after restoring the real gate: 1
```

Short and degenerate series are refused with the reason named, not silently:

```
60 bars:       passed=False detail='series shorter than 120 bars'
one flat side: passed=False detail='series holds one repeated price'
no data:       passed=False detail='series shorter than 120 bars'
```

### Every proposal names its method

Driven through `detect_all_topologies` on the same context:

```
  sector_cluster     score=  67.2 method=Correlation    window=365d
                     r=+0.672 over 6 pairs · p≤0.0000
  distance_to_band   score=  38.0 method=Band distance  window=live
                     +20.0% / -18.0% vs 10.0%

proposals: 2
with a method dict: 2
whose method passed: 2
```

The control: with the closes removed, no correlation-gated proposal survives,
and only the band-distance card, which needs no series, is built.

```
proposals with no series: 1
  distance_to_band method=Band distance
```

### Dimensions, after the corrections

Read off the Qt widgets and off the page's own elements, both sized 1400 by
860. A row matches when every number in it is within 1.5 px. Qt right-pane
zones are given in page coordinates so the two sides are in one frame.

```
MATCH   tab size                          qt=[1400, 860]  react=[1400, 860]
MATCH   split size                        qt=[1400, 860]  react=[1400, 860]
MATCH   left pane box                     qt=[0, 0, 697, 860]  react=[0, 0, 696.5, 860]
MATCH   right pane box                    qt=[704, 0, 696, 860]  react=[703.5, 0, 696.5, 860]
MATCH   zone 1 ATA-SPM                    qt=[6, 6, 685, 75]  react=[6, 6, 684.5, 75]
DIFFER  zone 2 Opposing Trades            qt=[6, 87, 685, 642]  react=[6, 87, 684.5, 640]
DIFFER  zone 3 Multi-Exchange Arbitrage   qt=[6, 735, 685, 75]  react=[6, 733, 684.5, 75]
MATCH   zone 4 Ready to Send              qt=[710, 6, 684, 75]  react=[709.5, 6, 684.5, 75]
MATCH   zone 5 Bot Swarm Topologies       qt=[710, 87, 684, 767]  react=[709.5, 87, 684.5, 767]
DIFFER  refresh button box                qt=[10, 71, 88, 36]  react=[9.8, 71.2, 83.96, 34.4]
MATCH   signals group inside its zone     qt=[10, 113, 665, 273]  react=[9.8, 111.6, 664.9, 273]
MATCH   pairs group inside its zone       qt=[10, 392, 665, 240]  react=[9.8, 390.6, 664.9, 239.6]
MATCH   signals table inside its group    qt=[10, 50, 645, 192]  react=[9.8, 49.8, 645.3, 192]
MATCH   pairs table inside its group      qt=[10, 50, 645, 180]  react=[9.8, 49.8, 645.3, 180]
MATCH   pairs column count                qt=[7]  react=[7]

rows 15 rows matched 12
numbers 53 numbers matched 49
```

The four numbers that differ are one cause. The Refresh button's padding and
border now match on both sides — 20 px each side, 8 px top and bottom, a 1 px
border the browser holds to the device grid as 0.8 px at a pixel ratio of 1.25.
What is left is the bold text box: 18 px tall in Qt against 16.8 px in the page,
and 46 px wide against 41.96 px. That is 1.6 px of button height and 4.04 px of
button width, and the button carries the Opposing Trades zone's remaining 2 px
of height, which carries the Multi-Exchange Arbitrage zone's 2 px of position.
Line height following from font metrics is a font difference.

### Text, driven and read back

Every value on both sides, read off the real Qt widgets and off the page's own
elements:

```
MATCH   pairs group title
MATCH   pair columns
MATCH   pair row cells
MATCH   card method line
MATCH   zone titles
MATCH   zone lines
text rows 6 matched 6
```

The six zone titles read the same on both sides:

```
ATA-SPM   Opposing Trades   Multi-Exchange Arbitrage
ATA-SPM Ready to Send   Bot Swarm Topologies
```

The Ready to Send zone is reserved and states what it waits for. Nothing wires
a phase source, so it reads `Phase source not wired. Nothing to approve.` The
bucket itself is phase 6 and is not built here.

The Opposing Pairs row, identical on both sides:

```
SOL (ENTRY_LONG_HIGH) | JUP (ENTRY_SHORT_HIGH) | Cointegration | 365d |
p=0.0000 · trace 57.5>15.5 | -0.843 | 1.50
```

The topology card's method line, identical on both sides:

```
Correlation  •  365d  •  r=+0.672 over 6 pairs · p≤0.0000
```

### The Electron shell

Reached by selecting the Market Inspector tab in the running shell, with the
backend redirected to the bridge under a throwaway home:

```
zones  ["ATA-SPM","Opposing Trades","Multi-Exchange Arbitrage",
        "ATA-SPM Ready to Send","Bot Swarm Topologies"]
lines  ["Phase source not wired.",
        "No scan yet. Press Refresh to look for opposing trades.",
        "Exchange source not wired.",
        "Phase source not wired. Nothing to approve."]
heads  ["Asset","Signal","Score","Daily","Weekly","Active",
        "Long side","Short side","Method","Window","Statistic",
        "Correlation","Score (Long+Short)"]
pairs row  ["SOL (ENTRY_LONG_HIGH)","JUP (ENTRY_SHORT_HIGH)","Cointegration",
            "365d","p=0.0000 · trace 57.5>15.5","-0.843","1.50"]
```

**What the shell does not draw.** The Bot Swarm Topologies zone draws its frame
and its title, and no cards. `market_inspector_topologies.js` calls
`acervatorPanelHost.register` nowhere, so the shell never asks for
`market_inspector_topologies.state` and nothing drives the pane. The shell
reports three panels drawn: `header_strip`, `console_tab` and
`market_inspector`. This is a missing conversion rather than a missing method —
the same is true before this unit — and it is the only place the topology
proposals cannot be read back.

### The manual

The Market Inspector page gains the method, the window, the significance, the
seven columns and the score rules. The new layout is not written there. Nothing
was removed:

```
git diff purge-non-canon-tests -- docs/ | grep "^-" | grep -v "^---" | grep -v "^-|"
REMOVED-LINE-COUNT=0
```

### Gate

Fixture controls first, each exit code read from the run itself and never
through a pipe:

```
coding_archetype known_good.py           exit=0    known_bad.py           exit=1
gui_archetype    known_good_widget.py    exit=0    known_bad_widget.py    exit=1
gui_archetype    known_good_screen.js    exit=0    known_bad_screen.js    exit=1
docs_archetype   known_good.md           exit=0    known_bad.md           exit=1
ta_archetype     known_good_ta001.py     exit=0    known_bad_ta001.py     exit=1
control failures 0
```

Every file this unit touched:

```
coding_archetype  src/trading/pair_selection.py                            passed=True
ta_archetype      src/trading/pair_selection.py                            passed=True
coding_archetype  src/trading/market_inspector.py                          passed=True
ta_archetype      src/trading/market_inspector.py                          passed=True
coding_archetype  src/trading/topology_proposals.py                        passed=True
ta_archetype      src/trading/topology_proposals.py                        passed=True
coding_archetype  src/gui/main_window.py                                   passed=True
gui_archetype     src/gui/main_window.py                                   passed=True
ta_archetype      src/gui/main_window.py                                   passed=True
coding_archetype  src/gui/market_inspector.py                              passed=True
gui_archetype     src/gui/market_inspector.py                              passed=True
ta_archetype      src/gui/market_inspector.py                              passed=True
coding_archetype  src/gui/market_inspector_topologies.py                   passed=True
gui_archetype     src/gui/market_inspector_topologies.py                   passed=True
coding_archetype  src/gui/main_tabs/market_inspector_surface.py            passed=True
ta_archetype      src/gui/main_tabs/market_inspector_surface.py            passed=True
coding_archetype  src/gui/main_tabs/market_inspector_topologies_surface.py passed=True
gui_archetype     src/gui/web/market_inspector.js                          passed=True
gui_archetype     src/gui/web/market_inspector_topologies.js               passed=True
docs_archetype    docs/manual/08-tabs.md                                   passed=True
subjects not passing 0
```

Every tool reported `ok`. `black --check` and `flake8` both exit 0 on the eight
Python files.

### Dependencies

`statsmodels 0.15.0` and `scipy 1.18.1` were already installed and nothing was
added. Neither ships type stubs, so both imports carry
`# type: ignore[import-untyped]`, which is the handling
`src/simulator/nuclear_fleet_controller.py` already uses for `psutil`.

### Safety

Every run used a throwaway home. `~/.acervator/settings.json` is unchanged and
its last write predates this unit:

```
before   f366f42f0e49b4b3468f301b4f2f701669cc13005cfe1ebac7a56988ec376423
after    f366f42f0e49b4b3468f301b4f2f701669cc13005cfe1ebac7a56988ec376423
modified 2026-09-06T00:33:11Z
```

No network call, no credential, no exchange order, and no test run. The running
platform was never started, stopped or queried.

### Size against time

```
source lines produced   900
wall clock              4408 s
seconds per source line 4.90
```

Stage B measured 5.62.

### What the operator sees differently

The Market Inspector draws six zones: ATA-SPM, Opposing Trades and
Multi-Exchange Arbitrage down the left, ATA-SPM Ready to Send above Bot Swarm
Topologies on the right. Every opposing pair in the Opposing Trades zone now
names the test that let it through, the year of daily closes it ran on, and the
number that passed. Two pairs that used to sit at the top of that list —
BTC against DOGE and ETH against PEPE — are gone, because a correlation of
-0.81 is a resemblance and the test for a relationship refuses them. Every card
in Bot Swarm Topologies carries the same line. A sector of five assets that
share a tag and nothing else no longer produces a card at all.
