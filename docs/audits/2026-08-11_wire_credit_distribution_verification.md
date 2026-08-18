# Wire-credit distribution to fold tranches — verification

Mode: Reference. This document records a verification run and its
evidence. It prescribes no fix.

Date: 2026-08-11
Scope: `ScrummingBot.apply_wire_income` and every path that later moves,
scales or destroys the credit it writes.
Product code changed: NONE.

## VERDICT — DEFECTIVE

**The even split itself is correct. Two paths around it destroy money,
and one of them threatens $171.84 on the operator's BTC/USD bot today.**

The distribution rule holds under test: every arrival splits evenly, sums
to the arrival, lands once per tranche, and survives a save and reload
with each credit still on the same tranche. The defects sit in the
lifecycle. This run executed two of them against shipped code rather than
inferring them:

| # | defect | status | live exposure |
|---|---|---|---|
| 1 | absorb-then-skim halves absorbed wire credit | EXECUTED, wrong | 7c39c7a2, $171.84 armed |
| 2 | arrival mid-fire is destroyed with the fired tranche | EXECUTED, wrong | any bot during a manual fire |
| 3 | parked total exceeds its own ledger | LIVE, measured | $354.03 across 2 bots |
| 4 | partial discharge scales `usd`, not the credit | LIVE, measured | 1 tranche, $0.0073 |
| 5 | no idempotency key on an arrival | latent | none observed |
| 6 | no bound between an arrival and the tranche it lands on | latent | none observed |

## Mechanism

A wire credit is a USD provenance record on a fold tranche. It states
that this many dollars of this tranche came from bot X at time T under
reference R.

`apply_wire_income` (`src/trading/scrumming_bot.py:2020-2234`) takes one
of three outcomes:

1. **STACK** (`:2152-2179`). The whole arrival lifts `_target_balance`
   and queues a buy. The code credits no tranche and writes no `wire_credits`
   entry. All 37 live bots carry `wire_inflow_stack_pct = 1.0`, so
   this diversion stands armed fleet-wide.
2. **DISTRIBUTE** (`:2197-2220`). The subject of this report.
3. **PARK** (`:2222-2234`). The zero-tranche case.

On the distribute path the split is even by count, not pro rata:

```
share = u / len(self._fold_tranches)          # :2199
t["usd"] = float(t.get("usd", 0) or 0) + share # :2201
self._add_wire_credits(t, [{...usd: share...}])# :2205
```

No eligibility filter exists. Every tranche receives a share regardless
of age, ref, or balance. The entry carries `ts`, `source`, `usd` and
`ref`. Here the code captures `ts` once per arrival at `:2055` and reuses it for
every tranche in that event. That shared `ts` is the only fingerprint an
arrival leaves behind, and every check below depends on it.

`_add_wire_credits` (`:3361-3400`) appends and then calls
`_roll_wire_credit_overflow` (`:126-163`), which folds detail past 20
entries into a `wire_credits_rolled` aggregate.

**Two different concerns share one loop body.** `t["usd"] += share` is
MONEY: it is the manual-fire buy cost at `:3197` and the fold queue at
`:2208`. The `wire_credits` list is an audit trail with exactly one
non-test reader, `nuclear_verification._tranche_wire_usd`
(`src/trading/nuclear_verification.py:298-330`). The list changes no
trading decision. It matters because it is the only instrument that can
retrospectively falsify the money half — which is what it did here.

## The conservation property

> Every dollar `apply_wire_income` accepts on the distribute path is, at
> every later moment, in exactly one of four places — a live tranche's
> `usd`, `_pending_wire_credits`, `_wire_credits_discarded_lifetime`, or
> spent on a completed rebuy — and never in two of them at once. The
> credit entries recording the arrival must sum to the arrival and must
> sit on tranches that exist.

Implemented in
`<scratchpad>/wcv_check.py`
in two modes, because they catch different defects:

- **Self-consistency** needs only the state. It sees a doubled credit, a
  broken part-sum, a bad shape, an identity collision.
- **Ledger** needs the arrivals the driver recorded. It sees a dropped
  credit and an orphan placement.

Self-consistency mode **cannot** see a deleted credit. A deleted entry
leaves nothing behind to contradict. Saying so is the point: a mode that
reported clean there would be an oracle false negative, and the live
result in the next section is reported inside that limit.

## The check failed on demand FIRST

The shipped code produces the fixture — a real `ScrummingBot`
receives a real `apply_wire_income` arrival of $9.00 across three real
tranches, giving $3.00 each. Every plant is a perturbation of genuine
output, not of an imitation.

Result: **10 of 10 rows met expectation.** Raw output in
`wcv_step1_out.txt` beside the script.

| row | expected | self-consistency | ledger |
|---|---|---|---|
| KNOWN-GOOD untouched | CLEAN | CLEAN | CLEAN |
| KNOWN-GOOD tranche folded back, accounted | CLEAN | CLEAN | CLEAN |
| **A — credit counted twice** | RED | `SC2_DUPLICATE_CREDIT` | `LM1`, `LM2` |
| **B — credit dropped entirely** | RED | *blind* | `LM1`, `LM2`, `LM3` |
| **C — credit on a tranche that no longer exists** | RED | *blind* | `LM1` |
| C2 — credit on a tranche never recorded | RED | *blind* | `LM1`, `LM2`, `LM4` |
| **D1 — rolled aggregate does not sum to its parts** | RED | `SC4_ROLLED_PARTS` | CLEAN |
| D2 — tranche grown, cached queue stale | RED | `SC3_QUEUE_SUM` | CLEAN |
| D3 — parked total does not equal its ledger | RED | `SC6_PENDING_PARTS` | n/a |
| D4 — one share scaled x1.5 (a pro-rata split) | RED | `SC1_UNEVEN_SPLIT` | `LM1` |

Sample arithmetic, plant A:

```
LM1_ARRIVAL_SUM: live $12.0000000000 + retired $0.0000000000
                 = $12.0000000000 vs arrival $9.0000000000
                 (missing $-3.0000000000)
```

Three controls stop this from proving less than it appears to:

1. **A false-positive control.** Row 2 removes a tranche that was
   *legitimately* folded back and accounts for it. The check stays CLEAN.
   Without this, `LM1` firing on row C would only show the check is
   always red.
2. **A blindness statement.** Rows B, C and C2 read *blind* for
   self-consistency because the run measured that, not because the mode
   never ran.
3. **A tolerance mutation.** Widening `USD_EPS` from `1e-9` to `1e9` and
   re-running the plants drops the arithmetic violations on A, B and D4
   from at least one each to **zero**. The tolerance is part of the
   check, not a knob.

The harness instrument carried its own control before use:
`coding_archetype` on `known_good.py` exits 0 and on `known_bad.py` exits
1.

## Live-data result — read-only

`~/.acervator/bot_state.json`, snapshot `2026-08-11 20:10:26`, 771,207
bytes. Each run took the digest before and after, and both match; the file is rewritten by the running application on its own
60-second timer, never by this work.

**Wire credits ARE present in production.** Inventory:

| measure | value |
|---|---|
| bots | 37 |
| fold tranches | 652 |
| tranches carrying any wire credit | 22 |
| bots carrying credit on any tranche | **1** — `c8e5c5db` (CHIP/USD) |
| wire-credit DETAIL entries | 264 |
| longest detail list (cap is 20) | 12 |
| tranches carrying `wire_credits_rolled` | **0** |
| credit USD standing on tranches | $0.8640 |
| credit USD in rolled aggregates | $0.0000 |
| parked (pending) wire credit | $363.0149 |
| discarded lifetime | $215.0996 |

**Conservation holds on 34 of 37 bots. Three fail.**

```
c8e5c5db  SC5_CREDIT_EXCEEDS_USD
  tranche #0 credited $0.03927376 > usd $0.03198447  (excess $0.00728929)

7c39c7a2  SC6_PENDING_PARTS
  pending $343.68244206 vs ledger $1.42573854 over 3 entries
  (unexplained $+342.25670352)

5d335c96  SC6_PENDING_PARTS
  pending $13.34109317 vs ledger $1.56091440 over 4 entries
  (unexplained $+11.78017877)
```

**Attributing the `c8e5c5db` over-credit.** Exactly four statements in
the whole file write a tranche's `usd`:

```
:2201   t["usd"] = float(t.get("usd", 0) or 0) + share     (credit, grows)
:3431   new_tranche["usd"] = ... + pending                 (absorb, grows)
:8792   _t["usd"] = _full_usd * _fold_frac                 (skim, shrinks)
:11150  t["usd"] *= (t["units"] / t_units)                 (discharge, shrinks)
```

Only the last two shrink a tranche, and neither touches `wire_credits`.
The observed ratio picks between them: `usd / credited = 0.03198447 /
0.03927376 = 0.8144`. This bot runs `scrum_fold_pct = 50`, so the skim at
`:8792` would leave exactly 0.5000. It leaves 0.8144, which is a units
ratio. The partial discharge at `:11150` wrote this, and it scales `usd`
while leaving the provenance at full value.

$354.03 of parked wire credit stands behind $2.99 of provenance. The
mechanism that fits is the persistence asymmetry: `pending_wire_credits`
has persisted since v3.16.57 (`:4609`) but `pending_wire_ledger` only
since v3.24.49 (`:4691`, restored at `:4964`). Every restart before that
kept the total and dropped the itemisation. Nobody observed this
happening — the diagnostics log retains about two days and the earliest
surviving ledger rows date to 2026-08-07. The mechanism fits; the event
does not appear in any retained record.

**Consequence at the next absorb.** `_absorb_pending_wire_credits_into`
(`:3417-3441`) adds the full pending amount to the new tranche's `usd` at
`:3431` but writes only `list(self._pending_wire_ledger)` as its
provenance at `:3432`. On 7c39c7a2 that is $343.68 of tranche balance
against $1.43 of provenance the instant it fires.

**The rolled aggregate has never engaged in production.** Longest detail
list is 12 against a cap of 20, and every rolled total is $0.00. Before
this report, `SC4` had gone red against a plant and nothing else. Adversarial case 5 below is the first exercise of that path
anywhere.

**Live exposure, measured independently:**

| condition | count |
|---|---|
| `scrum_fold_pct < 100` | 8 of 37 |
| `wire_inflow_stack_pct > 0` | 37 of 37 |
| holding parked wire credit | 4 |
| **armed for absorb-then-skim** (`fold_pct<100` AND 0 tranches AND pending>0) | **1 — 7c39c7a2 BTC/USD** |

```
7c39c7a2  BTC/USD  pending $343.6824 x (1 - 50/100) = $171.8412
                   would leave the fold queue on its next autonomous scrum
```

## Lifecycle results

Constructed bots, real methods. Raw output in `wcv_step3_out.txt`.

| hazard | what happens to the credit |
|---|---|
| **Manual fire a credited tranche** | Record dies with the tranche; the rebuy spent the dollars. $9.00 to $6.00 as the $3.00 tranche fires. Nothing carries into `_main_lots` — the rebought lot keeps units and `initial_buy_price` only. Consistent. |
| **Fold-back dequeue removes it** | LOST with the tranche, by design. $9.00 to $6.00, carrying away exactly $3.00. No counter anywhere records the credit USD destroyed here; `_tranches_discarded_lifetime` counts tranches. |
| **Re-sort the list** | SURVIVES. Credit rides with the dict object; total unchanged to 1e-12. The hazard is the INDEX, not the credit — see below. |
| **Export and re-import** | SURVIVES, proved at the consumer. |

**Re-sort is an index hazard.** `_execute_manual_rebalance` sorts at
`:11116`; `manual_fire_tranche` selects by position at `:3196`. Measured:
ref order `[1.01, 1.02, 1.03]` becomes `[1.03, 1.02, 1.01]`, so index 0
addressed ref 1.01 before the sort and ref 1.03 after. A stale index
fires a different tranche and takes that tranche's credit with it.
Whether the GUI can hold a stale index was not determined — the call site
was not opened.

**The consumer confirmed export/import**, not the raw dict. Read back
through `SwarmFeatureVerifier.scan_bots`, the only non-test reader:

```
BEFORE : tranches_seen 3, tranches_wire_fed 3, wire_usd_total 12.0,
         cross_bot_credits 6, sources {SRCBOT: 9.0, OTHERBOT: 3.0}
AFTER  : identical
every credit back on the SAME tranche : True
```

That “identical” is only worth reading because of its control: deleting
one tranche's credits moves the consumer total from $12.00 to $8.00. The
consumer is looking, so an unchanged number means survival rather than
blindness.

## Adversarial results

Raw output in `wcv_step4_out.txt`.

| case | outcome |
|---|---|
| arrival with zero eligible tranches | CORRECT, but strands |
| **arrival mid-fire** | **WRONG** |
| same wire event delivered twice | UNDEFINED |
| credit larger than the tranche | correct split, unbounded consequence |
| already-credited tranche receives more | CORRECT |
| **absorb then skim** | **WRONG** |

### Zero eligible tranches — correct, but strands

The code drops no value. It parks in `_pending_wire_credits` with a ledger
row, and both persist and restore. The code writes no `wire_credits` key
anywhere.

The queue is not safe either. Exactly one place calls the release window
`_absorb_pending_wire_credits_into` -- `:8756-8759` -- gated on an
autonomous scrum with `_tranche_count_before ==
0`. Measured: after tranches appear by any other path, a second arrival
distributes to the new tranches while the old pool stays parked. Live,
$363.01 sits parked and the fleet has already discarded $215.10.

### Arrival mid-fire — WRONG, and this is new

`manual_fire_tranche` captures the buy cost at `:3197`, then awaits the
ticker (`:3205`) and the buy (`:3229`), then removes the tranche at
`:3288`. Every coroutine in this application runs on the Qt GUI thread,
so an `await` is exactly where another bot's tick can run and wire into
this bot.

Driven at the real await point:

```
3 tranches x $10.00, one $9.00 arrival -> each tranche $13.00, credit $9.00
fire tranche #1: cost captured BEFORE the await = $13.00000000
during the awaited buy, a $6.00 arrival lands -> $2.00 per tranche
fired tranche ended holding $5.00 of credit and $15.00 of usd
the buy spent $13.00

fold queue $39.00 -> $30.00
of the $6.00 arrival: $4.00 reached surviving tranches
                      $2.00 was destroyed with the fired tranche
```

The $2.00 landed on a tranche the code then removed, and the rebuy
never spent it. It reaches no live tranche, no pending pool, no discard
counter and no order. The conservation property fails outright.

**Reproduction:** give a bot three tranches, apply a wire arrival, call
`manual_fire_tranche(1)`, and call `apply_wire_income` from inside the
awaited `_execute_buy`. Loss equals `arrival / len(tranches)` per event.

### Same event twice — undefined

No idempotency key exists. `ref` is free text that repeats
(`scrum@<price>`), and the code stamps `ts` at arrival, so a re-delivered wire
is indistinguishable from a genuine second one and is credited twice. The
self-consistency check reports CLEAN, correctly — the two entries differ
in `ts`. Harmless only while nothing retries.

### Credit larger than the tranche — split correct, consequence unbounded

A $1,000.00 arrival onto one tranche holding $0.01 and 0.005 units
produces `usd` $1,000.01 against unchanged units, a usd/units ratio of
200,002 against a ref of 1.01. The split arithmetic is right. Nothing
compares an arrival against the tranche it lands on, and `usd` is the
manual-fire buy cost, so that tranche would rebuy roughly 200,000 times
the units behind it.

### Already-credited tranche — CORRECT, and the first exercise of the cap

25 arrivals of $1.00 onto one tranche:

```
detail entries kept : 20   (cap is 20)
rolled count        : 5
rolled total_usd    : $5.00000000
rolled by_source    : {SRC0: 2.0, SRC1: 2.0, SRC2: 1.0}
detail + rolled     : $25.00000000   (expected $25.00000000)
```

Lossless. This run is the first exercise of the rolled path
anywhere, production included.

### Absorb then skim — WRONG

This run read `:8782-8798` out of
`src/trading/scrumming_bot.py` by line range and ran it verbatim against
a real bot. The block sits inline in `tick()`, so no caller can reach it,
and re-typing it would test the transcription instead.

```
scrum share $20.00 + pending $343.68 -> tranche usd $363.68   (:8759 absorb)
after the shipped skim block                  -> tranche usd $181.84   (:8792)
provenance still recorded                     -> $343.68

SC5_CREDIT_EXCEEDS_USD: credited $343.68 > usd $181.84 (excess $161.84)
```

`:8759` adds the whole pending pool to the new tranche. `:8784` then
takes `self._fold_tranches[_tranche_count_before:]`, and with
`_tranche_count_before == 0` that is every tranche including the absorbed
one. `:8792` scales it by `scrum_fold_pct/100`. Wire credit that never came from
scrum proceeds retires as cash. The `wire_credits` entries keep
their full `usd`, so the tranche over-states its own balance from the
first instant.

**Reproduction:** a bot with `scrum_fold_pct = 50`, zero tranches and
parked wire credit, then an autonomous scrum. Expect new tranche `usd` =
`scrum_share + pending`; observe `(scrum_share + pending) x 0.5`.

**Live:** 7c39c7a2 (BTC/USD) holds all three conditions right now.
$171.84 of the $343.68 parked would leave the fold queue on its next
autonomous scrum.

## What was NOT determined

1. Whether the GUI passes a fresh `tranche_index` to
   `manual_fire_tranche` after the re-sort at `:11116`. The call site was
   not opened.
2. Which events produced the $354.03 provenance gap. The retained
   diagnostics window is about two days and the loss predates it.
3. Whether the mid-fire race has ever fired in production. No counter
   records it and the log window is too short.
4. The rolled path's production behaviour. It has never run there, so
   “clean” is a statement about the instrument, not the world.

## Evidence

Scripts and raw output under
`<scratchpad>/`:

| script | output | purpose |
|---|---|---|
| `wcv_check.py` | — | the conservation check, both modes |
| `wcv_bot.py` | — | real `ScrummingBot` fixtures |
| `wcv_step1_plants.py` | `wcv_step1_out.txt` | the four planted defects |
| `wcv_step2_live.py` | `wcv_step2_out.txt` | live state, read-only |
| `wcv_step2b_exposure.py` | `wcv_step2b_out.txt` | per-bot exposure |
| `wcv_step3_lifecycle.py` | `wcv_step3_out.txt` | lifecycle hazards |
| `wcv_step4_adversarial.py` | `wcv_step4_out.txt` | adversarial pass |

`coding_archetype` reports `passed=True` on every script above.

Constraints honoured: no product code changed, nothing written under
`~/.acervator` or `~/.acervator_logs`, credentials never opened, no git
operation, no version bump, no island created.
This run read `src/trading/scrumming_bot.py` and never wrote it.
