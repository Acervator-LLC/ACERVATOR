# Replay findings, cold read and repair plan

Mode: Explanation, with a Reference table of sized work units. This
document re-verifies the five findings of
`docs/engineering-notes/2026-08-12_tranche_replay_validator.md` against the code as
it stands on 2026-08-13, sizes the surviving repairs, and records the
archetype baseline of every file those repairs would land in. It changes
no code.

Read-only throughout. No island. No commit. No version bump. The
operator's application was not started, stopped, or attached to. It is
trading real money on 37 live bots while this was written.

## 1. What was pinned

`~/.acervator/bot_state.json` was copied to the session scratchpad and
read there.

| property | value |
|---|---|
| pin time | 2026-08-13T17:00:48Z |
| source mtime | 2026-08-13 10:00:05 local |
| bytes | 838,140 |
| sha256 | `7e47266dc3ab99b83e74e22d5d6e4ada0da241f4173a65853533c397e3c81dce` |
| `saved_at_human` | 2026-08-13 10:00:05 |
| bots | 37 |
| mtime stable across the read | yes |

`src/trading/scrumming_bot.py` was pinned at 782,200 bytes, 14,153
lines, sha256 prefix `9cf7354c8aeb35e2`. That is byte-identical to the
copy the four cold reads worked from, so their quoted anchors and mine
describe the same file.

The state file does **not** persist `_current_holdings`. The holdings
scalar exists only at runtime. Section 3 explains why that matters and
where the scalar was read instead.

`coinbase_credentials.json` was never opened. Nothing was written to
`~/.acervator` or `~/.acervator_logs`.

## 2. Verdict table

Verdicts are from cold reads against current source. The cost column is
measured by this document from the pin above, not inherited.

| # | Finding | Verdict | What it costs today | In the 13 divergences? |
|---|---|---|---|---|
| F1 | The cap cannot admit what the spawn creates | **FIXED** | Nothing. `_plan_fold_consumption` splits against the remaining cap; `_settle_fold_plan` removes by identity. 92 over-cap tranches worth $132.96 are now admissible in slices. | **No.** Delays a rebuy; creates and destroys no units. Predicts a divergence of zero, which has no sign. |
| F2 | `scrum_fold_pct` honoured at one site only | **FIXED** | Nothing. Three tranche-building sites exist and all three scale. 8 bots run below 100 percent, governing $32.25 of a $208.16 queue. | **No.** Writes only `usd` and `units` on `_fold_tranches`. Never touches `_main_lots`. |
| F3 | Two consumption rules in one file | **PARTIAL** | The ungated loop in `_execute_manual_rebalance` is byte-identical to pre-promotion HEAD. 461 tranches worth $208.16 across 23 bots are reachable by it at any price. 12 bots arm Max Cartridge, 37 arm Wire Stack; both fire it autonomously. | **No.** Changes when a fold fires, not the arithmetic that books one. Its buy leg already reads `_settled_fill`, which is the more accurate of the two paths. |
| F4 | The sell path never reads back the executed quantity | **PARTIAL** | Six of eight sell paths still book the requested size. Two paths were closed by commit `953c253` on 2026-08-07, five days before the report that described them as open. | **No, and the sign is wrong.** An unread sell debits the book by more than the venue sold, which reads negative. Eleven of the thirteen rows are positive. |
| F5 | A tranche can be consumed to nothing and still exist | **PARTIAL** | Closed on the autonomous path. The manual loop keeps a units-only drain predicate and removal by value. Stored state holds 0 husks and 0 partial-spent remnants today. A husk is worth about $2.6e-14 and survives one fold cycle. | **No.** Ten to eighteen orders of magnitude too small, and a stranded husk reads negative. |
| D1 | The lot book is reconciled against nothing | **OPEN, and not named by any of the five** | 11 bots hold more units in `_main_lots` than in the holdings scalar, worth $29.74 of phantom position. 3 bots hold $4.04 of real coin they refuse to claim. | **Yes. This is the cause.** See section 3. |

## 3. What actually explains the thirteen divergences

The published comparison has two terms, the lot book and the export, so
it cannot say which of them is wrong. A third term settles it: the
holdings scalar the bot reconciles against the venue.

`_reconcile_holdings` prints both of its inputs on every run. The
emitter is the instrument. Quoted source is the anchor; line numbers
move.

```
        internal_units = self._current_holdings
```

It reads the scalar. It never reads `sum(lot["units"] for lot in
self._main_lots)`. Nothing else does either, in the trading path.

A 300 MB tail of `~/.acervator_logs/console/system.log` was read
read-only: 1,255,034 lines, 23,292 aligned readings and 1,242 drift
readings, covering 37 distinct bots. No bot is silent. Joining the last
reading per bot to the pinned lot book gives three populations.

| population | bots | signature | value |
|---|---|---|---|
| lot book above the scalar | 11 | scalar equals the venue exactly; the reconcile prints `aligned` | $29.74 phantom |
| scalar below the venue | 3 | drift-up branch refuses the surplus by design | $4.04 unclaimed |
| neither | 23 | book, scalar and venue agree | — |

Nine of the eleven reproduce the published percentages to the reported
digits.

| asset | excess units | excess | published |
|---|---|---|---|
| ORCA | 5.32340782 | +10.92% | +10.92% |
| LINK | 0.26871905 | +3.08% | +3.08% |
| ZEC | 0.00823103 | +2.68% | +2.68% |
| KAT | 1202.77875379 | +2.59% | +2.74% |
| PENGU | 332.55171539 | +2.10% | +2.10% |
| DOGE | 27.66247531 | +1.94% | +1.95% |
| BONK | 750458.33848215 | +1.71% | +1.71% |
| ETH | 0.00167269 | +1.56% | +1.56% |
| XLM | 4.20778050 | +1.35% | +1.35% |
| BTC | 0.00004406 | +1.12% | +1.12% |
| SOL | 0.00580807 | +0.58% | not listed |

In every one of the eleven the reconcile read `internal == exchange`
exactly, and printed `aligned`. The export is not stale on these rows
and it is not wrong. The scalar agrees with the venue, the venue agrees
with the export, and the lot book is the outlier.

**The check built to catch this reports a pass on it.** That is an
oracle false negative in the running system, on 11 of 37 bots, every
day. The predicate that establishes it was run against a mutated copy
and dropped to False, so it discriminates.

The direction is one-way, and the data shows exactly one direction: 11
bots above, **0 below**, 26 flat. The drift census over the same tail
says the same thing a second way: 1,245 drift events, of which **1,244
are drift-up** and exactly **one is drift-down**. The single drift-down
is CAP. `bootstrap_exchange_state` clamps the scalar with `min` against
the lot sum:

```
                self._current_holdings = min(
                    max(0.0, _units), _tracked_units_bootstrap) \
```

`min` can pull the scalar down to the venue. It can never pull the lot
list down with it.

Two further sites already compute this exact quantity and neither acts
on it. The state-restore check emits `STATE RESTORE WARNING` and
returns. `_main_lots_invariant_ok` computes `abs(lots_sum -
self._current_holdings) <= tol` and its own docstring says:

```
        NOT A GUARD. This reports; it never blocks.
```

Grep over `src/` finds no caller of it in the trading path. Every caller
is under `tests/`.

One limit on this evidence, found by controlling the instrument rather
than by trusting it. The init handshake re-seeds the scalar from the lot
sum, directly inside `if not self._initialised:` with no inner
condition. If it ran, the 11 group A bots would fire drift-down on every
launch. Counting its `INIT HANDSHAKE OK` line gave zero, which looked
conclusive. It is not: that line is a bus emit, and **bus emits never
reach this log**. Probed on the same tail, every bus-only string scores
0 and every logger string scores non-zero.

| probe | kind | occurrences |
|---|---|---|
| `INIT HANDSHAKE OK` | bus emit | 0 |
| `DRIFT UP (` | bus emit | 0 |
| `BALANCE DRIFT (` | bus emit | 0 |
| `ADOPTION CAPPED` | bus emit | 0 |
| `balance drift (` | `logger.warning` | 1,245 |
| `drift UP (` | `logger.info` | 1,244 |
| `bootstrap_exchange_state` | `logger.info` | 3,462 |

The handshake therefore cannot be observed here at all, and the zero was
my instrument. What survives is indirect and still strong: the app
restarted at 00:58 today, and a handshake that re-seeded the scalar from
the lot book would have produced 11 drift-down events. One occurred.
Which writer leaves the scalar equal to the venue on group A bots is
therefore **not settled**, and section 8 records it as open.

CAP is the control that proves the repair works and proves what it
cannot reach. At 2026-08-13 01:10:54 local the emitter printed
`internal=1136.227658 exchange=995.000000 drift=-141.227658 (12.430%)`.
Those are the published stored and export figures to six decimals. CAP's
excess had leaked into the audited counter, so the one working repair
deleted it, and CAP reads zero today. The other eleven hide their excess
in the counter nobody audits.

## 4. Repair units

Every unit below lives in `src/trading/scrumming_bot.py`. They cannot
run concurrently. Each owns one verb. Named neighbours are behaviours
with their own specification that this unit must not touch.

### U1 — LABELS the fallback emitter with its caller

`_settled_fill` hardcodes `MANUAL FIRE:` into the message it emits when
the venue reports no settled fill. Two callers are manual today, so the
label is true today. U5b adds an autonomous caller, and the label would
then lie about its own origin.

- **Verb: LABELS.** Structural. No behaviour changes.
- **Not this unit:** the polling policy (three attempts, 0.2 s) —
  that unit WAITS. The estimate fallback itself — that unit ESTIMATES.
  The `is_real` flag's consumers — those CONSUME.
- **Accepted input:** one `label` parameter.

| value | accepted | result |
|---|---|---|
| `"MANUAL FIRE"` | yes | current message, unchanged |
| `"SCRUM"`, `"DIST"`, `"STACK"` | yes | names that path |
| `""` | yes | falls back to the default label |
| `None` | yes | falls back to the default label |
| absent (default) | yes | `"MANUAL FIRE"`, so existing callers are byte-identical |

- **Two-sided control:** force the fallback (venue returns an order with
  no numeric fields and `get_order` raises) from each caller. Read the
  emitted `bot.log` string, which is the surface the operator sees.
  Planted defect: pass the wrong label and assert the test fails.

### U2 — RECONCILES the lot book against the venue

`_reconcile_holdings` compares the scalar only. Make it compare the lot
sum as well, so a book that disagrees with the venue is detected.

- **Verb: RECONCILES.** Behavioural, and it is the safety net for
  everything after it.
- **Not this unit:** the drift-up policy, which refuses surplus units —
  that unit ADOPTS, and the operator ruled on it in v3.23.43. The `min`
  clamp in `bootstrap_exchange_state` — that unit PRE-FILLS. The init
  handshake that sets the scalar from the lot sum — that unit SEEDS. The
  0.5 percent tolerance — that unit CALIBRATES, and recalibrating a
  constant around a defect is forbidden. How a correction is spread
  across lots, which today is a common ratio that haircuts every lot
  rather than removing units that were never there — that unit
  ATTRIBUTES, and it carries MEM-171 provenance.
- **Accepted input:** the lot sum, the scalar, and the venue reading.
  All three are floats and the type gate does not close them.

| input | type | accepted | required behaviour |
|---|---|---|---|
| `sum([])` over empty `_main_lots` | `int` 0 | yes | treated as zero, not as an error |
| ordinary positive units | `float` | yes | compared |
| `nan` in one lot | `float` | **no** | refuse and emit; `type(float('nan')) is float`, so the strictest type gate still admits it, and `json.loads('NaN')` returns it, so a hand-edited state file reaches it |
| `inf`, `-inf` | `float` | **no** | refuse and emit |
| `-0.0` | `float` | yes | equals zero |
| negative units | `float` | **no** | refuse and emit |
| lot dict with no `units` key | — | yes | treated as zero, matching the restore check's `.get`, not `_main_lots_invariant_ok`'s `[]` |
| venue reading `nan` or negative | `float` | **no** | refuse; do not rescale |

  The `nan` row is the one that matters. A `nan` lot makes the drift
  comparison False, which falls to the drift-down branch, where
  `_ratio = exchange_units / internal_units` is `nan` and every lot's
  units become `nan`. The book is destroyed. `math.isfinite` closes it
  in one call.

- **Two-sided control:** drive the real `_reconcile_holdings` on a stub
  whose lot book is ORCA's, 54.05340782 units against a scalar and a
  venue of 48.73. Read the surface the check reports through: the
  emitted `bot.log` line and the resulting lot sum. It must FIRE.
  Negative side: an aligned bot must produce SILENCE and an unchanged
  book. Planted defect: restore the scalar-only comparison and assert
  the ORCA fixture goes silent, which is the present live behaviour.

### U3 — GATES the autonomous fold on price

The fold loop in `_execute_manual_rebalance` carries no `ref` term. The
file's own header states the rule as a critical invariant. An
autonomous-only guard block already exists and already refuses on a
position mismatch and on a position ceiling. The price gate belongs
inside it.

- **Verb: GATES.** Behavioural. It can only make the bot trade less.
- **Not this unit:** the per-cycle cap — that unit BOUNDS, and it is a
  second verb even though F3 names both. How a tranche is divided —
  `_plan_fold_consumption` SPLITS. When a record is retired — U4 DRAINS.
  The `manual_button` exemption — the operator ruled on it, and the
  code says so in as many words. Do not re-ask.
- **Accepted input:** `caller_intent` is already a closed three-value
  set, enforced by a `raise` on anything else.

| `caller_intent` | gated by this unit |
|---|---|
| `"manual_button"` | **no**, exempt by operator directive |
| `"wire_stack"` | yes |
| `"max_cartridge"` | yes |
| anything else | unreachable; `ValueError` is raised before this point |

  The price terms are floats and need value rows:

| `ticker.last` or `t["ref"]` | accepted | required behaviour |
|---|---|---|
| positive finite | yes | compared against `ref * otd_factor` |
| `0.0`, `-0.0` | **no** | refuse the tranche, do not divide |
| negative | **no** | refuse the tranche |
| `nan` | **no** | refuse; every comparison against `nan` is False, so an ungated pass is the default failure |
| `inf`, `-inf` | **no** | refuse the tranche |
| `ref` key absent | **no** | refuse; the malformed-ref guard already exists upstream |

- **Two-sided control:** four tranches priced above the current price,
  every one price-ineligible. Drive the real coroutine at each of the
  three intents. `wire_stack` and `max_cartridge` must consume nothing.
  `manual_button` must consume all four, which proves the gate is not a
  blanket refusal. Planted defect: remove the price term and assert the
  autonomous intents consume all four, which is today's measured
  behaviour.

### U4 — DRAINS a spent tranche on the manual loop

The manual loop retires a record when `units <= 1e-12`. The autonomous
path was converted to test dollars as well, and to remove by identity.
`usd <= 1e-9` is denomination-free; `units <= 1e-12` means $1.2e-07 on
BTC and $1.7e-17 on BONK. Removal by value can retire two records on one
buy when their numbers coincide.

- **Verb: DRAINS.** Behavioural. No money moves.
- **Not this unit:** what a fold spends — U3 GATES it. How the remainder
  is scaled — that unit SPLITS. The top-up merge into an older record —
  that unit MERGES.
- **Accepted input:** the residue on a tranche after a take.

| residue | accepted | required behaviour |
|---|---|---|
| `units > 1e-12` and `usd > 1e-9` | yes | survives as a remnant |
| `units <= 1e-12` | yes | drained and removed |
| `usd <= 1e-9`, units above the floor | yes | drained and removed; this is the band the two predicates disagree on, non-empty on 22 of 23 stored queues |
| exactly `1e-12` | yes | drained; the boundary is inclusive and must be tested at the value, not near it |
| `0.0` and `-0.0` | yes | drained |
| `nan` | **no** | refuse; a `nan` residue is neither above nor below the floor, so it survives for ever |
| `inf` | **no** | refuse |
| two records with identical numbers | yes | exactly one is removed, by identity |

- **Two-sided control:** the operator's own stored queues, driven
  through the real coroutine at fill quantities swept around every
  cumulative tranche boundary. Zero husks required. Planted defect:
  delete the removal step and assert the husk count goes non-zero, which
  a prior sweep measured at 4,329 husks over 35,073 samples. Second
  plant: two value-identical tranches, and assert that removal by value
  retires both while removal by identity retires one.

### U5a — WIDENS the sell primitive's contract

`_execute_sell` returns `Optional[float]`, a fill price. The executed
quantity is never returned, so no caller can book it. Widen the return
to carry the quantity. Callers unpack it and continue to use the price
only, so behaviour is byte-identical.

- **Verb: WIDENS.** Structural. Zero behaviour change, and the test says
  so.
- **Not this unit:** what the callers do with the new value — U5b BOOKS
  it. Where the value comes from — U5b READS it back. The buy twin — its
  own unit, and it is withheld; see section 5.
- **Accepted input:** three call sites, enumerated by grep, not by
  memory: the SCRUM caller, the DIST caller, and the stack-tranche
  spend. Plus the `None` return on the failure path, which every caller
  already tests.

| return | accepted | required behaviour |
|---|---|---|
| success | yes | tuple carrying the price and the quantity |
| failure | yes | still falsy at every call site, unchanged |

- **Two-sided control:** a differential run. Drive all three callers
  before and after, and require the booked outcome to be identical in
  every field. Planted defect: change one booked value by one ulp and
  assert the differential test fails. A refactor test that cannot fail
  on a one-ulp change is not measuring anything.

### U5b — BOOKS the executed sell quantity

This is the F4 repair. `_execute_sell` debits `self._current_holdings -=
amount`, the requested size. The SCRUM caller then debits `_main_lots`
from `_units_remaining = scrum_asset`, also the requested size, and
recomputes `scrum_usd = scrum_asset * sell_fill` where only the price is
real. `_settled_fill` already exists and already solves this; the repair
adopts it rather than inventing a second mechanism.

- **Verb: BOOKS.** Behavioural, on the money path.
- **The scalar and the lot book move together, in one unit.** Splitting
  them is not allowed. The invariant the file declares is `sum(lot
  ["units"]) == _current_holdings`. A unit that debits the scalar by the
  executed quantity while the lots keep the requested quantity would
  manufacture exactly the D1 divergence this plan exists to close.
- **Not this unit:** whether the trade should fire — U3 GATES. Tranche
  sizing — that unit SPLITS. The buy twin — withheld. The
  `is_real=False` fallback policy — that unit ESTIMATES, and it is
  already specified.
- **Accepted input:** whatever the venue reports for `filled`.

| venue `filled` | accepted | required behaviour |
|---|---|---|
| positive, below the request | yes | book the executed quantity, both counters |
| equal to the request | yes | unchanged from today |
| `0` or `None` or absent | yes | poll, then fall back to the estimate and set `is_real=False` |
| `"0.4"`, a numeric string | yes | `float()` already coerces it in `_extract` |
| above the request | **no** | refuse and emit; a venue cannot fill more than it was asked for, so this is a parse error, not a fill |
| `nan`, `inf`, `-inf` | **no** | refuse and fall back to the estimate |
| negative | **no** | refuse and fall back to the estimate |

- **Two-sided control:** request 1.0 unit, venue fills 0.4. The
  instrument is booked-minus-filled, read on both counters. Required
  reading: zero on both. Planted defect: restore the requested-size
  debit and require the instrument to read +0.6 on both. The clean side
  is meaningless unless the planted side reads +0.6 first. Second
  control: `get_order` call count must be 1 on the clean side and 0 on
  the planted side, which proves the readback actually happened rather
  than the numbers coinciding.

### U6 — EMITS the booked-against-filled record

No repair to the buy side is planned, because the buy side is not
measured. Two estimators were built and both are confounded: per-trade
matching over-counts because the export lists one row per venue fill
while `trade.log` holds one record per order, and window totals
under-count because `trade.log` holds 903 records against roughly 2,200
venue fills in the same window.

The missing fields are named and small. Emit the venue `order_id` on
each trade record, and the units actually booked beside the units
requested. With those, `get_my_trades` closes the loop with no
inference. `exchange.get_my_trades` is already called elsewhere in the
class.

- **Verb: EMITS.** One event, two new fields, no verdict.
- **Not this unit:** any repair the measurement later justifies. The
  Console rendering of the record — that unit RENDERS. Log rotation —
  that unit ROTATES.
- **Accepted input:** the order object, which may carry `id` as a
  string, an int, `None`, or not at all. All four must produce a record
  rather than an exception, because an emitter that raises on a live
  trade is worse than the gap it measures.
- **Two-sided control:** two-sided at the CONSUMER, not at the emitter.
  Force a fill and a no-fill, and read the field a reader parses out of
  the written record. Planted defect: emit the requested quantity into
  the booked field and assert the reconciliation of the record against
  a synthetic venue history reports zero gap when the gap is real.

## 5. Order, and why the dependencies force it

Strict order. Every unit is in one file, so exactly one runs at a time.

| step | unit | what forces this position |
|---|---|---|
| 1 | U1 LABELS | U5b adds an autonomous caller to `_settled_fill`. Without U1 that caller emits `MANUAL FIRE` on an autonomous sell. A prerequisite of U5b, and free-standing. |
| 2 | U2 RECONCILES | Nothing blocks it, and everything after it needs it. Units 3 to 6 change what the books record. Until the lot book is compared against the venue, a bookkeeping regression accumulates silently for weeks, which is precisely how the present $29.74 arrived. Landing the detector before the changes it supervises is a dependency in the strong sense: without it the later units ship with no oracle in production. |
| 3 | U3 GATES | Pure refusal, so it can only reduce what flows through the ungated path. Doing it before U5b shrinks the blast radius of any error in the highest-risk unit. |
| 4 | U4 DRAINS | Code-independent of the others. Its position is fixed by a test-fixture dependency only: U3 changes which callers reach the loop, so writing U4 after U3 means its fixture is written once against the post-gate world. Stated as fixture economy, not as a code dependency, because it is not one. |
| 5 | U5a WIDENS | Structural prerequisite of U5b. Depends on nothing else. |
| 6 | U5b BOOKS | Needs U5a for the quantity and U1 for an honest label. Placed last among the behavioural units because it is the only one that changes what the books record about real fills. |
| 7 | U6 EMITS | Placed after U5b so the record can witness U5b's effect. It is also the gate on all buy-side work. |
| — | buy-side readback | **WITHHELD.** Its magnitude is unmeasured. U6 is the measurement. Planning a repair for an unmeasured defect is the error this document exists to avoid. |

U1 and U5a are both structural units with zero behaviour change on the
same contract. If the release gate cost dominates them, they may be
batched into one island run with two separate tests. That is a gate
economy decision and the operator makes it. It is not a boundary
decision, and no behavioural unit may be batched with anything.

## 6. Clean ground

A unit cannot be greener than the file it lands in. Every archetype that
applies was run on the unmodified live tree before any work order.

**The instrument was controlled first, in both directions.** An
archetype exits 0 and reports `passed: true` with zero findings on a
path that does not exist. Measured today:

```
python -m tools.harness.coding_archetype src/trading/NO_SUCH_FILE_control.py
EXIT=0   passed=true   findings=[]   errors=["target not found: ..."]
```

The red side was confirmed on the same tool: a copy of `otd_math.py`
with a planted `subprocess.run(..., shell=True)` returned EXIT=1,
`passed=false`, 16 findings, 3 high. An exit code is therefore
believable only when the target is confirmed to exist and the report
carries findings. Every baseline below was checked on both counts.

| file | archetype | exists | passed | findings | high or critical |
|---|---|---|---|---|---|
| `src/trading/scrumming_bot.py` | coding | yes | true | 1092 (547 med, 542 low, 3 info) | **0** |
| `src/trading/scrumming_bot.py` | ta | yes | true | 81 (all low) | **0** |
| `src/trading/otd_math.py` | coding | yes | true | 4 (all low) | **0** |
| `src/trading/otd_math.py` | ta | yes | true | 0 | **0** |
| `src/trading/stack_math.py` | coding | yes | true | 76 (21 med, 55 low) | **0** |
| `src/trading/stack_math.py` | ta | yes | true | 2 | **0** |
| `src/trading/bot_container.py` | coding | yes | true | 529 (135 med, 394 low) | **0** |
| `src/gui/bot_live_settings.py` | coding | yes | true | 633 (65 med, 561 low, 7 info) | **0** |
| `src/gui/bot_live_settings.py` | gui | yes | true | 99 (82 med, 17 low) | **0** |
| `src/gui/main_window.py` | coding | yes | true | 1553 (422 med, 1092 low, 39 info) | **0** |
| `src/gui/main_window.py` | gui | yes | true | 449 (306 med, 143 low) | **0** |

All ten tools reported available on the large run: ruff, mypy, pyright,
bandit, vulture, semgrep, scaffolding, hallucination, slop, numeric
guard. No archetype reported an error.

**Ground is clean. No unit is blocked by a pre-existing red file.**

Two notes for whoever builds. First, `otd_math.py` scored 0 on the TA
archetype; that is a real zero, because the same file scored 4 findings
on the coding archetype and all three TA tools reported available.
Second, these totals are the baseline to compare against. A build that
walks into 1092 findings and leaves 1090 has to be able to say so, and
cannot say so without this table.

The true touch set is one file, `src/trading/scrumming_bot.py`. The
other five are recorded because they were named as concurrently moving,
not because a unit needs them. Dropping a file a unit does not need is
the correct move, and all five are droppable here.

## 7. Live money against bookkeeping

Stated plainly, because the two classes carry different risk.

**U5b changes live money behaviour, and it is the highest-risk change in
this plan.** It changes what the books record about real fills. It runs
on every autonomous SCRUM and DIST sell across 37 bots trading real
money. If it books too little, the bot believes it holds units it sold
and will refuse to sell them again. If it books too much, the position
reads low and the next delta buys coins the operator already owns, which
is exactly the 2026-08-09 BICO and IMU incident the file documents. It
must ship alone, on its own island, with the planted defect shown red
before the clean result, and with `get_order` call counts read as well
as quantities.

**U3 changes live money behaviour, in one direction only.** It refuses
trades that fire today. 12 bots arm Max Cartridge and 37 arm Wire Stack,
so the refusal reaches the whole fleet. It cannot cause a trade; it can
only prevent one. A wrong gate costs a missed fold, not a wrong fill.
`manual_button` must stay exempt, and that is a test assertion, not a
preference.

**U2 changes live money behaviour once, then becomes a detector.** On
the first launch after it lands it will fire drift-down on the 11 group
A bots and rescale their lot books by up to 10.92 percent. That is a
real, one-time, operator-visible event worth $29.74 across the fleet. It
corrects the book toward the venue, which is truth. It also spreads the
correction across every lot by a common ratio, so each lot's recorded
size changes even though its `initial_buy_price` survives. The operator
should be told before it runs, not after.

**U1, U5a and U6 are bookkeeping.** U1 changes one emitted string. U5a
changes a return shape with a differential test proving byte-identical
behaviour. U6 adds two fields to a record. None of them can change an
order, a quantity, or a price.

**U4 is bookkeeping.** A husk is a record defect, not a money defect. It
costs a phantom row in the Fold Tranches tab, a truthy
`self._fold_tranches` that fold gates read, and a larger divisor in the
wire-credit split. It strands about $2.6e-14 for one fold cycle. Stored
state holds zero husks today.

## 8. What this plan does not do

It does not settle the 13 divergences by editing data. Section 3 shows
the lot book is the wrong term, and U2 corrects it from the venue rather
than from a spreadsheet.

It does not repair the buy side. That defect is real in shape and
unmeasured in size, and U6 is the measurement that would justify it.

It does not touch the drift-up policy, the bootstrap clamp, the init
handshake, the reconcile tolerance, or the ratio by which a correction
is spread across lots. Each is a named neighbour of U2 with its own
verb, and each is somebody else's unit.

One question is left open and named rather than answered. Which writer
leaves the holdings scalar equal to the venue on the 11 group A bots is
not settled. The `min` clamp in `bootstrap_exchange_state` produces
exactly that state and ran 3,462 times today. The init handshake would
undo it, and one drift-down event across 11 candidate bots argues that
it did not run, but its emitter is invisible to the console log so the
argument is indirect. Settling it needs one field: the lot sum logged
beside the units in the bootstrap line, which today logs only the units.

Three adjacent defects are named once here and repaired nowhere.
`_main_lots_invariant_ok` documents the invariant that fails on 11 bots
today, is called only from tests, and says of itself that it never
blocks. The fold-floor comparison against the exchange minimum is a bare
float `<`, so a take of $0.9999999 against a $1.00 minimum is held.
`_execute_buy` has the same missing readback as `_execute_sell` and no
`_settled_fill` equivalent on any of its five callers.

## Falsification

This document is wrong if any of the following holds.

The 11 group A bots do not read `internal == exchange` in the emitter.
That claim is the whole causal argument, and one counter-example refutes
it.

A twelfth tranche-building or tranche-consuming path exists that this
document did not enumerate. Sites were found by grep and by reading, and
a missed path would change U3's and U4's scope.

U2 lands and the 11 group A bots do not fire drift-down on the next
launch. The named candidate is the init handshake, which re-seeds the
scalar from the lot sum and would mask the gap before the reconcile ever
compares it. That path could not be observed from the console log,
because its only emitter is a bus emit and bus emits do not reach that
file. Whoever builds U2 should read the handshake first, from the
Console, and confirm which writer sets the scalar last.

The lot-above-scalar population is not one-way. Zero bots below is a
strong claim; one bot materially below the scalar refutes the `min`
clamp as the freezing mechanism.

U5b ships and the burst mismatches do not fall. The truncation-down
signature was measured in 12 of 12 cases, and a repair that does not
move it was aimed at the wrong term.

Any unit here needs a second adversarial round to close its input
domain. The accepted-input tables are written before the code precisely
so that cannot happen; a new input shape surfacing later means the unit
was oversized.
