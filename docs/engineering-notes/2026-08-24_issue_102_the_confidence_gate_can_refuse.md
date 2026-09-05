# Issue #102 — the confidence gate can refuse

**Unit:** the BB-priority arm of the TA confidence gate in
`ScrummingBot.tick()`.
**Branch:** `issue-102-the-confidence-gate-can-refuse`.
**Base:** `b91fb83`, v3.26.0.
**Date:** 2026-08-24.

---

## 1. What the code was trying to do, from its own record

The commit history is squashed, so `git blame` says nothing. The record
is in three places and it is complete.

**The operator's directive, 2026-04-26, verbatim, recorded at
`docs-archive/llm-session-history/DEVELOPMENT_CHRONICLE.md:15064-15068`:**

> Original: "Need to have logic gate prioritization. BB proximity and /
> or contact should immediately trigger or heavily favor a trade if
> Minimum Opposing Trade Distance is also satisfied and a Target Delta
> is available."
>
> Refinement: "Should skew TA confidence, not over ride as this seems
> dangerous."

**What the author built first, recorded at `:15093-15098`:**

> First attempt was a hard override: I added `_bb_priority_scrum` /
> `_bb_priority_fold` clauses to the SCRUM/FOLD if-conditions, which
> would fire the trade even when TA was actively contradicting. Operator
> caught the safety risk … Reverted that, replaced with the
> confidence-skew approach.

**What the author built second, and how it was sized, at `:15105-15109`:**

> `+0.30` amount: enough to lift any low-confidence NEUTRAL reading
> (0.0–0.24) over the 0.25 threshold … 0.30 is the minimum useful skew
> that actually changes behavior.

The intent is therefore not ambiguous. The arm is a PRIORITISATION —
the operator's own word is "favor" — and the refinement is a ruling that
it must not become an override.

## 2. What the code actually did

```
eff_confidence = max(0.0, min(1.0, eff_confidence + 0.30))
...
is_bullish = (eff_direction in (BULLISH, NEUTRAL)
              and eff_confidence >= _TA_CONFIDENCE_FLOOR)   # 0.25
```

`conf + 0.30 >= 0.25` is `conf >= -0.05`. The indicator output is
bounded [0, 1] (`ta_engine.py` returns `round(min(1.0, abs(net) /
voted_weight), 4)`), so no reading fails it, including exactly 0.0.

**The second attempt is the first attempt.** The clauses were removed
from the if-line and the same unconditional pass was re-created in
arithmetic. The author's sizing rule says so in as many words: a skew
chosen to clear the whole [0.0, 0.24] band IS the override the operator
refused.

**A second defect in the same line.** The chronicle also required the
skew to be "not so large that it inflates already-confident readings
into something deceptive". The addition inflated every reading, and the
inflated number was what nine sites in `tick()` printed — including the
`HOLD FOLD` explainer whose entire job, since v3.24.43, is to name the
conjunct that failed. The audit trail reported a confidence no indicator
produced.

### One qualification, measured rather than assumed

`eff_confidence` is not the raw indicator output. Two additive
adjustments reach it first: `position_boost` (`:8026`, range
[−0.29, +0.40]) and `bb_confidence_boost` (`:8166`, range [0, +0.60]).
A sufficiently negative `position_boost` can drive `eff_confidence`
below −0.05, and then the BEFORE gate does refuse.

Measured over the 406 tablets: the BEFORE arm refused **71 of 1,800**
arm rows (3.9 %). Every one of the 71 carries a `position_boost` between
−0.08 and −0.18 and a `bb_confidence_boost` of 0.00. They are named in
full in `2026-08-24_issue_102_evidence/sweep_result.md`.

The precise statement is therefore this: **the BEFORE gate could refuse
only a reading that a DIFFERENT additive adjustment had already driven
negative.** For every reading the indicators actually produced, it could
not refuse. That is the defect, and the 3.9 % is not a mitigation — it is
a second instance of the same class showing through.

## 3. The shape chosen, and why

**Shape 1 and shape 2 converge here, so both are taken.** The favour is
expressed as a routing rule (shape 1: the measured confidence is left
alone) and it lands on the arm's own documented threshold (shape 2: a
floor that can still refuse).

```python
_BB_PRIORITY_SKEW = 0.30
_BB_PRIORITY_CONFIDENCE_FLOOR = _TA_CONFIDENCE_FLOOR / (1.0 + _BB_PRIORITY_SKEW)
```

```python
_bb_priority_arm = _bb_priority_scrum_skew or _bb_priority_fold_skew
_eff_conf_floor = (_BB_PRIORITY_CONFIDENCE_FLOOR if _bb_priority_arm
                   else _TA_CONFIDENCE_FLOOR)
...
is_bullish = (eff_direction in (BULLISH, NEUTRAL)
              and eff_confidence >= _eff_conf_floor)
```

Four properties, and each answers something in the record:

1. **`eff_confidence` is never edited by this arm.** A confidence is an
   indicator output. The nine diagnostics below now print the measured
   value, and the `HOLD FOLD` explainer quotes the floor that actually
   applied.
2. **The relaxation is PROPORTIONAL, not subtractive, and that is what
   restores refusal.** Subtracting the same 0.30 from 0.25 lands at
   −0.05, clamps to 0.0, and is the tautology again. Dividing preserves
   zero: whatever the favour, a reading of exactly 0.0 is refused. The
   arm's floor is 0.25 / 1.30 = **0.1923**.
3. **It is also what the operator's word means.** A skew SCALES. A shift
   OFFSETS. v3.15.64 shipped a shift and called it a skew.
4. **No new number is introduced.** The floor is derived from the two
   constants already of record — the 0.25 floor and the 0.30 favour. The
   magnitude of the favour is unchanged; only its form and its target
   are. If the operator wants a different magnitude it is one constant,
   and the derivation moves with it.

**What is deliberately not changed.** The direction conjunct still gates
the trade. Actively-contradicting TA still refuses, exactly as v3.15.64
preserved it. The non-priority arm keeps `_TA_CONFIDENCE_FLOOR`
untouched.

## 4. The defect class — every other gate of this shape

An exhaustive scan of `src/` for an additive adjustment to a BOUNDED
quantity preceding a fixed-threshold boolean gate. Repaired: the
Bollinger one only. **Named, not repaired:**

- **`scrumming_bot.py:8026` — `eff_confidence += position_boost`.**
  Reachable maximum +0.40 against the same 0.25 floor (vortex +0.12,
  macd +0.08, ichimoku +0.05, stochRSI +0.10, market structure +0.05,
  all simultaneously satisfiable); at ≥ 0.25 of boost the conjunct
  reduces to `conf >= 0.0` and CANNOT REFUSE. Measured maximum on the
  tablets: **+0.40**.
- **`scrumming_bot.py:8166` — `eff_confidence += bb_confidence_boost`.**
  Reachable maximum +0.60 (landing strip 0.15–0.35 at `:7864`, plus
  tightening 0.08–0.25 at `:7888`, independent), against the same 0.25
  floor; tightening alone reaches 0.25 and CANNOT REFUSE. Measured
  maximum on the tablets: **+0.1437** — its ceiling was not reached by
  this tape set, which is why the sweep does not show it biting.

Nothing else in `src/` matches the shape. Checked and rejected with
reasons: `indicators/rsi.py:176,178` and `indicators/slingshot.py:416,420`
(+0.15 clamped, but the nearest thresholds are 0.3/0.5/0.7 — still
refuses); `indicators/ichimoku.py:281` and `indicators/volume.py:334`
(the `+=` literals BUILD the score, they do not adjust a prior
measurement); `triangular_swarm.py:186` (a convex weight, and
`mr_penalty` reaches 0.0); all of `gate_chain.py` (precomputed booleans,
no adjustment); `stocks/stock_accumulation_bot.py:268` (no adjustment);
every price / USD dust test (UNBOUNDED INPUT — the shape does not apply).

## 5. Calibration, before any zero was believed

Harness: `2026-08-24_issue_102_evidence/sweep_the_confidence_gate.py`.
406 tablets × six tape lengths = **2,436 rows, 0 errors**.

**C1 — the instrument sees what it should see.** Inject a known
perturbation into `eff_confidence`, count verdict flips on the non-arm
gate:

| injected | flips |
|---|---|
| 0 | 0 |
| 1e-09 | 0 |
| 1e-03 | 1 |
| 1e-02 | 16 |
| 5e-02 | 100 |
| 2e-01 | 1305 |

Blind to nothing it should see; reports nothing it should not.

**C2 — the arm is reached.** 1,800 of 2,436 rows (**73.9 %**) satisfy the
arm's measured condition. A sweep of an arm that never applied would be
a zero about the tape, not about the gate.

**C3 — the structural zero, counted rather than asserted.**

| | arm rows | confidence conjunct refuses | whole gate refuses |
|---|---|---|---|
| BEFORE | 1800 | 71 | 71 |
| AFTER | 1800 | 1625 | 1625 |

**A finding about the tape lengths, which a single length would have
hidden in the opposite direction this time.** The arm's proximity
condition is IDENTICAL at 35, 40, 60, 100, 200 and 400 bars — 300 of 406
tablets at every length, the same 300 assets, the same `bb_pos` to 12
decimal places. Bollinger is a trailing 20-period band, so the last
candle's band position does not depend on how much tape sits behind it.
What DOES move with tape length is `consensus_confidence` and
`position_boost` (market structure needs ≥ 60 bars), and those are what
the flip counts vary on.

## 6. The value sweep

SHA-256 per row over `consensus_confidence`, `consensus_direction`,
`position_boost`, `bb_confidence_boost`, `eff_confidence`,
`eff_direction`, `bb_pos`, both proximity flags, and the gate's own
outputs. Floats as `float.hex`, so nothing rounds away.

```
digest BEFORE  f6478b51c04736a326ab4e1cbe3d5136f107ccb28ef43700890be32459e7d2fc
digest AFTER   e0035c81860c14c9409b64f1823f0afb4ca8e8e0d92f5195f2c5290737115f97
```

**1,800 of 2,436 rows moved**, 300 at each of the six lengths. Each row
is hashed at the arm state its own tape produces, so a moved row is a
row whose LIVE evaluation moved. The 636 rows off the arm are judged
against the unchanged 0.25 floor and did not move — that is the whole
of the "changes nothing live" bucket, and it is exactly the non-arm
rows.

Measured ranges:

| quantity | min | max | median |
|---|---|---|---|
| `consensus_confidence` | 0.0002 | 0.3402 | 0.0731 |
| `position_boost` | −0.1800 | +0.4000 | 0.0000 |
| `bb_confidence_boost` | 0.0000 | 0.1437 | 0.0000 |
| `eff_confidence` | −0.1254 | 0.4694 | 0.0686 |

107 rows across the whole set have `eff_confidence < −0.05`, the only
reading the BEFORE arm could refuse. 71 of them are on the arm.

## 7. The decision sweep

Driven through the real `build_scrumming_scrum_chain()` and
`build_scrumming_fold_chain()`. Every `GateContext` field is set
permissive except the TA verdict, so a chain verdict is attributable to
the TA gate and to nothing else.

| bars | rows | on the arm | SCRUM before | SCRUM after | FOLD before | FOLD after |
|---|---|---|---|---|---|---|
| 35 | 406 | 300 | 88 | 22 | 239 | 28 |
| 40 | 406 | 300 | 121 | 18 | 198 | 14 |
| 60 | 406 | 300 | 179 | 19 | 148 | 18 |
| 100 | 406 | 300 | 114 | 17 | 189 | 16 |
| 200 | 406 | 300 | 111 | 19 | 195 | 18 |
| 400 | 406 | 300 | 110 | 19 | 193 | 18 |

**SCRUM verdict flips: 609. FOLD verdict flips: 1,050.**

| side | FIRE → shut | shut → FIRE | off the arm |
|---|---|---|---|
| SCRUM | 609 | 0 | 0 |
| FOLD | 1050 | 0 | 0 |

**Every flip is FIRE → shut. Not one is shut → FIRE, and not one is off
the arm.** That is structural, not luck: the repair only ever raises the
bar a reading must clear, and only on the arm. It cannot open a gate that
was closed.

Every one of the 1,659 flips is named — tablet, tape length, effective
direction, both boosts, the effective confidence and the before/after
verdict — in `2026-08-24_issue_102_evidence/sweep_result.md`, §"every
SCRUM flip, named" and §"every FOLD flip, named". The row-level record
is `rows.jsonl`.

**Read this number honestly.** Hysteresis and target-delta availability
are bot state that no tablet carries, so the harness holds them
permissive. 73.9 % is therefore the arm at its WIDEST, an upper bound on
live reach, and the flip counts are upper bounds with it. What the sweep
establishes is not "1,659 live trades change" but "on every row where
the arm applies, the gate now has a false case and 90 % of readings take
it".

## 8. What I could not verify

- **Live reach of the arm.** Two of its three conditions are bot state.
  The 73.9 % is an upper bound, not a live rate. Closing that needs a
  live `BB PRIORITY SKEW` emit count, which the log line now carries in
  a form that says which floor applied.
- **Whether 0.1923 is the RIGHT favour.** It is the operator-era 0.30
  re-expressed so it cannot override. The magnitude was the author's
  choice in 2026-04-26, not the operator's; the operator ruled only on
  override-versus-skew. One constant moves it.
- **`bb_confidence_boost` at its ceiling.** Its code maximum is 0.60; the
  tablets reached 0.1437. Its "cannot refuse" verdict is derived from the
  source, not observed on this tape set.
- **The harness replicates `tick()`'s confidence pipeline rather than
  calling it.** `tick()` needs an exchange, a bus and a ladder. Each
  copied block cites the shipping line it came from, and the two floors
  are IMPORTED from the module rather than restated, but the copy is a
  copy.

## 9. Guard status

- `tests/test_autonomous_fold_price_gate.py` — `PRE_CHANGE_SHA256`
  RE-BASED a fourth time, with the reason recorded and every prior
  digest kept in the auditable chain. `_pre_change_source` returns
  **zero orphans**. 122 pass.
- `tests/test_extractor_tranche_containment.py` — `CITATION_ANCHORS`
  re-anchored by anchor ordinal plus monotonic shift, never difflib.
  **Two bands: +68 from `:574` through `:7662`, +86 from `:9316` down.
  42 anchors moved, 0 did not, no anchor is new.** Every rewritten line
  read back out of the post-change file. 121 pass.
- `scrumming_bot.py`'s own prose: **74 of 75 self-citation tokens
  shifted** by the same two bands. The 75th, `:488-494` at `:1759`,
  names a spec document rather than this file — pre-change 488-494 is
  the phantom-timeframe filter — so a cross-document reference was left
  alone rather than corrupted.
- The emitter identification document — 8 pin line numbers shifted +68
  and each verified against the line it now named. That document has
  since been removed with the pin register.
- `tests/test_fold_hold_reason_is_true.py` — three source-level pins
  RESTATED for the new local, two added: one that both floors can refuse
  a reading of exactly 0.0, one that no addition reaches the measurement.
- `tests/test_indicator_numeric_identity.py` — untouched, 40 pass. No
  indicator was changed, so no digest moved.

## 10. Verification run

| check | result |
|---|---|
| `emitter_registry_check` before | exit 0, 76 pins, no E, no W1 |
| `emitter_registry_check` after | exit 0, 76 pins, no E, no W1 |
| `coding_archetype` / `ta_archetype`, per file | `passed=true`, `errors == []`, 0 high, 0 critical |
| `scrumming_bot.py` archetype baseline | low 573 → 572, medium 552 → 551, info 3 → 3 (no finding added) |
| the 84 test files that touch the subject | **3,273 passed, 1 skipped** |
| sweep reproducibility | identical digests on a second full run |

The full release gate was NOT run and the version was NOT bumped, per
the work order.
