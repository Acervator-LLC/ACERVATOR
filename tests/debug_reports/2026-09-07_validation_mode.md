# Validation Mode

Issue #117, step 3 of five. The Simulator now snaps each YTD trade to the
historical candle it happened in, reruns the gates on that candle, and puts the
gate row it latched beside the gate row the log recorded, light by light.

The criterion is gate latching and nothing else. No money figure and no trade
tally appears anywhere in the result.

`~/.acervator/settings.json` hashed the same before and after every run.

```
before  2b1946b9560593d7e437805a62e9770a5aed28af0827251bb84c0125862abc7e
after   2b1946b9560593d7e437805a62e9770a5aed28af0827251bb84c0125862abc7e
```

The live Stone Tablets, the gate log and `bot_state.json` were read where they
are and never written. The trade files were written into a throwaway directory
through `ACERVATOR_YTD_TRADES_ROOT`, so no run touched the runtime tree. No
authenticated call, no credential, no order, and the running Acervator process
was never started, attached to or queried.

## Reproduce

Four drivers outside the repository, run under the interpreter's own checks.

```
python -X dev -X faulthandler <driver>
QT_QPA_PLATFORM=offscreen
QTWEBENGINE_CHROMIUM_FLAGS=--disable-gpu --disable-gpu-compositing
ACERVATOR_YTD_TRADES_ROOT=<throwaway directory>
```

The operator's own transactions export was imported into that directory first.
The counts match the import unit's, so the same rows are in play.

```
rows_read       5798
rows_kept       5766
symbols         39
date range      2026-04-12 to 2026-09-07
```

## One entry, snapped and rerun

A real trade, the real candle its timestamp falls in, and the real gate row the
log recorded within five minutes of it.

```
bot          a632ff52   AGLD/USD
trade at     2026-07-27T20:46:50Z
candle at    2026-07-27T20:45:00Z
gate row at  2026-07-27T20:46:18Z
```

The nineteen lights, recorded beside rerun. The last column says which half of
the rerun moves that light: the tablet candle, or the recorded row.

| bank | gate | recorded | rerun | driven by |
| --- | --- | --- | --- | --- |
| S | TGT | passed | passed | record |
| S | INT | passed | passed | record |
| S | BB | passed | passed | tape |
| S | FIRE | passed | passed | record |
| S | TA | passed | passed | record |
| S | LS | not_evaluated | not_evaluated | override |
| S | TRND | passed | passed | record |
| S | HTF | passed | passed | record |
| S | CB | passed | passed | record |
| S | OTD | passed | passed | record |
| F | BB | blocked | blocked | tape |
| F | MID | blocked | blocked | tape |
| F | TA | blocked | blocked | record |
| F | LS | not_evaluated | not_evaluated | override |
| F | TRNQ | not_the_blocker | not_the_blocker | record |
| F | CEIL | not_the_blocker | not_the_blocker | record |
| F | HTF | not_the_blocker | not_the_blocker | record |
| F | CB | not_the_blocker | not_the_blocker | record |
| F | OTD | not_the_blocker | not_the_blocker | record |

Both armed flags agree as well: scrum armed on both sides, fold not armed on
both sides. Nineteen of nineteen.

Every label on both sides comes from one function, so the two sides cannot
disagree about what a gate is called.

`src/trading/gate_vocabulary.py` — the one vocabulary

```python
def gate_light_row(
    scrum_armed: bool,
    fold_armed: bool,
    scrum_blockers: Optional[list] = None,
    fold_blockers: Optional[list] = None,
    landing_strip_side: str = "",
    evaluated: bool = True,
) -> list[dict]:
```

## A disagreement, and a planted one

The first disagreeing row in the run. One light moves, and it is a tape-driven
light.

```
BILL/USD   trade 2026-06-10T21:22:10Z   candle 2026-06-10T21:20:00Z
F/BB   recorded blocked   rerun not_the_blocker   tape
agreed 18 of 19
```

Real disagreements are not enough on their own, because a check nobody has
watched fail is not a check. The same comparison was fed a copy of the AGLD row
with both armed flags inverted and nothing else changed.

```
clean row     19 of 19 agreed, latches identically
altered row    5 of 19 agreed, 14 lights reported, latches identically False
```

Red and green from one instrument on one row. The comparison can fail.

## What it could not verify

The tablets end on 1 August. The trade export runs to 7 September. Validation
says so instead of quietly verifying fewer trades than it was given.

```
38 bots, matched to a recorded gate row on bot id and time window.
3942 of 4904 YTD entries snapped to a candle; 962 could not be.
after_last_candle: 905
inside_gap: 57
uncovered span 2026-08-01T18:52:58Z to 2026-09-07T21:46:48Z; the newest
  candle is 2026-08-01T18:35:00Z
62 of 227 reruns latched every gate identically.
3572 of 4313 gate lights agreed.
60 of 60 recorded readings were reproduced exactly from the tablet.
45 of them came from a window 50 candles (250 minutes) behind the trade's
  own candle.
```

Thirteen live bots trade a pair the export does not name, so they carry no
trade file and none of their trades is counted above. That is reported as a
count, not hidden.

```
validated     25 bots
no_ytd_file   13 bots
```

## The two ways in

Import Live Fleet reads the bot_state load and nothing else. Generate From YTD
scans the trade files and creates one new bot per pair that was traded.

```
Import Live Fleet    38 bots, matched on bot id and time window
Generate From YTD    39 bots, matched on exchange, symbol and time window
```

A generated bot is a new bot with a new id and never wrote a gate row, so it is
matched on the pair and the time window. No generated bot is given a live bot's
id, and the gate log is never re-keyed.

The two counts differ by one and that is a fact about the two sources. The
export names 39 traded pairs; the live fleet holds 38 bots. Neither path
invented a bot to make the numbers meet.

```
Generate From YTD, first row   ADA/USD@coinbase  ADA/USD  6 trades  no target
Import Live Fleet, first row   ff6a37a3  ADA/USDC  0 trades  $25.00
```

The pair comes from the export's own asset and price-currency columns, so a
future export in another quote currency reads correctly.

`src/exchange/ytd_csv_import.py` — the pair

```python
def _symbol_of(cell: CellReader, row_number: int) -> str:
    """Return ``ASSET/CURRENCY`` from the row's asset and price currency."""
    asset = cell(COL_ASSET).strip().upper()
    quote = cell(COL_PRICE_CURRENCY).strip().upper()
```

## The exchange prompt

One chooser serves both buttons. It was driven three ways.

```
one exchange active           options ['coinbase']            prompt False, chosen coinbase
two active, none picked       options ['coinbase','kraken']   prompt True,  chosen ''
two active, one picked        options ['coinbase','kraken']   prompt False, chosen kraken
```

**The operator's tree holds exactly one exchange**, so the prompt cannot fire on
his data today. The second and third rows drive the shipped function on two
names. No fleet, bot or venue was invented to make the prompt appear.

## The send rule

Four read paths, nine venue calls asked of each, all thirty-six refused.

```
FleetSource      9 of 9 refused
GateLogSource    9 of 9 refused
YtdTradeSource   9 of 9 refused
TabletSource     9 of 9 refused
```

`src/simulator/fleet_source.py` — the refusal

```python
    def __getattr__(self, name: str):
        """Refuse every name outside ``READ_NAMES``."""
        raise SendRefused(
            f"FleetSource answers {READ_NAMES} and cannot {name!r}. "
            "The Simulator receives and asks; it sends nothing."
        )
```

No live stateful class is imported. The gate chains and the Bollinger reading
are pure functions over a candle list, and the bot record is a frozen dataclass
forked from the stored config, never a `ScrummingBot`.

## Calibrating the comparison before trusting it

A count of disagreements is a claim about the instrument until the instrument
is proved. Every recorded row was fed back through the shipped gate chains with
every field taken from the record and nothing from the tape.

```
armed flags reproduced   228 of 228
lights reproduced        4322 of 4332
```

The ten that did not come from one row, and that row was a program error. It is
corrected below. The context construction and the label mapping are therefore
sound, and what moves in the real run is the tape.

## Error 1 — a pre-tick row was compared as if it held a reading

**The error.** One row disagreed on ten lights while every field came from the
record, which cannot happen if the machinery is sound.

```
GROVE/USD   2026-07-28T14:23:05Z
recorded scrum blockers   ['pre-tick']
recorded fold blockers    ['pre-tick']
control scrum blockers    ['delta≤0', 'TA-not-bullish(dir=)',
                           'scrum_ok=False(bb_pos=0.00)', ...]
```

**The cause.** The gate log also holds rows written before a tick has computed
anything. Both fixtures are empty and the only blocker is the word `pre-tick`,
which maps to no gate label. Rerunning an empty fixture blocks every gate, so
the row reported ten false disagreements.

**The correction.** A row with no fixture is refused rather than compared, and
the refusals are counted.

```python
def is_rerunnable(row: Any) -> bool:
    """True while ``row`` carries both fixtures ``rerun_context`` reads.

    ``gate.log`` also holds pre-tick rows whose fixtures are empty and whose
    only blocker maps to no gate label.
    """
    return bool(row.scrum_fixture) and bool(row.fold_fixture)
```

**The rerun.** One row refused, and the ten false disagreements are gone.

```
before   228 rows compared, 4332 lights
after    227 rows compared, 4313 lights, 1 row refused for holding no fixture
```

## Error 2 — Generate From YTD reached no gate row

**The error.** The generated fleet snapped 4,378 trades and compared nothing.

```
rows_compared 0
"No YTD entry reached both a candle and a recorded gate row."
```

**The cause.** A recorded row was looked up by bot id. A generated bot is a new
bot with a new id and never wrote a gate row, so no id could ever match.

**The correction.** A generated bot is matched on its exchange, its symbol and
the time window. A live bot trades one pair, so the pair carries the
correspondence the id cannot. No id is copied, derived or rewritten in either
direction.

```python
        near = (
            rows_by_bot.get(bot.bot_id)
            if bot.origin == LIVE_ORIGIN
            else rows_by_pair.get((bot.exchange_id, bot.symbol))
        )
```

**The rerun.**

```
before   0 rows compared
after    234 rows compared, 63 latching identically, 3685 of 4446 lights agreed
```

## Error 3 — the reader saw an empty page

**The error.** The React side answered nothing for all eleven values while the
page had drawn.

```
page_ready False
before null
after  null
```

**The cause.** The driver pumped the event queue in a tight loop. That never
gives the browser real time, so the page had not finished loading when the
first read went out. The defect was in the driver, not in the tab.

**The correction.** The driver waits on the event loop properly.

```
QTest.qWait(50) in a bounded loop, until page_ready
```

**The rerun.** The page reports every part it draws, including both new
buttons and all four validation parts, with no faults.

```
page_ready True
faults []
parts  sim-import-live-fleet, sim-generate-from-ytd, sim-validation-title,
       sim-validation-lines, sim-validation-table, sim-validation-lights
```

## What the run found, and how far it was chased

Sixty-two of 227 reruns latched every gate identically. Every disagreement
traces to the Bollinger reading, and the tablet is not at fault.

The tablet's prices are right. Measured over one asset across every recorded
row, the price the log stored sits inside the tablet candle covering that same
moment.

```
BILL/USD   gate rows 10086
prices inside their own candle   9869
prices outside                    169
worst miss                      0.24%
```

The recorded reading is internally consistent, so it is the number the live
code produced.

```
bb_above_upper_dt agrees with bb_pos and the threshold   161657 of 161657
bb_below_lower_dt agrees                                 161656 of 161657
```

The recorded reading is reproduced from the tablet exactly, but from an older
window. Four searches were run before this was accepted: a window offset sweep,
a rollup sweep across seven timeframes, a fixture self-consistency check, and a
wide search across the whole tape.

```
window offsets -4..+4         no offset improves the fit
rollups 5m,15m,30m,1h,2h,4h,1d   no timeframe improves the fit
wide search over the tape     141 of 141 rows reproduced exactly
offset found                  -50 candles (117 rows), -51 (23), -84 (1)
```

Fifty five-minute candles is four hours and ten minutes. The price in each of
those rows is current and the candle-derived values are fifty bars behind.

**This is a reading about the live bot's own candle window, taken from the
operator's own logs.** No live trading file was changed. Validation now reports
the offset it measures on every run, so the operator sees the cause beside the
count.

## Both builds draw the same result

Both tabs were built, both had Import Live Fleet pressed, and eleven values
were read off the drawn window and the drawn page.

```
matched 11 of 11
differed 0
```

| value | read |
| --- | --- |
| the two fleet button words | Import Live Fleet, Generate From YTD |
| fleet row count | 38 |
| every fleet row | ten cells each |
| validation title and its ran flag | Validation, true |
| validation prompt | empty, one exchange active |
| the eight report lines | identical text |
| validation table titles | seven |
| every validation row | seven cells each |
| light table titles | five |
| all nineteen light rows | five cells each |

Before any press, both sides say the same thing rather than filling themselves.

```
ran      false
lines    "No validation run yet. Import Live Fleet or Generate From YTD."
rows     0
```

## The archetypes

Every file this unit touched, with the archetype that owns it.

```
src/simulator/validation.py                  coding passed=True exit=0 high=0
src/simulator/validation.py                  ta     passed=True exit=0 high=0
src/simulator/fleet_source.py                coding passed=True exit=0 high=0
src/simulator/fleet_source.py                ta     passed=True exit=0 high=0
src/simulator/gate_log_source.py             coding passed=True exit=0 high=0
src/simulator/gate_log_source.py             ta     passed=True exit=0 high=0
src/gui/main_tabs/simulator_tab_surface.py   coding passed=True exit=0 high=0
src/gui/main_tabs/simulator_tab_surface.py   ta     passed=True exit=0 high=0
src/gui/main_tabs/simulator_tab_surface.py   gui    passed=True exit=0 high=0
src/gui/simulator_tab.py                     coding passed=True exit=0 high=0
src/gui/simulator_tab.py                     gui    passed=True exit=0 high=0
src/gui/simulator_tab.py                     ta     passed=True exit=0 high=0
src/gui/react_simulator_tab.py               coding passed=True exit=0 high=0
src/gui/react_simulator_tab.py               gui    passed=True exit=0 high=0
src/gui/react_simulator_tab.py               ta     passed=True exit=0 high=0
src/gui/web/simulator_tab.js                 gui    passed=True exit=0 high=0
docs/manual/08-tabs.md                       docs   passed=True exit=0 high=0
docs/manual/08-tabs/simulator.md             docs   passed=True exit=0 high=0
tests/debug_reports/2026-09-07_validation_mode.md
                                             docs   passed=True exit=0 high=0
```

The fixture control was run before any verdict above was trusted.

```
harness_fixtures/coding_archetype/known_good.py   exit 0
harness_fixtures/coding_archetype/known_bad.py    exit 1
```

## The tests that name what changed

```
tests/test_canonical_tab_order.py
tests/test_desktop_panel_host.py
tests/test_c51_indicator_panel_no_fabrication.py
tests/test_conversion_state_pairs_on_the_bridge.py
tests/test_react_empty_tabs_render.py
tests/test_extract_product_manual_keeps_additions.py
tests/test_version_sweep_reports_uninspected_checks.py
tests/test_island_machinery_stays_retired.py

1186 passed
```

## The manual

Both pages take additions only.

```
docs/manual/08-tabs.md              23 added, 0 removed
docs/manual/08-tabs/simulator.md   100 added, 0 removed
```

The conversion table's rows for `src/gui/simulator_tab.py` and
`src/gui/react_simulator_tab.py` already state what this unit leaves true, so
neither row changes. The new modules under `src/simulator/` are not screens and
belong in no row of that table.

## What is not done

Back Test and Portfolio Battery are later units. A run reads the whole gate log
and takes about fourteen seconds, and it runs on the interface thread, so the
window is still while it works.
