# Tick messages: tightened, standardized, and made true to their source

The Activity Log prints whatever the trading engine writes to `bot.log`. This
unit rewrote those messages. The three-column screen layout is deferred: the
operator runs a build that predates the screen work, so only the message text
reaches him today.

`~/.acervator/settings.json` hashed the same before and after:

```
before  f366f42f0e49b4b3468f301b4f2f701669cc13005cfe1ebac7a56988ec376423
after   f366f42f0e49b4b3468f301b4f2f701669cc13005cfe1ebac7a56988ec376423
```

`bot_state.json` was read once and never written: `f621999406383330bb813e644
753744505481b6c37c65c608397e0a5091fe28d`. No authenticated call, no credential,
no network read, and the running Acervator process was never touched. Every
input is a value read back from `~/.acervator_logs/`, or a recorded tape served
by `TabletBackend`.

## Which messages these are

`~/.acervator_logs/trade/diagnostics.log` holds every `bot.log` line the live
fleet wrote. Counting them names the work:

```
8,136 records, category bot_log

1885  Delta                      533  RISK GATE SNAPSHOT [SCRUM]
1885  TA Vote                    439  RISK GATE SNAPSHOT [FOLD]
1529  HOLD FOLD                  420  BULLSEYE UPPER
 840  READ                       321  BULLSEYE LOWER
 163  HOLD SCRUM                  64  BB PRIORITY SKEW
  18  FOLD_DIAG_*                 12  MEM-196 DEEP-FOLD OVERRIDE
  20  HOLD w/                      2  AT TARGET (MEM-258)
```

Nine shapes carry 99.7% of what he reads. Those are the ones rewritten.

## Reproduce

Two runs, and neither needs the live application.

**The recorded panel.** The first `RISK GATE SNAPSHOT` in `diagnostics.log`
carries the whole voting panel as a printed dictionary. Reading it back gives a
`VotingSummary` holding twelve real voters, which drives
`_emit_risk_gate_snapshot` and `_emit_trade_fire_snapshot` directly.

**A real tick loop.** `ScrummingBot.tick()` runs 400 times against a
`TabletBackend` serving a recorded tape that climbs and falls, so both bands are
reached. Only the outward edges are supplied: the tablet venue and a private
`CapitalReservationRegistry` under a temporary directory. Every gate, every
sizing decision and every message is the shipping code.

The before reading came from a second worktree at `origin/current`, driven the
same way against the same data.

## The instrument answers for itself

The driver was pointed at `origin/current` and its `RISK GATE SNAPSHOT` line
compared against the line the live fleet actually wrote:

```
recorded live chars 1008
before-tree  chars  1008
byte identical:     True
```

The rebuilt panel reproduces the live producer exactly, so the after reading is
a reading of the same producer and not of a lookalike.

## The panel dump, before beside after

The measurement that decided what the tightened line keeps, taken over 1,143
real snapshots:

```
message length        min 1005   median 1011   max 1017
weight per indicator  exactly one value each, all 1,143 snapshots
detail present        adx, kaufman_er, zscore only — always, all 1,143
NEUTRAL confidence    4,981 readings, 0 of them above zero
```

Weight never moves, so printing it 1,143 times repeats a configuration constant
rather than reporting a reading. A NEUTRAL vote is fixed at zero confidence in
the indicator code itself — `rsi.py` sets it outright, `adx.py` assigns `0.0` —
so its confidence is a constant too. Both come out. Direction, confidence and
the raw detail are per-tick readings and all stay.

Before, on the recorded panel:

```
RISK GATE SNAPSHOT [SCRUM] risk_blockers=['hysteresis_scrum']
ticker_last=3.17e-06 panel={'bollinger_bands': {'dir': 'BEARISH', 'conf':
0.824, 'weight': 1.0, 'detail': None}, 'vortex': {'dir': 'BULLISH', 'conf':
1.0, 'weight': 0.9, 'detail': None}, 'macd': {'dir': 'BULLISH', 'conf': 0.6,
'weight': 1.2, 'detail': None}, 'stochastic_rsi': ... 'rsi': {'dir':
'NEUTRAL', 'conf': 0.0, 'weight': 0.8, 'detail': None}}

1008 characters
```

After, same panel, same run:

```
RISK GATE [SCRUM] blocked by hysteresis_scrum. Price $0.00000317.
Panel 6 bullish, 3 bearish, 3 neutral.
bullish vortex 1.00, kaufman_er 0.70 (er 1.0), macd 0.60, adx 0.36 (adx
25.52), volume 0.35, supertrend 0.26.
bearish bollinger_bands 0.82, stochastic_rsi 0.50, slingshot 0.35.
neutral ichimoku, rsi, zscore (z 0.143).

322 characters
```

The price reads `$0.00000317` rather than `3.17e-06`, matching every other
price on the log. `TRADE FIRED` takes the same panel line and went from 1,044
characters to 354.

## Every message the real tick loop produced

400 ticks, one bot, the same tape both sides.

| head | before | after |
| --- | --- | --- |
| DELTA | `Delta: $+3.9417 (7.9%) — holdings=$53.9417 vs target=$50.00` | `DELTA: $+3.9417 (7.9% of target) \| holdings $53.9417 vs target $50.0000` |
| TA VOTE | `TA Vote: BEARISH (conf=0.25, B:2/N:4/S:6) \| BB pos=0.02` | `TA VOTE: BEARISH at confidence 0.25 \| 2 bullish, 4 neutral, 6 bearish \| BB position 2.3%` |
| HOLD SCRUM | `HOLD SCRUM: delta +$3.9417 but TA=BEARISH conf=0.25 (floor 0.25) — waiting for BULLISH` | `HOLD SCRUM: delta +$3.9417 — TA=BEARISH is not BULLISH or NEUTRAL` |
| HOLD FOLD | `... queued — TA=BEARISH but confidence 0.25 < 0.25 floor` | `... queued — TA=BEARISH but confidence 0.2471 < 0.2500 floor` |
| BULLSEYE UPPER | `... FIRE ramp in FIRE; scrum fires only when ramp reaches FIRE.` | `... Ramp at FIRE, so the FIRE gate passes.` |
| BULLSEYE LOWER | `... Fold decision governed by MEM-171 tranche gates.` | `... 3 tranche(s) queued; a fold needs one whose reference price the market has fallen past.` |
| override | `MEM-196 RIPE-HARVEST OVERRIDE ta_bullish: raw is_bullish=False (dir=BULLISH, conf=0.06, floor 0.19) — RipeHarvestScrumOverride will force-pass.` | `RIPE HARVEST OVERRIDE: the TA gate refused the scrum (TA=BULLISH, confidence 0.0614, floor 0.1923). The ripe-harvest override passes it.` |
| BB PRIORITY SKEW | 356 characters ending `Arm alone would be 0.1923. TA direction NOT flipped — actively-contradicting TA still gates trade, and a confidence under the relaxed floor still refuses it.` | 291 characters ending `The direction is untouched, so a contradicting TA still refuses the trade.` |
| FOLD DIAG | `FOLD_DIAG_BLOCKED: 3/3 tranches strict-eligible ... State: bb_pos=0.023, is_bearish=False, fold_ok_midline=True, bb_below_lower_dt=True, ...` | `FOLD DIAG blocked: 3 of 3 tranche(s) eligible ... BB position 2.3%, TA bearish no, midline gate yes, below the lower detect line yes. ...` |

`BALANCE DRIFT`, `DRIFT UP`, `ADOPTION CAPPED`, `OPENING POSITION ADOPTED`,
`INIT HANDSHAKE OK`, `Scrumming init`, `Mode` and `TARGET` are identical on both
sides. They are boot and reconciliation lines, not tick messages, and none was
touched.

## The line that said something false

`HOLD FOLD` printed `confidence 0.25 < 0.25 floor`. Read literally that is not
true, and the operator cannot act on it. The gate is
`eff_confidence >= _eff_conf_floor`, so the two numbers differ; both rendered at
two decimals and collided.

A trace on `scrumming_bot.py` line 4023, inside a real tick, read the frame:

```
site reached 12 time(s) inside a real tick
  eff_confidence=0.0111  _eff_conf_floor=0.25                dir=BEARISH
  eff_confidence=0.0844  _eff_conf_floor=0.2577319587628866  dir=BEARISH
  eff_confidence=0.1265  _eff_conf_floor=0.25                dir=BEARISH
```

The floor is not always the standing 0.25; the skew moves it into the third
decimal and beyond. Both numbers now print at four decimals, at every site that
compares them.

Counted over the 400-tick run, both sides:

```
lines printing A < B with A equal to B
  before  2      HOLD FOLD, and the TA-conf-below-floor blocker inside FOLD DIAG
  after   0
```

The instrument reported two before the change, so its zero afterwards is a
reading.

## The line that named a condition the data could not support

`HOLD SCRUM` said `— waiting for BULLISH`. It fires on `not is_bullish`, which
is a conjunction: the direction must be BULLISH or NEUTRAL **and** the
confidence must clear the floor. When only the floor blocked it, the message
told the operator to wait for a direction the panel had already produced.

That is the same defect `tests/test_fold_hold_reason_is_true.py` was written
for, on the fold side, in August. The scrum side was never brought across. It
is now: the branch names the half that actually failed, and the two halves are
exhaustive, because `is_bullish` being false with a good direction leaves only
the floor.

The same conjunction is printed by the every-fifty-ticks scrum summary, which
rendered `not_bullish(dir=BULLISH)` — self-contradicting on its face. It now
names the failing half as well.

## The one line whose firing frequency changed, and why

The brief said to change wording, not when a line is written. One line had to
move, and it is the one that fired on the wrong condition.

`FOLD DIAG blocked` writes only when the blocker set changes. The key it
compared was `"|".join(sorted(_fold_blockers))` — the blocker strings **with
their rendered numbers in them**. A confidence drifting in the second decimal
therefore read as a new blocker set. Raising the rendering to four decimals made
that worse before it made it better: the run went from 111 lines to 112 on the
first pass, purely from added digits.

The key is now the blocker names, with the parenthesised detail cut. The line
writes when a blocker joins or leaves, which is what
`_fold_diag_last_blocker_set` has always been named for.

```
bot.log lines over the 400-tick tape
  before  250
  after   239
```

Eleven fewer lines, all of them repeats of a blocker set that had not changed.

## Identifiers that mean nothing outside this repository

Four removed. Each said what the gate did instead.

```
MEM-171   BULLSEYE LOWER    -> the tranche count, and what a fold needs
MEM-258   AT TARGET         -> the dust band, which the line already states
MEM-196   two override lines -> the gate that refused, and what passed it
FOLD_DIAG_SNAPSHOT and its four siblings -> FOLD DIAG, with a state word
```

## What is not changed

`READ`, `HOLD FOLD` and the four `TARGET` ramp lines were already tight,
standardized and true. Their wording moved only where a word was code rather
than English.

`TA-conf-below-floor` maps to no label in `src/trading/gate_vocabulary.py`. It
appears 251 times on the scrum side and 285 on the fold side in the real
`gate.log`, so the gate-light strip on the Simulator and History screens shows
nothing for it. Adding a twentieth light changes a picture the operator reads,
and both screens are deferred, so the vocabulary is untouched and this is one
line for the issue.

`_BB_PRIORITY_CONFIDENCE_FLOOR` was printed on every BB priority line as `Arm
alone would be 0.1923`. It is a module constant, `0.25 / 1.30`, identical on
every line. It came out on the same ground as the voter weights.

## Tests

Serially, no `-n`. Every test naming a changed symbol or message.

```
test_c39g_bot_log_reaches_disk.py          test_fold_diag_matches_executor.py
test_fold_hold_reason_is_true.py           test_sim_bot_agrees_with_its_venue.py
test_fold_tranche_books_net_proceeds.py    test_fold_tranche_count_bound.py
test_ivp_persist_and_named_causes.py       test_scrum_fold_pct_mirrored_on_every_path.py
test_hedge_reserve_reads_the_gap_the_fold_left.py
test_fold_tranche_partial_consumption.py   test_gate_chain_blocker_messages.py
test_gate_coverage.py                      test_autonomous_fold_price_gate.py
test_fold_gate_order_independence.py

551 passed, 1 skipped
```

Three test files named a renamed string.

`test_sim_bot_agrees_with_its_venue.py` pins that a held message states the
numbers it compared. It looked for `Δ=$`, a bare `<`, and `holding`. The bare
`<` matched any comparison anywhere in the line. It now looks for `delta $`,
`interval` and `holding` — the same invariant, naming the threshold that was
compared rather than the punctuation of the comparison.

`test_c39g_bot_log_reaches_disk.py` emits its own literal onto the bus and
asserts it reaches disk. Its docstring calls that literal "the exact vocabulary
the operator was told to grep for", so the literal was updated to the vocabulary
that now exists.

`test_fold_hold_reason_is_true.py` passes unchanged, all 31.

## Archetypes

Fixture controls first, both directions:

```
coding_archetype  known_good.py        exit 0
coding_archetype  known_bad.py         exit 1
ta_archetype      known_good_ta001.py  exit 0
ta_archetype      known_bad_ta001.py   exit 1
```

Then the files:

```
coding_archetype  src/trading/scrumming/snapshots.py     passed
coding_archetype  src/trading/scrumming/tick_phases.py   passed
coding_archetype  src/trading/scrumming_bot.py           passed
ta_archetype      src/trading/scrumming/snapshots.py     passed
ta_archetype      src/trading/scrumming/tick_phases.py   passed
ta_archetype      src/trading/scrumming_bot.py           passed
docs_archetype    docs/manual/06-trading-tab.md          passed
docs_archetype    docs/manual/08-tabs.md                 passed
```

`coding_archetype` on `scrumming_bot.py` was run by hand: the PostToolUse hook
cannot gate that file inside its thirty-second limit.

## Edits

`src/trading/scrumming/snapshots.py` — `_panel_line` renders the voting panel as
a count and three direction groups, strongest confidence first, and both
snapshot emitters read it, so the two lines cannot drift apart.
`_build_panel_snapshot` now records which detail key it took, so `adx 25.52` and
`z 0.143` are told apart. `yes_no` renders one flag for a message.

`src/trading/scrumming/tick_phases.py` — both bullseye notices, the four
`FOLD DIAG` lines and the all-gated `HOLD FOLD`. The `FOLD DIAG blocked` dedupe
key reads the blocker names rather than their rendered numbers.

`src/trading/scrumming_bot.py` — `DELTA`, `READ`, `TA VOTE`, `HOLD SCRUM`, the
scrum hold summary, `AT TARGET`, `BB PRIORITY SKEW`, and the four override
lines. Every site comparing a confidence against a floor prints four decimals.

## What the operator sees differently

The gate snapshot on his Activity Log was a thousand characters of Python
dictionary. It is now about three hundred, grouped bullish, bearish and neutral,
strongest voter first, and it still carries every reading that changes tick to
tick. Two lines that said something arithmetically false say the true numbers.
One line that told him to wait for a signal his own panel had already produced
now names the gate that actually refused. Four labels that pointed at nothing he
could look up are gone.
