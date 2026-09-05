# Issue #104 — the remaining confidence favours can refuse

Date: 2026-08-24. Branch `issue-104-the-remaining-boosts-can-refuse`,
from `040fc8e` (v3.26.0, gate green, 7,862 tests).

Instrument: `tools/sweep_the_remaining_boosts.py`.
The worked example this unit follows is issue #102, commit `6adbb0b`.

---

## 1. What each favour is for, from its own record

### `position_boost` — a PRIORITY rule, written into a confidence

The chronicle records the insight that created it, 2026-04-14, the
"BONK insight":

> strong VX bullish AT the upper BB means the price is being PUSHED into
> resistance with force. **Best time to sell, not worst.**

That is a statement about WHEN TO TRADE. Every comment in the block says
the same thing: "boost scrum", "great time to scrum", "Bearish = good
for scrum". Six mentions of SCRUM, and the arithmetic it produces feeds
`is_bullish` AND `is_bearish` equally.

### `bb_confidence_boost` — a one-sided grant from a pattern detector

Two terms. The landing-strip term fires with `bb_override_direction`,
and the landing strip is ALSO honoured further down as a hard override
that sets `is_bullish` or `is_bearish` to True whatever the confidence
is. The tightening term comes from `detect_landing_strip_v2`, whose own
field comment calls its output a "Recommended confidence boost".

### The manual's own equation, and where the code left it

The product manual §6.5.5, shipped v3.15.73, documents the cascade:

```
eff_confidence = consensus_confidence
               + position_boost          (±0.03 to ±0.20)
               + bb_confidence_boost     (+0.15 to +0.35)
               + bb_priority_skew        (+0.30, never flips direction)
```

`position_boost` is documented at ±0.20 — **deliberately under the 0.25
floor**, so the favour alone could not carry a reading over the gate.
The shipped code reaches +0.40. `bb_confidence_boost` is documented at
+0.35 and the shipped code reaches +0.60, because the tightening term
was added on top of a term the manual describes as the whole quantity.
The generator is `tools/build_product_manual.py`, which is in the tree
and builds the manual PDF.

---

## 2. BUILDS a score, or FAVOURS a comparison?

Both FAVOUR a comparison. The evidence, per site:

**`position_boost`.**

1. It adds no measurement. Every signal it reads — vortex, macd,
   ichimoku, stochastic_rsi — has ALREADY been counted by `VotingEngine`
   into `consensus_confidence`, each with a weight of its own. It
   re-reads votes already cast and re-spends them.
2. Its magnitudes are flat constants (0.12, 0.08, 0.05, 0.10), not
   functions of the signal's own strength. A builder scales with
   evidence; a favour is a flat grant.
3. Its ceiling, +0.40, is **larger than the largest consensus confidence
   the sweep measured, 0.3402**. A term bigger than the quantity it
   adjusts is not an adjustment to it.

**`bb_confidence_boost`.**

1. It is one-directional. A detected pattern only ever raises the
   confidence, never lowers it.
2. It raises the confidence used by BOTH `is_bullish` and `is_bearish`,
   while the pattern that granted it names ONE side in
   `bb_result.landing_strip_side`. A reading that names one direction
   but favours both is not a measurement of either.
3. Its landing-strip half is already honoured as a hard override
   downstream, so its confidence contribution there only ever favoured a
   comparison that had already been decided.

The #102 shape therefore fits, and it is what was shipped.

---

## 3. The ceilings

| favour | ceiling | floor | established how |
|---|---|---|---|
| `position_boost` | **+0.40** | −0.29 | ENUMERATED over its own term structure, and OBSERVED at +0.4000 |
| `bb_confidence_boost` | **+0.60** | 0.00 | DERIVED from two component bounds; observed maximum is only +0.1437 |

`position_boost` enumeration. `at_upper_bb` (bb_pos > 0.75) and
`in_bb_middle` (0.35 ≤ bb_pos ≤ 0.65) are mutually exclusive, so a
reading sits in exactly one of three zones; the product over each zone's
term menus is the whole reachable set.

| zone | min | max |
|---|---|---|
| upper | −0.13 | **+0.40** |
| middle | **−0.29** | +0.20 |
| outside | −0.13 | +0.20 |

The enumerated ceiling EQUALS the observed maximum. That equality is the
positive control for the enumeration (control C4): a term structure
counted wrongly would not land on the number the tape produced.

`bb_confidence_boost` derivation. The landing-strip term is
`0.15 + consolidation_strength * 0.20`, and `consolidation_strength` is
clamped to 1.0 twice in `bb_proximity.py`, so it tops out at +0.35. The
tightening term is `0.08 + 0.17 * length_factor * tightness_factor`,
both factors clamped to 1.0, so it tops out at +0.25. The two detections
are independent and both can fire on one reading: **+0.60**. The tape
reaches only +0.1437, so this ceiling is DERIVED and is reported that
way (control C5).

---

## 4. Do they compound? Yes

| question | rows of 2,436 |
|---|---|
| both favours strictly positive on the same reading | 3 |
| favour alone at or above the floor that judged it | **73** |
| `eff_confidence` driven BELOW ZERO | **316** |
| passed the standing 0.25 floor while the MEASURED consensus did not | **111** |

On those 73 readings the comparison had no false case. Consensus
confidence is bounded below by 0, so no indicator output whatever could
have refused. On 316 readings the "confidence" the gate judged, and nine
diagnostics printed, was NEGATIVE — outside the domain of a confidence.

All three favours are computed on every tick from the same reading, so
the repair sums the three and divides once, rather than relaxing one
floor at a time.

---

## 5. The repair

`eff_confidence` is left alone. It is now exactly
`summary.consensus_confidence`. The three favours are summed and divide
the threshold:

```python
_ta_conf_skew = position_boost + bb_confidence_boost
if _bb_priority_arm:
    _ta_conf_skew += _BB_PRIORITY_SKEW
_eff_conf_floor = _skewed_confidence_floor(_ta_conf_skew)
```

`_skewed_confidence_floor(skew, floor=_TA_CONFIDENCE_FLOOR)` returns
`floor / (1.0 + skew)`, and `math.inf` when `1.0 + skew <= 0`.

Why proportional. Subtracting 0.30 from 0.25 lands at or below zero and
is the tautology again. Dividing preserves zero: at the largest skew
this module can build (+1.30, all three at their ceilings) the floor is
still 0.1087, so a reading of exactly 0.0 is refused. Dividing also
needs no second rule for a NEGATIVE skew, which TIGHTENS the floor by
the same arithmetic.

No new number is introduced. The floor and every skew were already of
record; only the form of the favour and its target change. With the
other two favours at zero the arm's floor is still exactly
`_BB_PRIORITY_CONFIDENCE_FLOOR` = 0.1923, the number #102 shipped.

The `math.inf` branch is unreachable from this module —
`position_boost` bottoms at −0.29, `bb_confidence_boost` is never
negative, the arm's skew is positive — so it guards a future term. It
returns infinity rather than a friendlier fallback because a fallback
would REWARD total evidence against.

---

## 6. Prints repaired: FIVE

Nine sites print `eff_confidence`. Four already paired it with
`_eff_conf_floor` and became honest with no edit. Five were repaired:

| # | site | what was wrong |
|---|---|---|
| 1 | `TA Vote` | printed `+ BB 0.nn` beside the confidence, as an ADDEND to it. It is not added any more; it now reads `floor skew +0.nn pos +0.nn BB` |
| 2 | `BB PRIORITY SKEW` (#102's explainer) | said the floor went to 0.1923 `(÷1.30)`. The divisor is now the sum of three, so it names all three terms and still quotes the arm-alone figure |
| 3 | `MEM-196 RIPE-HARVEST OVERRIDE ta_bullish` | reported a confidence as the reason without naming the floor that refused it |
| 4 | `MEM-196 DEEP-FOLD OVERRIDE ta_bearish` | the same, on the fold side |
| 5 | `HOLD SCRUM ... waiting for BULLISH` | the same |

The four already correct: both `TA-conf-below-floor` blocker labels, the
`HOLD FOLD` explainer's confidence branch, and the SCRUM fill record
(which also had `pos_boost=` renamed to `pos_skew=` and gained the floor
it cleared).

One print was deliberately NOT changed: the `HOLD FOLD` "blocked by an
override" branch. Adding the floor to it would have broken
`test_the_boundary_is_reported_correctly`, which discriminates a
floor-block from an override-block on the presence of the word "floor",
and that branch already states the confidence was not the blocker.

---

## 7. Proof

Calibrated first, six controls, **PASSED**, exit 0. 406 stone tablets ×
six tape lengths = 2,436 readings, 0 errors.

### Value sweep

```
digest BEFORE  c6dd9686d502e9c3a150a994f84591271e8cb027a13c1f0570aa920f305ee8f0
digest AFTER   a624fe07551add3a95bf9ae31d55f7e31a456f6202a0c9c2efc9df5cab8c24d2
```

**1,198 of 2,436 rows moved** — 66 / 111 / 266 / 251 / 252 / 252 at 35 /
40 / 60 / 100 / 200 / 400 bars. Each row is hashed over the gate's
inputs, the confidence it JUDGES, the floor it judges against, and both
verdicts. A row with a zero favour cannot move; every moved row has a
non-zero one.

### Decision sweep

Through `build_scrumming_scrum_chain()` and
`build_scrumming_fold_chain()`, every field permissive except the TA
verdict.

| side | flips | FIRE → shut | shut → FIRE | on the arm | off the arm |
|---|---|---|---|---|---|
| SCRUM | 86 | 83 | 3 | 71 | 15 |
| FOLD | 48 | 40 | 8 | 35 | 13 |

**NOT structural in #102's sense.** #102 produced 1,659 flips, all
FIRE → shut. This unit produces 134, of which **11 go shut → FIRE**, and
the sign of the favour explains every one:

| side | direction | favour > 0 | favour < 0 | favour == 0 |
|---|---|---|---|---|
| SCRUM | FIRE → shut | 83 | 0 | 0 |
| SCRUM | shut → FIRE | 0 | 3 | 0 |
| FOLD | FIRE → shut | 40 | 0 | 0 |
| FOLD | shut → FIRE | 0 | 8 | 0 |

Zero rows in the wrong column. A trade that STOPS firing is a reading a
POSITIVE favour had carried over the floor. A trade that STARTS firing
is a reading a NEGATIVE favour had dragged under it — every one of the
11 carries a `position_boost` between −0.03 and −0.08 and a measured
consensus above 0.21. That is the mirror of #102's finding that the only
rows its arm could still refuse were ones a negative `position_boost`
had already pushed below zero.

All 134 flips were enumerated one by one with tablet, tape length,
direction, both favours, both judged values, both floors and the arm
state. Every one of the 134 crosses its OWN floor: the BEFORE value sits
on one side of the BEFORE floor and the AFTER value on the other side of
the AFTER floor. No flip comes from a row the repair left alone.
`tools/sweep_the_remaining_boosts.py` reproduces the enumeration.

### Calibration

| control | asks | result |
|---|---|---|
| C1 | can the instrument see a change? | 0 flips at a 0 perturbation, 0 at 1e-9, 11 at 0.01, 1,501 at 0.20 |
| C2 | is the BB-priority arm reached? | 1,800 of 2,436 rows, 73.9 % |
| C3 | can the conjunct refuse? | BEFORE 2,218 refusals with **73 rows no reading could refuse**; AFTER 2,322 refusals, 0 unfailable BY CONSTRUCTION |
| C4 | is the enumerated ceiling real? | enumerated +0.40 EQUALS observed +0.4000 |
| C5 | is the derived ceiling honest? | +0.60 derived, +0.1437 observed, stated as derived |
| C6 | do the favours co-occur? | 3 rows both positive, 73 rows past the floor, 316 rows negative |

### What varies with tape length

| bars | `position_boost` non-zero | its min | its max | `bb_confidence_boost` non-zero |
|---|---|---|---|---|
| 35 | 63 | −0.08 | **+0.20** | 4 |
| 40 | 108 | −0.13 | **+0.30** | 4 |
| 60 | 266 | −0.13 | +0.35 | 4 |
| 100 | 248 | −0.18 | **+0.40** | 4 |
| 200 | 249 | −0.18 | +0.40 | 4 |
| 400 | 249 | −0.18 | +0.40 | 4 |

**A single tape length would have been a false green here, and this
table is the proof.** `position_boost`'s market-structure term is
guarded by `len(candles) >= 60`, so at 35 bars the favour tops out at
+0.20 — UNDER the 0.25 floor. A sweep at 35 bars alone would have
concluded this gate could always refuse.

`bb_confidence_boost` is the opposite, and matches #102's finding about
the proximity condition: non-zero on the same 4 rows at EVERY length,
because both detectors read a trailing window rather than the whole
tape.

---

## 8. Re-anchor, both guards

`scrumming_bot.py` 15,682 → 15,823 lines. **TWO shift bands**: +52 at
and above `:7782`, +141 from `:9543` down.

* `PRE_CHANGE_SHA256` in `tests/test_autonomous_fold_price_gate.py`:
  `d4edd46f…` → `03d05460421d2c601a37dadc5cd97b6a77805a974ac29f6f3f2b5e75cf7f40f5`.
  Fifth re-base. All five prior digests kept in the chain.
  `_pre_change_source` returns **zero orphans**. 122 tests pass.
* `CITATION_ANCHORS` in `tests/test_extractor_tranche_containment.py`:
  42 anchors, all 42 moved, none new, no ordinal count changed. The
  positive control's own `lineno = 642` moved to 694. 121 tests pass.
* 74 of the 75 self-citation `:NNNN` tokens inside `scrumming_bot.py`
  moved. The 75th is `:488-494`, the spec-document reference #102 named.
  A further 19 tokens carry another module's filename, and one more —
  `[:180]` at the credential-refusal emit — is a SLICE the citation
  regex matches and that was never a citation. All 21 left alone, and
  counted so the gap does not read as an omission.

Derived by anchor ordinal plus monotonic shift, never difflib, and
**derived a second way as a cross-check**: an exact line map from git's
own hunk ranges, verified by requiring identical text on both sides for
every one of the 15,667 unchanged lines — not a sample. The two
derivations agree on all 42 anchors.

---

## 9. Gates

| check | result |
|---|---|
| `coding_archetype src/trading/scrumming_bot.py` | `passed=true`, `errors=[]`, low 572 / medium **550** / info 3 (baseline 572 / 551 / 3), 0 high or critical |
| `ta_archetype src/trading/scrumming_bot.py` | `passed=true`, `errors=[]`, low 91 (baseline 91) |
| both, `tests/test_autonomous_fold_price_gate.py` | `passed=true`, unchanged from baseline |
| both, `tests/test_extractor_tranche_containment.py` | `passed=true`, unchanged from baseline |
| both, `tests/test_fold_hold_reason_is_true.py` | `passed=true`, low 46 / medium 21 / info 16 (baseline 39 / 16 / 12; the file grew by 107 lines) |
| both, the new sweep harness | `passed=true`, `errors=[]`, 0 high or critical |
| `emitter_registry_check` | exit 0, 76 pins, no E lines, **no W1 lines**. Eight pin rows in `scrumming_bot.py` shifted +52 and each was verified against the line it now names |
| tests | 3,981 passed / 1 pre-existing skip across the 94 files that touch `ScrummingBot`; 420 passed across the 16 further TA and gate files |

---

## 10. What could not be verified

1. **The +0.60 ceiling of `bb_confidence_boost` was never observed.** It
   is derived from two clamped component bounds. The tape reaches
   +0.1437. Both detections firing on one reading is possible in source
   and did not happen in 2,436 readings.
2. **The product manual's §6.5.5 equation is still wrong.** It documents
   `position_boost` at ±0.20 and `bb_confidence_boost` at +0.35 against
   the +0.40 and +0.60 the code reaches. `tools/build_product_manual.py`
   generates the page.
3. **The sweep replicates the gate rather than calling it.** `tick()` is
   a 4,500-line coroutine needing an exchange, a bus and a live ladder.
   The replication is #102's, copied unchanged. Only
   `_TA_CONFIDENCE_FLOOR` and `_BB_PRIORITY_CONFIDENCE_FLOOR` are
   imported from the module; the rest of the copy has no pin against it.
4. **The arm's other two conditions are held permissive.** Opposing-trade
   hysteresis and available target delta are bot state no tablet carries.
   That is the arm at its widest.
5. **The enumeration assumes one signal per indicator.** `tick()` loops
   over `summary.signals` and would double a term if an indicator voted
   twice. The equality of the enumerated ceiling with the observed
   maximum is the only check on that assumption.

## 11. Adjacent defects, named in one line each

* `position_boost` re-spends votes `VotingEngine` has already weighted —
  a double-count of macd, ichimoku, vortex and stochastic_rsi.
* Its comments say "scrum" six times, but the value it produces unlocks
  FOLD as well as SCRUM.
* The landing strip sets `is_bullish`/`is_bearish` to True downstream
  regardless of any confidence — a hard override of the gate this unit
  just taught to refuse.
