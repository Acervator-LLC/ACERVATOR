# tick() extraction — investigation and recommendation

Reference. 2026-08-04, against v3.24.26.

**Recommendation: do not extract. No functional defect motivates it.**

## Why it was on the docket

`ScrummingBot.tick()` is 4,038 lines (`scrumming_bot.py:4629-8666`).
An AST walk confirms the structural claim that put it on the list:

| fact | value |
|---|---:|
| `return` statements in `tick()` | 28 |
| first `_last_gate_state` write | line 6823 |
| returns **before** that write | **27** |
| returns after it | 1 |

The hypothesis was that 27 early exits meant most ticks — and some
trades — recorded no gate fixture, which would explain the incomplete
gate coverage seen in the trade history and would make the extraction a
correctness fix rather than a cosmetic one.

## The hypothesis is false

Measured against a real 6-asset / 900-candle replay on Stone Tablet data
(5,400 bot-ticks, 20 trades):

| metric | value |
|---|---:|
| ticks with a gate fixture present | **5,400 (100%)** |
| trades with a fixture present | **20 of 20** |
| trades whose fixture carries `evaluated_at_tick` | **20 of 20** |

`_last_gate_state` **persists across ticks**. It is set once and updated
in place, so a bot that exits through one of the 27 early returns retains
its previous fixture rather than losing it. The early returns do not
create gaps in gate data.

## Two measurement errors, both caught

Recording these because the first two runs produced confident, wrong
numbers, and only re-verification distinguished them from the third.

1. **`id()` comparison.** The first probe detected fixture writes by
   comparing `id(self._last_gate_state)` before and after each tick. The
   fixture is mutated in place, so its identity never changes. Result:
   *"0 of 5,400 ticks wrote gate state (0.0%)"* — a fabricated 100%
   failure rate. Caught by checking the attribute directly after a run
   and finding a fully populated dict.

2. **Content comparison.** The second probe compared serialised dict
   contents. That detects *change*, not *presence*, so a fixture written
   with values identical to the previous tick counted as absent. Result:
   *"93.1% of ticks absent, 6 of 20 trades without a gate write"* — still
   wrong, in a subtler and more plausible direction.

Only the third probe — testing presence and the `evaluated_at_tick`
marker — answered the question that was actually being asked.

The general lesson: for state that is mutated in place and persists
across calls, "did it change" and "is it there" are different questions,
and the wrong one produces a confident number.

## What remains as justification

Maintainability alone. That is real — 4,038 lines with 28 exits is hard
to reason about — but it is not what the docket entry claimed, and it
runs directly into the standing rule:

> "Bug fixes only fix the bug. Don't refactor, don't add scaffolding,
> don't create abstractions for hypothetical futures."

## Cost side

- The method is live money code. Every scrum and fold decision runs
  through it.
- The complexity audit's throughput findings were **elsewhere** and are
  all shipped (v3.24.20-v3.24.25). Extraction buys no measured
  performance.
- A restructure of this size cannot be verified bit-identically the way
  the TA changes were: TA has pure functions with comparable outputs,
  whereas `tick()` mutates bot state, places orders and emits events.
  The strongest available check is the existing suite plus replay
  comparison, which is weaker than what was used for changes far smaller
  than this.

## If it is ever done anyway

Sequence that reduces the risk rather than pretending it is absent:

1. Build a replay-parity harness first — run N assets before and after,
   compare the full trade sequence (timestamp, side, amount, price) and
   the per-tick gate fixtures. Extraction is only safe if that harness
   shows zero divergence.
2. Extract in the direction of the 27 early returns: hoist the
   *guard clauses* into a `_tick_preconditions()` that returns a reason
   or `None`. That shrinks the method substantially, is mechanical, and
   leaves the decision logic untouched.
3. Do not touch the gate-fixture write or anything downstream of it in
   the same cascade, so a parity divergence bisects cleanly.

## Falsification

This recommendation is wrong if any of the following turns out true:

- A replay shows trades whose fixture `evaluated_at_tick` does not match
  the firing tick (a stale fixture attached to a live decision). The
  probe above checked presence, not freshness against the firing tick.
- Gate coverage gaps in the *live* trade history trace to `tick()` rather
  than to the gate.log writer stall of 2026-06-11, which is the current
  leading explanation and is a separate live-side defect.
- Profiling shows `tick()`'s own control flow — not the TA it calls — as
  a material cost.
