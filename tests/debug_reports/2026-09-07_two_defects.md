# The two defects held for after ATA-SPM

Issue #407 held two defects for completion after ATA-SPM. Both are closed. Both
were in the six-zone pattern the Market Inspector draws.

Renders:

```
docs/audits/2026-09-07_units/defects_closed_qt.png
docs/audits/2026-09-07_units/defects_closed_react.png
docs/audits/2026-09-07_units/defects_closed_electron.png
```

Every run used a throwaway home. `~/.acervator/settings.json` hashed the same
before and after:

```
before  f366f42f0e49b4b3468f301b4f2f701669cc13005cfe1ebac7a56988ec376423
after   f366f42f0e49b4b3468f301b4f2f701669cc13005cfe1ebac7a56988ec376423
```

## Edits

`src/trading/pair_selection.py` — `MethodResult` no longer stores the statistic
line. It stored the p-value twice: once as the number `p_value`, and once
already written into the string `statistic_text`. `statistic_text` is now a
property that formats the numbers the test returned, reading the same
`p_value` that `gate_text` reads. The numbers the tests hand back are held as
their own fields: `trace` and `critical` from
`statsmodels.tsa.vector_ar.vecm.coint_johansen`, `pair_count` for a cluster of
correlated assets, and `scrum_distance_pct`, `fold_distance_pct` and `deep_pct`
for a band distance. `cointegration_test`, `correlation_test` and
`band_distance_result` pass those numbers instead of a written line.
`CLUSTER_STATISTIC_FORMAT` moved here, so all four statistic formats sit beside
the one property that uses them.

`src/trading/topology_proposals.py` — `_cluster_correlation` passes
`pair_count` in place of a written statistic line, and no longer holds its own
copy of `CLUSTER_STATISTIC_FORMAT`.

`src/gui/main_tabs/market_inspector_surface.py` — `zone_view` drops the method
line and the hint while an entry is open. Both repeat what the four expanded
lines say, and dropping them gives every zone's open entry the same height
whatever buttons it carries. `stepper_skin` publishes
`push_button_height_px`, so an entry's buttons take the same box in every host.

`src/gui/main_tabs/market_inspector_topologies_surface.py` — `proposal_actions`
puts Preview and Dismiss inside the entry, the way the Ready to Send zone puts
Approve and Decline there. `PANE_MARGINS` is zero, because the zone group box
already insets the pane.

`src/gui/market_inspector.py` — `ProposalStepper.show_view` reads the view's own
`hint` rather than deciding from the entry count.

`src/gui/market_inspector_topologies.py` — the pane holds one row above the
stepper and nothing below it. The Preview and Dismiss buttons and the
auto-refresh line came out from under the stepper; the buttons are now the
entry's own action row, handled by `_on_action`, and the line sits beside
Refresh.

`src/gui/web/market_inspector.js` — `EntryAction` reads its padding, weight and
height from the stepper skin and presses through the stepper's own handler, so
the shared stepper works in the proposals pane as well as in the screen. The
hint is drawn from the view's `hint`.

`src/gui/web/market_inspector_topologies.js` — `Pane` holds the top row and the
shared stepper, nothing else. The 180 lines that drew a second card list —
`CardButtons`, `ProposalCard`, `screenChild`, `Scroll`, `ListGroup` and
`shownName` — are gone, along with their four export rows. Nothing outside the
file named them.

## Errors detected

### 1 The expansion stated two different numbers for one statistic

The card the operator saw:

```
Result: p=0.0100 · trace 20.1>15.5
Why it is here: p 0.0000 is at or below the 0.05 required.
```

`Result` prints `MethodResult.statistic_text`. `Why it is here` prints
`MethodResult.gate_text`. Before this change `statistic_text` was a stored
string written once, at the moment the test returned, and `gate_text` was a
property reading the number `p_value`. Two copies of one statistic, and nothing
held them together.

**`p=0.0100` was the wrong number.** `p_value` is the number every decision in
the program is made on: `cointegration_test` sets `passed` from it,
`MarketInspector._find_opposing_pairs` ranks pairs by it, and
`score_from_p_value` scores a card from it. `0.0100` existed only inside the
written string, and nothing else in the program agreed with it.

Driven under the debugger against the real tests, 200 pairs of daily closes
through `statsmodels.tsa.stattools.coint` and `coint_johansen`:

```
PYTHONWARNINGS=error python -X dev -X faulthandler twodefects_screen_repro.py
signals [('ETH', 'ENTRY_LONG_MEDIUM', 0.6, 'long'), ('LINK', 'ENTRY_SHORT_MEDIUM', 0.6, 'short')]
cointegration_test: 76 passing verdicts, 0 disagreed
CONTROL result Result: p=0.0100 · trace 20.1>15.5
CONTROL reason Why it is here: p 0.0000 is at or below the 0.05 required.
CONTROL disagreed: True
EXIT=0
```

The 76 verdicts are the measurement and the control is the positive half: a
`method` payload carrying two written lines reaches the screen unchecked, and
`market_inspector_surface.method_detail_rows` prints both. That is how two
numbers for one statistic could exist at all.

After the change, one number reaches both lines, and every statistic line is
byte-identical to the stored form it replaced:

```
PYTHONIOENCODING=utf-8 PYTHONWARNINGS=error python -X dev -X faulthandler twodefects_one_number_check.py
cointegration  statistic_text 'p=0.0000 · trace 155.9>15.5' matches stored form: True
correlation    statistic_text 'r=+0.878 · p=0.0000' matches stored form: True
band_distance  statistic_text '-14.2% / +11.5% vs 10.0%' matches stored form: True
refused        statistic_text '' matches stored form: True
cluster        statistic_text 'r=+0.901 over 3 pairs · p≤0.0000' matches stored form: True

cointegration  one p reaches both lines: True
correlation    one p reaches both lines: True
cluster        one p reaches both lines: True

CONTROL p_value 0.0123 result p=0.0123 · trace 155.9>15.5
CONTROL p_value 0.0123 reason p 0.0123 is at or below the 0.05 required.
CONTROL both lines moved: True
CONTROL differs from the unmoved verdict: True
MethodResult accepts a typed statistic line: False
EXIT=0
```

The control moves `p_value` to 0.0123 and both lines follow it, so the check
had something to report. The last line is the structural half: `statistic_text`
is no longer a field, so no caller can hand the screen a second copy.

### 2 The Bot Swarm Topologies card clipped its own expansion

Read off the running page, before the change, under
`ACERVATOR_VARIANT=react`:

```
opposing_trades entry [16, 436, 735, 177] scrolled 0
    86 True Test: Cointegration — Engle-Granger + Johansen
   105 True Window: 365 daily closes
   125 True Result: p=0.0070 · trace 140.1>15.5
   144 True Why it is here: p 0.0070 is at or below the 0.05 required.
topologies entry [789, 436, 735, 177] scrolled 36
   126 True Test: Cointegration — Engle-Granger + Johansen
   146 True Window: 365 daily closes
   165 True Result: p=0.0070 · trace 140.1>15.5
   185 False Why it is here: p 0.0070 is at or below the 0.05 required.
```

Both zones had the same entry box, 735 by 177. The topologies entry carried 36
more pixels of content than fitted, because Preview and Dismiss sat under the
stepper and the entry started 40 pixels lower. Its last line ended below the
box.

After the change, both zones read the same box and nothing overflows:

```
opposing_trades entry [16, 436, 735, 177] scrolled 0
    66 True Test: Cointegration — Engle-Granger + Johansen
    86 True Window: 365 daily closes
   105 True Result: p=0.0070 · trace 140.1>15.5
   125 True Why it is here: p 0.0070 is at or below the 0.05 required.
topologies entry [789, 436, 735, 177] scrolled 0
   107 True Test: Cointegration — Engle-Granger + Johansen
   126 True Window: 365 daily closes
   146 True Result: p=0.0070 · trace 140.1>15.5
   165 True Why it is here: p 0.0070 is at or below the 0.05 required.
```

### 3 The Electron shell would not start under a shared profile

```
COMMAND: electron.exe --remote-debugging-port=9223 <repo>/desktop
alive: False
EXIT: 2147483651
STDOUT:
STDERR:
```

`2147483651` is `0x80000003`. The shell wrote nothing on either channel. It
starts when it is given its own profile directory:

```
COMMAND: electron.exe --enable-logging=stderr --log-level=0 --user-data-dir=<throwaway>/electron_data
         --no-sandbox --disable-gpu --remote-debugging-port=9226 <repo>/desktop
alive: True
STDERR:
DevTools listening on ws://127.0.0.1:9226/devtools/browser/80b5aec1-c684-4b34-b60e-ee96b9b6e33b
```

`ELECTRON_RUN_AS_NODE=1` is set in this shell's environment. With it set, the
shell reports `electron.exe: bad option: --remote-debugging-port=9222` and
exits 9. It has to be removed from the child's environment.

### 4 An exit code read after a command substitution

The first fixture control run reported every archetype green:

```
gui_archetype known_bad_widget.py=0
```

`echo "gui $(basename $f)=$?"` expands `basename` first, so `$?` carried
`basename`'s status, not the archetype's. Read on its own line the same file
answers:

```
gui_archetype harness_fixtures/gui_archetype/known_bad_widget.py exit=1
```

## Resolution

### Which p was wrong, and why

`Result: p=0.0100`. The gate line's `p 0.0000` was the number the test
returned, because `p_value` is the field `passed`, the pair ranking and the
card score all read. `0.0100` lived only in a written string that no decision
consulted.

The repair is not the two lines agreeing. `MethodResult` now holds the p-value
once, and both lines format that one field. A caller can no longer supply a
statistic line at all, so a second copy cannot be introduced.

### One implementation, or two

**One.** In Qt both zones are drawn by `ProposalStepper` in
`src/gui/market_inspector.py`. In React and in the Electron shell both are
drawn by `ZoneStepper` in `src/gui/web/market_inspector.js`, which
`market_inspector_topologies.js` takes from the screen. Both hosts build their
lines from `zone_view` in `market_inspector_surface.py`.

That was already half true before this unit, and the half that was not is what
made two results out of one pattern. The Qt pane drew one row above the stepper
and two more below it; the React pane drew a whole second card list of its own,
180 lines that nothing else named. Both are gone. Each zone is now a group box,
one row, and the shared stepper.

### The three hosts

Read off the real objects: Qt off the widgets, React and the Electron shell off
the page.

```
                 Qt          React       Electron
opposing  entry  220 tall    735x177     735x177
topologies entry 220 tall    735x177     735x176
opposing  lines  4, all in   4, all in   4, all in
topologies lines 4, all in   4, all in   4, all in
opposing  buttons 0          0           0
topologies buttons 2         2           2
```

102 dimensions compared, 100 exact. The two that differ are the Electron
shell's topologies stepper height, 204 against React's 205, and its entry
height, 176 against 177 — one pixel each, from where the right pane's flex
split lands.

Every host prints `p 0.0070` on both lines of both cards.

### The gate

Fixture controls first, each exit code read on its own line:

```
coding_archetype known_good exit=0     known_bad exit=1
docs_archetype   known_good exit=0     known_bad exit=1
gui_archetype    known_good_widget.py exit=0   known_bad_widget.py exit=1
gui_archetype    known_good_screen.js exit=0   known_bad_screen.js exit=1
ta_archetype     known_good_ta001.py  exit=0   known_bad_ta001.py  exit=1
```

Every changed file, by its owning archetype:

```
coding_archetype src/trading/pair_selection.py                              passed
ta_archetype     src/trading/pair_selection.py                              passed
coding_archetype src/trading/topology_proposals.py                          passed
ta_archetype     src/trading/topology_proposals.py                          passed
coding_archetype src/gui/main_tabs/market_inspector_surface.py              passed
ta_archetype     src/gui/main_tabs/market_inspector_surface.py              passed
coding_archetype src/gui/main_tabs/market_inspector_topologies_surface.py   passed
ta_archetype     src/gui/main_tabs/market_inspector_topologies_surface.py   passed
coding_archetype src/gui/market_inspector.py                                passed
gui_archetype    src/gui/market_inspector.py                                passed
ta_archetype     src/gui/market_inspector.py                                passed
coding_archetype src/gui/market_inspector_topologies.py                     passed
gui_archetype    src/gui/market_inspector_topologies.py                     passed
ta_archetype     src/gui/market_inspector_topologies.py                     passed
gui_archetype    src/gui/web/market_inspector.js                            passed
gui_archetype    src/gui/web/market_inspector_topologies.js                 passed
```

`ta_archetype` on `src/trading/pair_selection.py` reports `passed True`,
`scanned True`, tools `ta-quant ok, ta-chart ok, ruff ok`, no findings.

`black --check` leaves six files unchanged. `flake8` exits 0.

### What the operator sees differently

The Opposing Trades card and the Bot Swarm Topologies card now state one number
for one statistic, and both show all four lines with nothing cut, in the Qt
build, the React build and the Electron shell.

### Time

3520 seconds of wall clock. 357 source lines changed under `src/`, 106 added and
251 removed, counted from the branch diff. 9.9 seconds per source line.
