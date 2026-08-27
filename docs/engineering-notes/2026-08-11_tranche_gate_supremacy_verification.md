# Tranche gate supremacy — verification

**VERDICT: SUPERSEDED.** Fold tranches obey every gate; invisible Stack
tranches obey none of them, because the reconciler that fires them runs
2,089 lines before the gate chain is evaluated. Two unrelated crashes
currently stop that path from placing an order, so the leak is latent
today, not active.

Date: 2026-08-11
Scope: `src/trading/scrumming_bot.py`, `src/trading/gate_chain.py`
Method: executable check driving the real `ScrummingBot.tick()`
Product code changed: none

**Every line number below is anchored to
`scrumming_bot.py` sha256[:16] = `6825c2d55a8e8131` (13,262 lines) and
`gate_chain.py` sha256[:16] = `9a3db06d72738eda` (872 lines).** That
matters here: another job edited `scrumming_bot.py` during this
investigation, moving it from 13,180 to 13,262 lines mid-audit. The
first draft of this report cited the pre-edit numbering and was wrong by
roughly 80 lines in the back half of the file. Every result below was
re-measured against the hash above, and the runner verifies the hash is
unchanged before and after each run, so no result mixes two versions.

---

## 1. The property under test

The operator's requirement:

> Tranches do not supersede any trading gates. They are only 'used' when
> a valid trading condition occurs.

Stated precisely, and this is what the check asserts:

> A tranche is consumed ONLY when the trading condition that would
> authorise the equivalent ordinary trade is satisfied. If every gate
> would refuse a trade right now, NO tranche of either type may be
> consumed right now.

Formally, per tick, with `manual_fire_tranche` the one declared
operator-override exemption:

    consumed_fold_tranche  => fold_chain.evaluate(ctx).should_fire
    consumed_stack_tranche => scrum_chain.evaluate(ctx).should_fire

Tranches change WHAT is traded and at what provenance. They must never
change WHETHER trading is permitted.

## 2. The instrument

`tranche_gate_check.py` builds a real `ScrummingBot` on a stub exchange
and drives the real `tick()`. The gate chain, both stack reconcilers,
both executors and `guarded_place_order` are the shipped objects.
Nothing is transcribed.

The check reports through two surfaces, read where they happen:

| surface | meaning |
|---|---|
| `guarded_place_order` invoked | an order reached the exchange |
| fold queue shrinks | a fold tranche was consumed |
| stack tranche leaves `pending` | a stack tranche was consumed |

Gate refusals are produced by the REAL gates. The check steers one
`GateContext` field so the gate under test blocks, then records the
chain's own verdict. The gate's logic decides; only its input is set.

Two instrument corrections made during construction, both of which had
been silently producing reassuring results:

- **Order attribution.** Orders are attributed by call-stack provenance.
  Without it, a `hedge_replenish` buy landing on the same tick was
  blamed on the fold chain — a false positive, caught and removed.
- **Order success.** An order counts as "reached the exchange" only
  after the exchange accepts it. Recording at call time counted
  pre-flight rejections as placed orders.

## 3. The gate chain

SCRUM chain evaluated at `scrumming_bot.py:8568`, consumed at `:8574`.
FOLD chain evaluated at `:9483`, consumed at `:9487`. Both built at
`:452-453`, imported at `:68`. `GateChain.evaluate`
(`gate_chain.py:752`) runs every gate, applies overrides in a second
pass, and sets `should_fire = (not final_blocked)`.

SCRUM order (`gate_chain.py:818`): `delta_positive`, `interval`,
`ta_bullish`, `trend_hold`, `midline_scrum`, `target_fires`,
`bb_proximity_scrum`, `circuit_breaker_scrum`, `htf_defer_scrum`,
`hysteresis_scrum`, `adx_trend_suppression`, `efficiency_ratio_regime`,
`zscore_extremity`, plus `ripe_harvest_override`.

FOLD order (`gate_chain.py:854`): `tranches_queued`, `ta_bearish`,
`midline_fold`, `smart_ceiling`, `bb_proximity_fold`,
`circuit_breaker_fold`, `htf_defer_fold`, `hysteresis_fold`,
`zscore_extremity`, plus `deep_fold_override`.

## 4. Where each tranche path sits in the chain

Landmark lines, first-visit order captured from a live trace of `tick()`:

    [6479, 6492, 8568, 9483]

| line | what runs | gated? |
|---|---|---|
| 6479 | `_reconcile_stack_tranches_invisible` — can SELL | **no** |
| 6492 | `_reconcile_stack_tranches_visible` — read only | n/a |
| 8568 | SCRUM chain evaluated | — |
| 9483 | FOLD chain evaluated | — |
| 9772 | fold `_execute_buy` | yes, under `:9487` |
| 9841 | fold queue dequeue | yes, under `:9487` |

The reconciler precedes the SCRUM chain by 2,089 lines of the same
function, at the same indentation, under no conditional. The source
explains the position purely as race avoidance — firing a tranche
"doesn't race the SCRUM logic that might otherwise open a new stack on
top." Gate policy is never mentioned. The ordering looks deliberate for
a reason unrelated to gates.

## 5. What `bypass_stack` really does

Innocent. It skips one branch and that branch is not a gate.

`bypass_stack` occurs at `scrumming_bot.py` lines 11833, 12043, 12050,
12072, 12083, 12092 and 12099. Only `:12099` is executable:

```python
if (not bypass_stack
        and getattr(self.config, "stack_mode", False)
        and amount and amount > 0 and price and price > 0):
    _n = await self._open_stack_from_scrum(...)
```

With it False and stack mode on, a SELL is converted into a stack of
pending tranches. With it True the conversion is skipped and execution
falls through to the ordinary single-sell path. It exists to stop a
tranche fire from opening a stack on top of a stack.

Every refusal inside `_execute_sell` (`:12070`) sits BELOW that branch
and runs identically either way: OTD hysteresis `:12132`, capital
reservation `:12183`, P0b stacked-sell `:12253`, Verify-Hit `:12290`.

Measured, driving the reconciler's real `bypass_stack=True` path:

| run | state | result |
|---|---|---|
| control | nothing armed | tranche `pending`→`filled`, 1 order |
| armed | SCRUM OTD hysteresis armed at $149 pivot | tranche stays `pending`, 0 orders |

The armed run emitted `SCRUM REFUSED (opposing hysteresis v3.15.77)`.
The in-executor gates bind under `bypass_stack=True`. The lead was worth
checking and it comes back clean.

## 6. Planted-failure evidence

A gate-supremacy check never seen to fail is worthless. All four plants
were required to turn the check red, and all four did.

| plant | what was planted | check |
|---|---|---|
| 1 | fold tranche consumed while the FOLD chain refused (`ta_bearish`) | **RED** |
| 2 | stack tranche fired while the SCRUM chain refused (`ta_bullish`) | **RED** |
| 3 | fold tranche consumed with the circuit breaker open | **RED** |
| 4 | fold tranche consumed below minimum trade size | **RED** |

Plant 4 needed two attempts, and the first attempt is worth recording.
Setting the advertised exchange minimum high did NOT produce a
violation: `tick()` set `_fold_skipped_below_min`, skipped
`_execute_buy`, and correctly left the queue intact. That is the product
behaving properly, not the check failing. A real bypass required an
exchange whose enforced minimum exceeds its advertised one, paired with
the phantom-fill pattern the MEM-207 comments describe. Only then did
the queue dequeue with nothing placed:

    VIOLATION: 2 fold tranche(s) were consumed but NO buy order
               reached the exchange (tranche burned, no trade)

Converse control (section 9) shows the same check going green on real
consumption, so it discriminates in both directions.

## 7. Per-gate results

Each row: one gate steered to refuse, tranches present, price thresholds
satisfied, real `tick()` driven.

### FOLD — 2 tranches queued, ref $200, price $100 (eligible)

| gate | chain verdict | tranches consumed | result |
|---|---|---|---|
| `tranches_queued` | False | 0 | held |
| `ta_bearish` | False | 0 | held |
| `midline_fold` | False | 0 | held |
| `smart_ceiling` | False | 0 | held |
| `bb_proximity_fold` | False | 0 | held |
| `circuit_breaker_fold` | False | 0 | held |
| `htf_defer_fold` | False | 0 | held |
| `hysteresis_fold` | False | 0 | held |
| `zscore_extremity` | False | 0 | held |

**Fold tranches are fully gated.** Consumption is dominated by
`_fold_chain_result.should_fire` at `:9487`, and the dequeue at `:9841`
only runs after a successful buy — on a None fill the code returns at
`:9804` without dequeuing.

### STACK, invisible — 1 pending tranche @ $120, price $150 (crossed)

| gate | chain verdict | consumed | result |
|---|---|---|---|
| `delta_positive` | False | 1 | **SUPERSEDED** |
| `interval` | False | 1 | **SUPERSEDED** |
| `ta_bullish` | False | 1 | **SUPERSEDED** |
| `trend_hold` | False | 1 | **SUPERSEDED** |
| `midline_scrum` | False | 1 | **SUPERSEDED** |
| `target_fires` | False | 1 | **SUPERSEDED** |
| `bb_proximity_scrum` | False | 1 | **SUPERSEDED** |
| `circuit_breaker_scrum` | False | 1 | **SUPERSEDED** |
| `htf_defer_scrum` | False | 1 | **SUPERSEDED** |
| `hysteresis_scrum` | False | 1 | **SUPERSEDED** |
| `adx_trend_suppression` | False | 1 | **SUPERSEDED** |
| `efficiency_ratio_regime` | False | 1 | **SUPERSEDED** |
| `zscore_extremity` | False | 1 | **SUPERSEDED** |

Every SCRUM gate. In each case the tranche went `pending`→`filled` and a
SELL reached the exchange, with provenance
`_execute_sell` ← `_reconcile_stack_tranches_invisible` ← `tick`.

Run AS SHIPPED, the same 13 rows show 0 consumed — but not because any
gate stopped anything. See finding F2: the path crashes before it can
place an order. The rows above are with that crash repaired in the rig,
which is what the code will do the moment the crash is fixed.

## 8. The reconciler finding — CONFIRMED supersession

### F1 — the invisible stack reconciler runs before the gate chain

`scrumming_bot.py:6479` calls
`_reconcile_stack_tranches_invisible(current_price=ticker.last)` at the
top level of `tick()`, under no conditional. Its only preconditions are
its own (`:12028` invisible, `:12030` stack mode, `:12032` non-empty,
`:12034` price > 0, `:12041` `current_price >= t["price"]`). None is a
trading gate.

The exposure is wider than "the chain refuses". Between `:6492` and
`:8568` there are ten `return` points that abandon the tick, so the
chain is never evaluated at all — and the reconciler has already run.

**Sharpest reproduction — the HARD circuit breaker:**

```
bot with stack_mode=True, visibility="internal",
one pending stack tranche @ $120, market price $150,
bot._cb_hard_tripped = True        # scrumming_bot.py:7381
-> tick exits at line 7382, chain NEVER evaluated
-> stack ['pending'] -> ['filled']
-> SELL 0.5 units placed via
   _execute_sell <- _reconcile_stack_tranches_invisible
```

The system's strongest stop is checked ~900 lines AFTER the reconciler
has already fired. A hard-tripped bot still sells.

Reproduce: `python tranche_gate_check.py reconciler`.

**The design counter-argument, stated fairly.** The tranche price was
fixed at stack-open time by a fully gated SCRUM decision, so firing on a
price crossing is the semantics of a resting limit order — and visible
mode literally IS one, placed at `:11909`. Under that reading the
authority was earned once, at open. Whether that satisfies the operator
is a design call, not a code fact. The operator's wording — used "only
when a valid trading condition occurs" — reads as requiring the
condition AT CONSUMPTION, which invisible mode does not check.

That argument also does not cover the hard circuit breaker. A breaker
exists precisely to revoke previously granted authority.

### F2 — the invisible stack path cannot place an order at all

`_reconcile_stack_tranches_invisible` (`:12023`) passes `summary=None`
at `:12049`. `_execute_sell` dereferences
`summary.consensus_confidence` at `:12325`, inside the "SELL signal:"
emit, BEFORE `guarded_place_order` at `:12332`. The `AttributeError` is
swallowed at `:12364`, emits `SELL FAILED: 'NoneType' object has no
attribute 'consensus_confidence'`, and returns None. Status stays
`pending`, so the bot retries every tick forever.

Reproduced live: the sweep run AS SHIPPED emits exactly that message on
every row. This is what currently masks F1.

### F3 — `self.exchange_interface` does not exist

`scrumming_bot.py:11864`:

```python
min_order = float(getattr(self.exchange_interface, "min_order_size", 0.0) or 0.0)
```

The attribute is `self.exchange` (`bot_container.py:939`).
`exchange_interface` appears exactly once in the whole of `src/` and is
defined nowhere. The `getattr` default protects the inner lookup, not
`self.exchange_interface` itself, so this raises.

Reproduced: with `stack_mode=True`, a SCRUM fire reaches
`_open_stack_from_scrum` (`:11824`) and the `AttributeError` escapes
`tick()` entirely. Stack mode therefore cannot open a stack from a
scrum.

Consequence for F1: F2 and F3 together are why this is latent rather
than active. Neither is a gate. Fixing either without addressing the
ordering turns F1 live.

### Blast radius, measured

From a scratchpad copy of the operator's `bot_state.json` (the live file
was never opened for write):

| measure | value |
|---|---|
| bots | 37 |
| `stack_mode=True` | **0** |
| holding stack tranches | **0** |
| `visibility=internal` | 1 |
| `cb_hard_tripped=True` | 1 (`f9cfb7ba`) |
| holding fold tranches | 24 bots, 630 tranches |

Positive control for that reader: it parses 37 config blocks and 37
`scrumming_state` blocks and finds 630 fold tranches, so its zeros are
earned. An earlier version read the wrong nesting level and reported
zero for everything — a blind instrument returning a reassuring number.

**No live bot can reach F1 today.** One bot is hard-tripped right now,
which is the exact state F1 exploits, but it has stack mode off.

## 9. The converse — the check is not vacuous

| path | gates | threshold | outcome |
|---|---|---|---|
| FOLD | permit | ref $200, price $100 | 2 tranches consumed, 2 buys placed |
| STACK | permit | tranche $120, price $150 | `pending`→`filled`, 1 sell placed |

Both fire. A "no supersession" result from this check is not the result
of nothing ever trading.

## 10. Manual fire

`manual_fire_tranche` (`:3176`) is an operator action and routes through
`_execute_buy` (`:3229`), so the gates inside `_execute_buy` (`:12498`)
still apply to it. An operator override is not a defect. An
undocumented one is.

The operator-facing claim at `:3218`:

> Bypasses TA/OTD/Target-Delta gates; Smart Ceiling + MEM-257 still apply.

### Documented and true

- **TA gates bypassed.** Confirmed: with `ta_bearish` blocking, the
  manual fire still applied and the tranche was consumed. No
  `_fold_chain.evaluate` call exists anywhere in the method.
- **Target-Delta bypassed.** No delta or interval check between index
  validation (`:3191`) and the buy (`:3229`).
- **Smart Ceiling still applies** — MEM-251 v2 Layer 1 breach refusal at
  `:12838`.
- **MEM-257 still applies** — `_verify_buy_safe_or_refuse` at `:12756`.

### F4 — the OTD claim is false

OTD is documented as bypassed. It is enforced.

```
tranche ref $200, price $100,
bot._hyst_armed_fold_side = True
bot._hyst_ref_fold_side   = 101.0
-> manual_fire_tranche(0)
-> applied=False, tranche unchanged, 0 orders
-> "FOLD REFUSED (opposing hysteresis v3.15.77)"
```

`_execute_buy` hits the FOLD-side hysteresis at `:12554` and returns
None at `:12583`. The stale comment at `:12552` — "Manual fire bypasses
(uses guarded_place_order directly)" — is true only of
`_execute_manual_rebalance`, not of `manual_fire_tranche`.

Worse, the returned reason at `:3239` lists Smart Ceiling, MEM-257 and
P0b but NOT hysteresis, so the operator is given a wrong cause after
being told the gate would not apply.

### F5 — the per-tranche price floor is skipped, undocumented

The autonomous path filters tranches by
`ticker.last <= ref * _otd_factor` (`:9576`). That floor is what
guarantees a fold buys BELOW its own sell reference. Manual fire selects
by index (`:3196`) with no price comparison.

```
tranche ref $50, current price $100
-> manual_fire_tranche(0)
-> applied=True, tranche consumed, buy placed ABOVE its own ref
```

The bot rebought at double its sell reference. The code half-knows —
`_mf_profit` at `:3260` goes negative and is floored at zero — but the
skip is never stated to the operator.

### Undocumented skips, not individually reproduced

Also absent from the `:3218` message: the fold per-cycle capital cap
(`:9638`), the MEM-244 taper including its hard stop (`:9672-9704`),
minimum trade size (`:9718-9746`), and the malformed-tranche guard
(`:9507`). Gates that still apply but go unmentioned: operator entry
bounds (`:12601`, `:12609`) and the P0b stacked-buy guard (`:12645`).

## 11. Verdict

**SUPERSEDED**, split by path:

| path | verdict |
|---|---|
| fold tranche consumption | **GATES SUPREME** — 9 of 9 gates held |
| stack, visible | gated at PLACEMENT, never re-gated at fill |
| stack, invisible | **SUPERSEDED** — 13 of 13 SCRUM gates bypassed |
| manual fire | exempt by design; exemption mis-stated (F4, F5) |

The operator's requirement holds for the tranche type that 24 live bots
actually use, and fails completely for the type none of them do.

Nothing here is a live leak today. It is a latent architectural defect
held shut by two crashes, one of which (F3) is a one-word attribute
error. That is not a safety margin.

## 12. Findings summary

| id | finding | file:line | severity |
|---|---|---|---|
| F1 | invisible stack reconciler runs before the gate chain; bypasses all 13 SCRUM gates, including the hard circuit breaker | `scrumming_bot.py:6479` | high, latent |
| F2 | `summary=None` crashes `_execute_sell` before order placement; stack tranche can never fire and retries forever | `scrumming_bot.py:12049`, `:12325` | high, latent |
| F3 | `self.exchange_interface` is undefined; `AttributeError` escapes `tick()` | `scrumming_bot.py:11864` | high, latent |
| F4 | OTD documented as bypassed by manual fire but enforced; refusal reason omits it | `scrumming_bot.py:3218`, `:12554` | medium |
| F5 | per-tranche price floor skipped by manual fire, undocumented; allows rebuy above ref | `scrumming_bot.py:3196`, `:9576` | medium |
| F6 | `gate_chain.py` docstring claims the module is dead code; it is imported at `scrumming_bot.py:68` and evaluated at `:8568` and `:9483` | `gate_chain.py:30` | low |

No repairs were made. Each lands in its own cascade.

## 13. Falsification

This report is wrong if: the steered `GateContext` misrepresents what
`tick()` would build, so the recorded refusals are not reachable from
real market data; the stub exchange diverges from the live connector in
a way that changes control flow before `:6479`; the rig-side repair of
F2 changes more than the crash; or `stack_mode` proves reachable on a
live bot by a path not visible in `bot_state.json`.

The check itself is falsified if any of the four plants stops turning it
red, or if the converse stops showing consumption.

Line numbers are falsified by any edit to `scrumming_bot.py` after
sha256[:16] `6825c2d55a8e8131`. Re-resolve with `locate.py`, which finds
every cited construct by content and refuses ambiguous anchors.
