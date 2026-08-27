# Tranche consumption at and beyond the price threshold

Reference — a verification record for the fold and stack consumption
paths, with the sweep that produced each number.

**One line:** Both types consume a tranche that sits EXACTLY at its
threshold, so the boundary is correct; but the fold path then refuses most
eligible tranches on a per-cycle cap that counts the wrong unit, and it
skips 6 of the 9 tranches eligible right now on the live fleet.

| Type | Verdict | Basis |
|---|---|---|
| FOLD | **DEFECTIVE** | Boundary correct (0 of 3,481 sweep probes disagree). Consumption path violates conservation on 115,964 of 3,936 full-path sweep passes. 6 of 9 live-eligible tranches skipped. |
| STACK | **UNEXERCISED** | Boundary correct (0 of 387 sweep probes disagree). `stack_mode` is False on 37 of 37 bots and 0 stack tranches exist fleet-wide. The path has never run in production. |

Date: 2026-08-11. Investigation only. This work changed no product code.

---

## 1. The two mechanisms

### 1.1 Fold tranches

`src/trading/scrumming_bot.py:560` declares `_fold_tranches`. A fold tranche
starts on a SELL and holds the proceeds until price falls far enough to buy
the units back cheaper.

The eligibility filter is `src/trading/scrumming_bot.py:9492-9495`:

```python
_eligible = [
    t for t in self._fold_tranches
    if ticker.last <= float(t.get("ref", 0)) * _otd_factor
]
```

The executor computes the threshold factor once at
`src/trading/scrumming_bot.py:9182-9191`:

```python
_otd_pct_for_gate = max(0.0, min(50.0, _otd_pct_for_gate))
_otd_factor = 1.0 - (_otd_pct_for_gate / 100.0)
```

`t["ref"]` is the sell fill price recorded at tranche creation. No rounding
happens between the multiply and the compare. The comparison price is
`ticker.last`.

Eligible tranches are then filtered a second time by a per-cycle capital cap
at `src/trading/scrumming_bot.py:9532-9585`, sorted highest cost first, and
removed from the queue at `src/trading/scrumming_bot.py:9758-9760`.

### 1.2 Stack tranches

`src/trading/scrumming_bot.py:571` declares `_stack_tranches`. A stack
tranche is a resting SELL placed above the scrum price, built by
`src/trading/stack_math.py` and extended at runtime with a `status` field.

The fire gate is `src/trading/scrumming_bot.py:11956-11960`:

```python
for t in self._stack_tranches:
    if t.get("status") != "pending":
        continue
    if current_price < float(t["price"]):
        continue
```

The skip test is strict `<`, so the fire condition is `current_price >=
t["price"]`. Stack-open time fixes `t["price"]`, and nothing recomputes it.
This side carries no cap, no budget and no per-tick limit: every pending
tranche at or above the price fires in one pass.

Consumption differs between the types. The fold path REMOVES the tranche
from the list. The stack path only MARKS it
(`src/trading/scrumming_bot.py:11971-11972`) and stays in the list for the
life of the bot.

---

## 2. The boundary verdict

The operator asked whether both types consume tranches "at or beyond their
respective price thresholds". "At" is the question, because it turns on
whether the comparison is strict.

**FOLD — the executor consumes a tranche exactly at its threshold.** The operator
at `src/trading/scrumming_bot.py:9494` is `<=`, so `ticker.last == ref *
_otd_factor` is eligible.

**STACK — the reconciler fires a tranche exactly at its threshold.** The skip at
`src/trading/scrumming_bot.py:11959` is strict `<`, so equality does not
skip and `current_price == t["price"]` fires.

**The two types agree.** Both are inclusive at the boundary. The
directions are opposite — fold buys when price falls to or below its
threshold, stack sells when price rises to or above its threshold — but the
inclusivity is the same on both sides. The types show no inconsistency to
report.

Both are correct as written. Neither needs a repair.

### 2.1 A caveat on reachability

`ref` is an exchange fill price and sits on the venue tick grid. `ref *
_otd_factor` generally does not. An exact equality between `ticker.last` and
either threshold is therefore rare on live data, so the `<` versus `<=`
choice is almost never the binding question in production. The cap is.

---

## 3. Evidence that the check works

A clean result means nothing until the instrument demonstrates that it can
go red. Each check therefore ran against a planted defect of every kind it
exists to catch, on a fixture the real source passes.

### 3.1 How the check reads the real code

The harness does NOT transcribe the predicates. It lifts the real decision
source out of `src/trading/scrumming_bot.py` by anchor string, materialises
it verbatim into a generated module, and imports it. A transcription would
encode the same mental model as the code and would agree with itself. Every
run prints the resolved spans:

```
OTD     lines 9182-9191
ELIG    lines 9492-9495
CAP     lines 9532-9585
BUY     lines 9612-9617
REMOVE  lines 9758-9760
```

The stack side runs the real
`ScrummingBot._reconcile_stack_tranches_invisible` through
`inspect.getsource`.

### 3.2 The conservation property

FOLD: after a pass at price P, every tranche t with `P <= t["ref"] *
_otd_factor` has been removed from `_fold_tranches` and its full `t["usd"]`
deployed into the rebuy, and no tranche failing that predicate has been
removed.

STACK: after a pass at price P, every tranche with `status == "pending"` and
`P >= t["price"]` has been marked filled for its full `t["size"]`, and no
tranche failing that predicate has been marked.

### 3.3 The planted-failure table

A plant row MUST read FAIL. Reproduce with `python tc_step1_plants.py`.

| Type | Case | Result | Violations raised |
|---|---|---|---|
| FOLD | known-good fixture, real source | **PASS** | 0 |
| FOLD | PLANT at-threshold skipped (`<` for `<=`) | **FAIL** | 1 × V1_SKIP |
| FOLD | PLANT ineligible consumed (threshold widened) | **FAIL** | 1 × V2_OVERREACH |
| FOLD | PLANT consumed twice | **FAIL** | V3_DOUBLE + V4_CAPITAL |
| FOLD | PLANT partial remainder (half deployed, all removed) | **FAIL** | 1 × V4_CAPITAL |
| STACK | known-good fixture, real source | **PASS** | 0 |
| STACK | PLANT at-threshold skipped (`<=` for `<`) | **FAIL** | S1_SKIP + S4_PARTIAL |
| STACK | PLANT ineligible consumed | **FAIL** | 1 × S2_OVERREACH |
| STACK | PLANT consumed twice | **FAIL** | S3_DOUBLE + S4_PARTIAL |
| STACK | PLANT partial remainder | **FAIL** | 2 × S4_PARTIAL |

Each plant raises its own discriminating violation class, so the check
distinguishes the four defect kinds rather than reporting one blanket
failure.

### 3.4 The instrument was blind on its first run — three of eight

This section matters more than the table above it. The first run of the
table above produced this:

```
[PASS] FOLD  PLANT P2_ineligible_consumed   0 violations   <-- INSTRUMENT BLIND
[PASS] STACK PLANT P2_ineligible_consumed   0 violations   <-- INSTRUMENT BLIND
[PASS] STACK PLANT P3_consumed_twice        0 violations   <-- INSTRUMENT BLIND
```

Two distinct causes, both real:

1. **Fixture defect (both P2 rows).** The plant widened the threshold by
   2%, but the nearest ineligible tranche in the fixture sat 100% away.
   Nothing was in range to be wrongly swallowed. Fixed by adding a
   near-miss tranche whose threshold lands 0.1% below the pass price.
2. **Inert plant (stack P3).** The plant doubled the loop, but the first
   visit writes `status = "filled"` and the pending guard at
   `src/trading/scrumming_bot.py:11957` absorbs the second visit. The
   plant could not double-fire. Fixed by also weakening the guard, which
   models a duplicated reconcile call.

Accepting those three greens would have left the sweep in section 4 with no
evidence that it can detect an over-consuming predicate at all. The fix went
into the instrument, not the verdict.

---

## 4. The sweep

An enumerated table does not close a numeric domain. This decision turns on
a price threshold and a comparison operator, so this check sweeps the price
domain.

Domain: 14 price scales from 1.234e-08 (memecoin) through 1.0, 250.0 and
64000.0 to 105000.0 (BTC), crossed with 9 interval percentages. The live
state carries only `scrumming_interval_pct` of 1.0 and 5.0; the sweep also
covers 0.0, 0.25, 0.5, 2.0, 10.0, 25.0 and 50.0 so a scale-dependent defect
cannot hide in a band nobody has configured yet.

Probes around every computed threshold: the three algebraically identical
spellings of "exactly at" (`ref*(1-p/100)`, `ref - ref*p/100`,
`ref*(100-p)/100`), the four nearest representable floats on each side via
`math.nextafter`, a cent either side, relative offsets from 1e-12 to 1e-2
either side, and the 8-decimal display grid the GUI renders on with its own
float neighbours.

### 4.1 Boundary in isolation (cap given slack)

| Sweep | Combinations | Consumed | Skipped | Disagreements |
|---|---|---|---|---|
| FOLD, real source `:9494` | 3,481 | 1,952 | 1,529 | **0** |
| FOLD, positive control: plant `<` for `<=` | 3,481 | 1,504 | 1,977 | **448** |
| FOLD, positive control: threshold widened | 3,481 | 3,399 | 82 | **1,447** |
| STACK, real source `:11959` | 387 | 222 | 165 | **0** |
| STACK, positive control: plant `<=` for `<` | 387 | 169 | 218 | **106** |
| STACK, positive control: threshold widened | 387 | 381 | 6 | **159** |

The two zeros are claims about the sweep, so they are reported beside the
sweep's own positive controls. Both controls fired on both types, at the
smallest scale first: the first fold control disagreement is `ref=1.234e-08,
otd=0.0, probe=exact_mul`, and the first stack control disagreement is
`price=1.234e-08, probe=exact_mul`. The sweep can detect a one-operator
change at the boundary, and it detects none in the real source.

### 4.2 Full path over the live tranche lists

The section above gave the cap unlimited slack to isolate the boundary. This
sweep restores the real per-cycle cap and asks the operator's actual
question. Reproduce with `python tc_step2b_fullpath.py`.

| Sweep | Passes | Consumptions | Eligible but skipped | Disagreements |
|---|---|---|---|---|
| Real cap active (`:9532-9585`) | 3,936 | 111,330 | 115,964 | **115,964** (all V1_SKIP) |
| Control: cap given unlimited slack | 3,936 | 227,294 | 0 | **0** |

Removing only the cap takes the fold path from 115,964 violations to zero.
The cap is the whole of the violation. That exonerates the boundary
comparison, and the sort order with it.

---

## 5. Why the cap refuses eligible tranches

### 5.1 The defect

`src/trading/scrumming_bot.py:9532-9556`:

```python
_max_growth_pct = float(getattr(self.config, 'max_target_growth_pct', 1.0))
_cycle_cap_usd = (self._anchor_target_balance * _max_growth_pct / 100.0)
_cap_remaining_for_queue = max(0.0, _cycle_cap_usd - self._fold_cycle_cap_consumed)
for _t in _elig_sorted:
    _tranche_usd = float(_t.get('usd', 0) or 0)
    if _running_usd + _tranche_usd <= _cap_remaining_for_queue:
```

The budget counts TARGET-GROWTH dollars. Only `_growth_applied` increments
`_fold_cycle_cap_consumed`, at `src/trading/scrumming_bot.py:1643`. The
admission test at `src/trading/scrumming_bot.py:9556` spends that budget on
`_t['usd']`, the tranche's full parked CAPITAL. Surplus is a small fraction
of capital, so the gate weighs a whole tranche against a budget sized for
its profit.

The consequence is a permanent stall, not a delay. If `t['usd'] >
_cycle_cap_usd` then the admission test is false even with a completely
fresh cap, because `_cap_remaining_for_queue` can never exceed
`_cycle_cap_usd`. The cap does reset each cycle
(`src/trading/scrumming_bot.py:7551-7554` and `:8682-8684`), so this is not
a spent-budget problem. And `src/trading/scrumming_bot.py:9559-9562`
explicitly refuses to split the tranche.

### 5.2 Reproduction, live and right now

Live snapshot `~/.acervator/bot_state.json`, saved 2026-08-11 20:00:26,
read-only. Nine tranches qualify fleet-wide at each bot's own last price.
The executor consumes three.

```
XRP/USD   price=1.0204  cap=$0.75
   eligible usd=$ 0.425 ref=1.0976  thr=1.0427199999999999  FITS
   eligible usd=$ 2.005 ref=1.082   thr=1.0279             EXCEEDS FULL CAP
   eligible usd=$ 0.846 ref=1.082   thr=1.0279             EXCEEDS FULL CAP
   eligible usd=$ 0.004 ref=1.082   thr=1.0279             FITS
   eligible usd=$ 0.976 ref=1.1363  thr=1.079485           EXCEEDS FULL CAP
   eligible usd=$ 1.786 ref=1.0976  thr=1.0427199999999999 EXCEEDS FULL CAP
   -> eligible=6 fired=2 deployed=$0.4287  violations=4 V1_SKIP

BICO/USDC price=0.037157 cap=$0.50
   eligible usd=$ 1.769  EXCEEDS FULL CAP
   eligible usd=$ 1.519  EXCEEDS FULL CAP
   -> eligible=2 fired=0 deployed=$0.0000  violations=2 V1_SKIP

FLEET NOW: eligible=9  actually consumed=3  skipped=6
```

### 5.3 The drain test

This test gives the fold path the most favourable market that exists: price
effectively zero, so every tranche qualifies, with the cap reset to full
every cycle, for 10,000 cycles.

```
FLEET: 652 tranches / $185.43 queued
AFTER 10,000 maximally-favourable cycles:
   69 tranches / $98.58 STILL QUEUED (53.2% of parked fold capital)

CAP/USD    22 of  61 stuck  $24.29  cap $0.50
PUMP/USD   13 of  22 stuck  $23.79  cap $0.50
ALLO/USDC   3 of   8 stuck  $10.04  cap $1.25
RAVE/USD    6 of  12 stuck  $ 7.23  cap $0.50
LINK/USD    6 of  29 stuck  $ 6.02  cap $0.75
XRP/USD     4 of   6 stuck  $ 5.61  cap $0.75
ADA/USDC    4 of   4 stuck  $ 5.24  cap $0.25
```

The autonomous path cannot consume 53.2% of parked fold capital at ANY
price. Price is not the binding constraint.

### 5.4 The queue-versus-drain arithmetic

```
CAP/USD   cap $0.50/cycle, mean tranche $0.51 -> 0 admitted per cycle; 61 queued, 22 never fit
PUMP/USD  cap $0.50/cycle, mean tranche $1.18 -> 0 admitted per cycle; 22 queued, 13 never fit
ADA/USDC  cap $0.25/cycle, mean tranche $1.31 -> 0 admitted per cycle;  4 queued,  4 never fit
LINK/USD  cap $0.75/cycle, mean tranche $0.43 -> 1 admitted per cycle; 29 queued,  6 never fit
```

On CAP/USD, PUMP/USD and ADA/USDC the mean tranche is larger than the entire
per-cycle cap, so the cap admits the mean tranche zero times per cycle. The
drain rate stays below one tranche per cycle while creation runs unbounded
at `src/trading/scrumming_bot.py:8740`. The queue can only grow.

---

## 6. The item-7 hypothesis, answered with numbers

Item 7 reports scrum-fold pairs not collapsing, with over-allocation at
1.28x fleet-wide, BONK 1.78x, SPK 1.74x and KAT 1.55x. Non-consumption
and non-collapse look identical from outside, so this section tests the
hypothesis directly.

### 6.1 On the three named bots, non-consumption explains NONE of it

| Bot | Tranches | Eligible now | Never-fit | Queued | Measured ratio |
|---|---|---|---|---|---|
| BONK/USD | 0 | 0 | 0 | $0.00 | 1.012 |
| SPK/USD | 0 | 0 | 0 | $0.00 | 1.014 |
| KAT/USD | 34 | 0 | 0 | $5.09 | 1.045 |

BONK/USD and SPK/USD hold **zero** fold tranches in this snapshot. KAT/USD
holds 34, none eligible and none too large for its $2.00 cap. Whatever
drives the reported ratios on these three bots, it is not tranche
non-consumption. The named bots do not support the hypothesis.

### 6.2 On other bots it explains a large minority

The bots where non-consumption does bite are different ones:

| Bot | Ratio | Tranches | Never-fit | Stuck capital | Cap |
|---|---|---|---|---|---|
| CAP/USD | 1.581 | 61 | 22 | $24.29 | $0.50 |
| PUMP/USD | 1.484 | 22 | 13 | $23.79 | $0.50 |
| ADA/USDC | 1.195 | 4 | 4 | $5.24 | $0.25 |
| LINK/USD | 1.180 | 29 | 6 | $6.02 | $0.75 |
| RAVE/USD | 1.167 | 12 | 6 | $7.23 | $0.50 |

Excess over target on bots above 1.0x: **$211.60**. Never-fit tranche
capital on those same bots: **$93.62**, which is **44%** of the excess.

### 6.3 The answer

Non-consumption explains **PART**, not all, and specifically **none of the
three bots item 7 names**.

- On BONK, SPK and KAT: **0%**. They hold no stuck tranche capital.
- On the fleet: 44% of the measured excess over target is capital parked
  in tranches the executor cannot consume at any price. The other 56% is not
  accounted for here and needs the item-7 collapse investigation.

### 6.4 The 1.28x figure did not reproduce

The metric above, stated explicitly: `(stats.position_value +
sum(tranche.usd)) / scrumming_state.target_balance`. On this snapshot it
gives **1.060** fleet-wide ($3,652.66 / $3,445.62), not 1.28. The worst
offenders on this metric are CAP/USD at 1.581 and PUMP/USD at 1.484, not
BONK and SPK.

Different snapshot, different offenders, and possibly a different formula.
The definition behind 1.28x is not recorded anywhere I could find. Anyone
reconciling these two numbers needs that definition first. The 44% share
above rests on MY metric, not the reported one.

---

## 7. Other defects found on the consumption path

These surfaced while answering the boundary question. This report names
them; it repairs nothing.

### 7.1 The GUI calls a tranche eligible that the executor will never consume

`src/gui/bot_live_settings.py:2050-2057` renders each tranche's Status from
`cur_price <= ref * (1 - OTD/100)` alone. That render carries no cap term —
lines 2000-2100 contain zero references to `max_target_growth_pct` or the
cycle cap. A tranche that can never fit the cap displays as **"Price-OK"**.

Measured on the live snapshot: **6 tranches** currently show "Price-OK"
while exceeding their bot's full per-cycle cap. The GUI tells the operator
these will fold back. They will not. That is the exact reading under which
non-consumption resembles non-collapse.

### 7.2 Removal is by value, and a comment says otherwise

`src/trading/scrumming_bot.py:9759`:

```python
self._fold_tranches = [t for t in self._fold_tranches if t not in _eligible]
```

`not in` invokes dict `__eq__`. Two value-identical tranches are
indistinguishable, so if the cap admits one and refuses its twin, the
comprehension drops BOTH and the rebuy pays for only one.

The same shape is at `src/trading/scrumming_bot.py:3288` in
`manual_fire_tranche`:

```python
self._fold_tranches.remove(tranche)
```

`list.remove` also uses `==`. The comment directly above it at
`src/trading/scrumming_bot.py:3279-3280` says "Remove the tranche BY
IDENTITY ... identity is safe". **The comment is false.**

Blast radius, measured: **0 duplicate-by-value tranches across all 652 live
tranches**. `created_ts` discriminates in practice. Report as a latent
hazard with a false comment, not a live loss. The mismatch log at
`src/trading/scrumming_bot.py:9767-9772` detects the symptom but only logs
it; nothing restores the loss.

### 7.3 Two latent partial-consumption paths

- **Fold taper.** `buy_cost = _fusd * _taper` at
  `src/trading/scrumming_bot.py:9617` can size the buy at 10% of the
  eligible USD, while `src/trading/scrumming_bot.py:9759` removes ALL
  eligible tranches regardless. Up to 90% of tranche capital would be
  discarded with no record. LATENT: `position_ceiling_enabled` is False
  on all 37 bots, so `fold_rate_taper` returns 1.0.
- **Stack partial fill.** `_execute_sell` returns a fill PRICE, not a
  filled amount, so a partial exchange fill is invisible to
  `src/trading/scrumming_bot.py:11970-11972`, which marks the tranche
  fully filled. The visible variant at
  `src/trading/scrumming_bot.py:11922-11925` books "filled" whenever
  `_filled > 0`, even below `t["size"]`. LATENT: no bot runs stack mode.

### 7.4 Stack tranches are never pruned

Nothing removes an entry from `_stack_tranches`. The only writes are
`.append` at `src/trading/scrumming_bot.py:11854` and the rebuild on state
import at `src/trading/scrumming_bot.py:4971-4973`. Filled and cancelled
entries persist for the life of the bot, and every save writes them to
`bot_state.json` in full. The GUI filters by status for display, so operator
counts stay correct, but the list and the state file grow without bound.
This is an accumulation mechanism specific to the stack type and independent
of the boundary.

---

## 8. Scope and limits

- Read-only. This work changed no product code and created no island.
  It reads `src/trading/scrumming_bot.py` and never writes it, because
  another job is editing that file.
- A copy of `~/.acervator/bot_state.json` went to the scratchpad, and
  every read happened there. Nothing opened the live file for writing.
  Nothing opened the credentials file at all.
- Every stack finding is code reading plus synthetic sweep. `stack_mode`
  is False on 37 of 37 bots and 0 stack tranches exist, so none of it has
  faced a real exchange. That is why the stack verdict is
  UNEXERCISED and not CORRECT.
- All 37 bots report `current_holdings == 0` in the saved state, so
  position figures fall back to the persisted `stats.position_value`. The
  dollar over-allocation figures are indicative. The never-fit tranche
  figures do not depend on that field and stand on their own.
- This work could not determine whether the unit mismatch at
  `src/trading/scrumming_bot.py:9556` is deliberate. The comment block at
  `src/trading/scrumming_bot.py:9516-9528` quotes the operator on
  soft-capping "deployed fold-back capital", which reads as capital;
  only growth feeds `_fold_cycle_cap_consumed`, which reads as
  growth. The code implements one reading on each side of the same
  subtraction. This needs an operator ruling before anyone repairs it,
  and it is the highest-value open question in this report.
- This work did not repair item 7.

## 9. Reproduction

The scripts are read-only and live under the session scratchpad.

| Script | Produces |
|---|---|
| `tc_harness.py` | Lifts the real decision source; the two conservation properties |
| `tc_step1_plants.py` | The planted-failure table in section 3.3 |
| `tc_step2_sweep.py` | The boundary sweep in section 4.1 |
| `tc_step2b_fullpath.py` | The full-path sweep in section 4.2 |
| `tc_step4_live.py` | The drain test and per-bot table in section 5 |
| `tc_step4b_detail.py` | The live eligibility detail and item-7 numbers |

Run with `PYTHONIOENCODING=utf-8 python <script>`. Each exits 0 on a clean
instrument and 1 when a control fails to fire.
