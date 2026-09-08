# ATA-SMP Indicator Voting Panel and gate chain

The module files on disk carry the spelling `ata_spm` today. This page cites
those filenames as they stand. The feature is ATA-SMP.

The screens:

```
docs/audits/2026-09-07_units/ata_ivp_qt.png
docs/audits/2026-09-07_units/ata_ivp_react.png
docs/audits/2026-09-07_units/ata_ivp_electron.png
docs/audits/2026-09-07_units/ata_ivp_expanded_react.png
```

Every run used a throwaway home. `~/.acervator/settings.json` hashed the same
before and after:

```
before  f366f42f0e49b4b3468f301b4f2f701669cc13005cfe1ebac7a56988ec376423
after   f366f42f0e49b4b3468f301b4f2f701669cc13005cfe1ebac7a56988ec376423
```

## Edits

`src/trading/ata_gate_scan.py` is new. It fills a `GateContext` from one
market's candles and its `VotingSummary`, and hands that context to the chains
`build_scrumming_scrum_chain` and `build_scrumming_fold_chain` build. It reads
no bot, no exchange and no event bus. `scan_gates` answers a `GateScan` of
`GateReading` rows, one per gate, each carrying a state and its evidence.

The market values the gates read are computed from price and settings:
`detect_thresholds` for the band detect levels, `circuit_breaker_sides` for the
single-candle range, `ramp_mode` for the search, track and fire walk,
`htf_bias` for the higher-timeframe consensus, and `confidence_floor` for the
floor direction is judged at. `hypothetical_reading` calls
`minimum_opposing_trade_distance_pct` for the two opposing-trade-distance rows.
`composite_net` weighs the higher timeframes for the panel's Comp column.

`src/trading/ata_spm.py` — `AssetVote` now carries the three vote counts and
its own `VotingSummary`, and `AssetVote.panel_row` answers the row the panel
reads. `panel_rows_for` collects every timeframe one asset voted on.
`proximity_of` runs `detect_bb_proximity`, which is the Landing Strip formula.
`pull` now carries the gate scan, the panel rows, the landing strip side and
the opposing trade distance. `SectorBoard.compute` and `SectorBoard.take` split
the scan into a part that writes nothing and a part that writes.

`src/gui/main_tabs/market_inspector_surface.py` — `voting_panel` describes the
panel as rows of cells, and `gate_rows` describes the gate result. Every cell's
text, colour and tint comes from `indicator_panel_surface`, which is the same
description the Trading tab's panel is drawn from.

`src/gui/market_inspector.py` — `_VotingPanel` draws the panel from that
description, and `ProposalStepper` places one per called asset with that
asset's gate lines under it. `_on_scan_now` starts a worker thread,
`_compute_scan` runs the phases on it, and `_take_scan` writes the answer back
through the `scanFinished` signal.

`src/gui/web/market_inspector.js` — `VotingPanel`, `PanelRow`, `PanelCell` and
`PanelLine` draw the same description on the page. `ZoneStepper` places them
inside the open entry.

`src/gui/react_market_inspector_tab.py` — Scan Now on the page now runs the
inherited `_on_scan_now`, so both builds use one scan path and one thread rule.

## Errors detected

### 1 The TA archetype refused four comparisons

`ta_archetype` reported `TA004` seven times on the new module. The rule tracks
which local names came from a division and refuses a comparison that crosses
that line.

```
ta-quant:TA004 units mismatch: 'move_pct' (dimensionless) against 'limit' (absolute)
ta-quant:TA004 units mismatch: 'distance' (absolute) against 'detect_frac * span'
ta-quant:TA004 units mismatch: 'trend_strength' (absolute) against 'TREND_MIN_BULL_SHARE'
```

### 2 The GUI archetype refused absolute placement

The first `_VotingPanel` placed each cell with `setGeometry`.

```
gui-static:GUI003 setGeometry used without any QLayout — the widget will not
respond to resize / high-DPI / accessibility
```

### 3 A tint alpha two hosts read differently

The cell tint was first written as `rgba(r, g, b, 0.047)`. Qt reads a bare
decimal alpha in a style sheet as a byte, and the page reads it as a fraction,
so the same declaration would have painted two different colours.

### 4 A fixture control that never ran

The first control run reported the TA archetype refusing its own known-good
file.

```
[archetype] not green: target was never scanned:
  harness_fixtures/ta_archetype/known_good_ta004.py - an empty report is not a clean one
```

No such file is on disk. The archetype ships known-good fixtures for TA001,
TA002, TA003, TA010 and TA011 only. A gate that never started reads the same as
one that failed.

## Resolution

### 1 Compare like with like

`circuit_breaker_sides` now compares `move_ratio` against `limit_ratio`, both
divided. `ramp_step` compares `travel_frac` and `edge_gap_frac` against
`detect_frac`, `retreat_frac` and `fire_frac`, all divided. `retreat_frac` is
`detect_frac / RETREAT_DIVISOR`. `build_context` divides
`bull_candle_count(candles)` by `TREND_CANDLES` and compares that share against
`TREND_MIN_BULL_SHARE`. Every comparison answers what it answered before; only
the form changed. `ta_archetype` reports `passed` on the file.

### 2 A layout, not a placement

`_VotingPanel.show_panel` builds one row layout per panel row and gives each
label a fixed size. The page draws the same rows as flex rows of fixed-width
cells. Both hosts read the widths and the row heights out of one description,
and both measured 592 by 204 for the panel and 592 by 18 for its title cell.

### 3 A percentage alpha

`PANEL_CELL_STYLE_FORMAT` now writes the alpha as a percentage. Qt and the page
both read a percentage the same way.

### 4 The control pair that exists

The controls were re-run against fixtures that are on disk, each exit code read
on its own line.

```
coding_archetype known_good exit=0            known_bad exit=1
docs_archetype   known_good exit=0            known_bad exit=1
gui_archetype    known_good_widget.py exit=0  known_bad_widget.py exit=1
gui_archetype    known_good_screen.js exit=0  known_bad_screen.js exit=1
ta_archetype     known_good_ta003.py  exit=0  known_bad_ta004.py  exit=1
```

`tool_availability` on the TA run reads `ta-quant ok`, `ta-chart ok`,
`ruff ok`.

### Which gates ran

One scan of the `payments` sector, two assets, four timeframes each, eight
reversal calls. Read off the real `GateScan` object for BCH on 5m:

```
16 of 22 gate(s) ran · 9 latched · 7 blocked · 6 did not run
```

Latched:

```
scrum  midline_scrum  target_fires  bb_proximity_scrum  circuit_breaker_scrum
       htf_defer_scrum  zscore_extremity
fold   circuit_breaker_fold  htf_defer_fold  zscore_extremity
```

Blocked, each with the engine's own message:

```
scrum ta_bullish              TA-not-bullish(dir=BEARISH)
scrum trend_hold              trend_hold(100%)
scrum adx_trend_suppression   adx_trend_suppression(ADX=60.0≥30.0;
                              strong-trend MR suppression)
scrum efficiency_ratio_regime efficiency_ratio_regime(ER=0.971≥0.70;
                              strong-trend MR suppression)
fold  ta_bearish              TA-not-bearish(dir=BEARISH)
fold  midline_fold            fold_ok_midline=False(bb_pos=0.88)
fold  bb_proximity_fold       BB-above-lower-detect(bb_pos=0.88>0.12)
```

### The six that did not run, and what the post says instead

Four are named, marked as not run, and carry the reason. Nothing implies a
latch.

```
scrum delta_positive  did not run  a scan holds nothing, and no surplus exists to test
scrum interval        did not run  the same surplus, and a scan holds none of it
fold  tranches_queued did not run  a scan has no fold queue
fold  smart_ceiling   did not run  a scan holds nothing, and any ceiling test passes
```

The two opposing-trade-distance gates publish a price and no verdict.

```
scrum hysteresis_scrum  hypothetical  entry at $94.49648009 would need
                                      $96.00842377, 1.60% away; no gate ran
fold  hysteresis_fold   hypothetical  entry at $94.49648009 would need
                                      $92.98453641, 1.60% away; no gate ran
```

The distance is what `minimum_opposing_trade_distance_pct` answers for the
scrumming interval plus the trading fee. At the instant of the scan the pivot
is the scanned price, so both sides refuse; the number is the reading and the
verdict is not.

### The stricter floor is kept

`confidence_floor` takes two of the three favours the tick sums. The third arms
only when a delta is available and signed, and a scan has no delta, so the
floor a scan reads stays higher. Nothing was added to compensate for that. It
is what puts `ta_bearish` in the blocked list above on a chart whose consensus
already reads bearish: the vote's confidence sits under the higher floor.

### The live path is unchanged

No file the running bots execute was edited. Measured against the branch point:

```
git diff --stat purge-non-canon-tests -- src/trading/scrumming_bot.py
  src/trading/gate_chain.py src/trading/scrumming/ src/trading/phantom_balance.py
  src/trading/otd_math.py src/trading/container/config.py src/trading/ta_engine.py
  src/trading/indicators/
(no output)
```

The scan is a third construction of `GateContext` in a new caller. The tick in
`ScrummingBot` builds the only two under `src/` and neither it nor the chain
gained a line. The 38 live bots run the same bytes they ran before.

### The thread

`Scan Now` starts a thread named `ata-smp-scan`. `SectorBoard.compute` writes
nothing and runs there; `SectorBoard.take` writes the answer and runs on the
window-drawing thread, reached through the `scanFinished` signal. Measured from
the log line each side writes:

```
ATA-SPM scan on thread ata-smp-scan: compute
ATA-SPM scan on thread MainThread: draw
```

The Electron shell runs the phases in the Python bridge process, which the
shell spawns; the browser thread that draws the page runs none of them.

### The three hosts

Read off the real objects: Qt off the widgets, React and the Electron shell off
the page.

```
                       Qt        React     Electron
panel groups           8         8         8
panels                 8         8         8
cells                  688       688       688
gate lines             192       192       192
other expanded lines   78        78        78
panel width            592       592       592
panel height           204       204       204
title cell width       592       592       592
title cell height      18        18        18
```

The text each host drew:

```
title      BCH 5m   ▲ 16  ▼ 20  ─ 12
header A   TF BB VTX MACD SRsi Ichi Vol Net Comp Conf
header B   KER RSI
row 5m     ▼ 32%  ▲ 98%  ▲ 60%  ▼ 50%  ▼ 65%  ▲ 45%  -0.15  -0.15
           ░░░░░░░░░░ 1%
gate 1     Gate chain BCH 5m: 16 of 22 gate(s) ran · 9 latched · 7 blocked
           · 6 did not run
gate 2     Gate chain distance: opposing trade distance 1.60% · landing strip none
gate 3     Gate chain scrum delta_positive: did not run a scan holds nothing,
           and no surplus exists to test
```

39 readings compared across the three hosts. All 39 the same.

### The debugger

Every run above ran under `python -X dev -X faulthandler` with
`PYTHONWARNINGS=error`. No warning and no traceback was printed on any of them.
The import of the new module under the debugger:

```
COMMAND: python -X dev -X faulthandler -m pdb -c continue -m src.trading.ata_gate_scan
exit=0
The program finished and will be restarted
> src/trading/ata_gate_scan.py(1)<module>()
-> """ata_gate_scan.py -- the live trade gates run over scanned price data.
(Pdb)
```

`main.py` was not started. The brief forbids a second instance of the trading
application, and `main.py` is that application. The runtime proof is the real
tab widgets of both builds and the real Electron shell over the bridge, driven
under the same debugger flags.

### The gate

Every changed file, by its owning archetype, each exit code read on its own
line:

```
coding_archetype src/trading/ata_gate_scan.py                     passed
ta_archetype     src/trading/ata_gate_scan.py                     passed
coding_archetype src/trading/ata_spm.py                           passed
ta_archetype     src/trading/ata_spm.py                           passed
coding_archetype src/gui/main_tabs/market_inspector_surface.py    passed
ta_archetype     src/gui/main_tabs/market_inspector_surface.py    passed
coding_archetype src/gui/market_inspector.py                      passed
ta_archetype     src/gui/market_inspector.py                      passed
gui_archetype    src/gui/market_inspector.py                      passed
coding_archetype src/gui/react_market_inspector_tab.py            passed
ta_archetype     src/gui/react_market_inspector_tab.py            passed
gui_archetype    src/gui/react_market_inspector_tab.py            passed
gui_archetype    src/gui/web/market_inspector.js                  passed
docs_archetype   docs/manual/08-tabs.md                           passed
```

`black` reformatted three files and then reported nothing to change. `flake8`
exits 0 on all five.

### Size against time

```
source lines produced   1355   722 new, 633 changed
wall clock              3961 s
seconds per source line 2.92
```

### What the operator sees differently

Expanding a scanned sector on the Market Inspector now draws the voting panel
for every asset the scan called, and under each one the trade gate result for
that asset: which gates latched, which refused and why, and which four could
not run because a scan holds nothing.
