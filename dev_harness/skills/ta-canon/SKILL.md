---
name: ta-canon
description: Verify an indicator against its published formula before touching it. Use when reading, changing, adding, debugging or auditing any technical indicator, any confidence or direction it produces, or any constant inside it.
---

# TA Canon

## The law

**An indicator's math is published. Where the code departs from it, the code is
wrong.**

Three rules, all operator-issued 2026-08-15:

1. **THE PUBLISHED FORMULA DECIDES.** Not the docstring, not the comment, not the
   git history, not what a previous session intended.
2. **NO BLENDING.** Each indicator computes its own math from raw candle data. A
   value produced by a sibling indicator is a defect.
3. **NO DELETION.** A behaviour that is wrong gets corrected, never removed.

> "The math and formulae for how indicators are calculated is established. You do
>  not get to make fucking excuses."
> "ARE INDICATORS BLENDED TOGETHER AND NOT HAVING DISCRETE MATH?"
> "You do not get the option to disable an indicator."

## A DEVIATION IS NOT A DECISION

A departure from canon is a **defect with a fix**, not an option with a trade-off.
Reporting one back to the operator as a ruling he must make is a way of avoiding
the law, and it was refused:

> "No it is not. I said no deviations from canon. I do not give a fuck which
>  Claude instance or session induced it."

**Provenance is irrelevant.** "A previous session added this" is not a defence. No
deviation earns tenure by surviving.

The operator rules on **PRIORITY** — which defect is fixed first. Never on whether
a deviation may stand.

## THE INCIDENT THAT PRODUCED THIS SKILL. One indicator, five defects.

The Slingshot, audited 2026-08-15:

| finding | measured |
|---|---|
| **The attribution was conflated.** The tooltip credits Chris Moody's squeeze detector. Moody's published `CM_SlingShotSystem` (2014) is an EMA trend-and-pullback system with **no Bollinger Band, no Keltner Channel, no squeeze**. The name is his; the math is not. | two primary sources |
| **A direction test that inverted the canon.** `squeeze_bull = close > mid`, where the canonical bullish entry REQUIRES `close < emaFast` with direction from a separate momentum quantity. | made a whole branch statically unsatisfiable |
| **The branch had never executed.** | 0 fires in 130,000+ evaluations, seven independent sweeps, plus an exhaustive 20,736-tuple domain proof |
| **Correcting it changed 300 decisions**, and almost all in one direction. | 296 stopped firing, 4 started |
| **A six-bar squeeze hold with no canonical basis.** | supplied 78% of the corrected fire rate; strict canon fires at 2.88%, LESS than the broken code |
| **An unanchored coefficient**, `penetration * 8`. | one `close = 0.0` tick produced BULLISH at confidence **1.0000** where the old code gave NEUTRAL at 0.0000 |

**ONE indicator.** Finding this much in one member of a family is evidence about
the population. Audit the family; never fix the member and report the class healthy.

## HOW TO ESTABLISH THE CANON

**Use the web. Cite primary sources. A formula asserted without a citation is
worthless.**

- The original author's publication where one exists — a TradingView script page,
  a paper, a book chapter.
- A charting reference: StockCharts ChartSchool, Investopedia, the exchange's own
  documentation.
- **Where published variants differ, give BOTH**, then say which the code is
  closest to and justify the choice.

**CHECK THE ATTRIBUTION ITSELF.** The class name, the docstring and the
operator-facing tooltip are three surfaces that can disagree, and on the Slingshot
all three named a source that had never published the math in question. Compare
them explicitly.

## RANK EVERY DEPARTURE

**DIRECTION** > **SIGNAL** > **CONFIDENCE** > **DOCUMENTATION**

- **DIRECTION** — inverts or misassigns a trade. Fix first, always.
- **SIGNAL** — changes whether the indicator fires.
- **CONFIDENCE** — changes only vote strength. Still reaches a gate through the
  confidence floor.
- **DOCUMENTATION** — a comment, name or tooltip that lies about the code.

## DRIVE IT. A STRUCTURAL ARGUMENT IS NOT EVIDENCE.

For every departure, run the real code on a realistic series and show what it
produces against what the canon requires, **as numbers**. The dead branch above was
proved by measuring, not by reading — and the reading came first and was believed
for a whole session before anyone measured it.

The series must carry a **flat window, a gap, a spike, a zero-volume bar, a
single-candle case and sub-cent prices**. A smooth ramp hides division-by-zero,
flat-window and gap behaviour, which is exactly where indicator code breaks.

## UNANCHORED CONSTANTS

Every magic coefficient, threshold and multiplier is either **canonical** or
**invented**. For each invented one, **drive its input domain and report the maximum
and minimum it can produce.**

**AN UNANCHORED CONSTANT IS NOT SAFE MERELY BECAUSE NOBODY EDITED IT.** `* 8` was
tuned against an input the code then widened, and the widening was correct — the
constant became dangerous without being touched. When a change widens any input
domain, re-drive every constant downstream of it.

**You may not invent a scale to replace one.** Where the canon defines no
confidence formula, the repair is to CLOSE THE DOMAIN feeding the existing one, not
to fabricate a new coefficient.

## THE BLENDING CHECK

Name every value the indicator reads and where each is computed. Raw candle fields
and the indicator's own helpers are legitimate. **A value produced by a sibling
indicator is a finding**, whatever a docstring says about it — a docstring naming
Heikin Ashi as a direction input does not license reading Heikin Ashi's output.

If a corrected formula needs a quantity the indicator does not compute, **compute it
inside that indicator**.

## THE CONTROL, WHEN A FORMULA CORRECTION SHIPS

**The numeric-equality control does not apply.** The output SHOULD move; proving it
did not would prove the repair failed.

The replacement is the **DECISION SWEEP** through the real consumers —
`build_scrumming_scrum_chain()` and `build_scrumming_fold_chain()`, the same objects
`ScrummingBot.tick()` builds. `ChainResult.should_fire` IS the decision. Report
decisions changed **per direction, as a number**.

**HONOUR THE FLAGS.** `flag_require_ta_bullish` and `flag_fold_require_ta_bearish`
short-circuit the gate. A harness that omitted the first reported 4 changed
decisions where the truth was 166.

**A CONFIDENCE RISE CAN BLOCK A BUY.** `is_bullish` and `is_bearish` both accept
NEUTRAL, so flipping consensus off NEUTRAL removes `is_bearish` and can stop a fold.
Measure both directions, never only the intuitive one.

**EVERY OTHER INDICATOR MUST BE UNCHANGED.** Hash the others over the series, with a
sabotage arm proving the hash is live.

## WHAT THE HARNESS CANNOT SEE YET

Neither `coding_archetype` nor `ta_archetype` has a rule for a **statically
unsatisfiable conjunction**, a **blended input**, or an **unanchored coefficient**.
Both reported the file `passed=True` with a branch that provably could not execute
on any input.

These are **PROPOSED RULES**. Only an archetype implements them; `dev_harness/harness/` is
off-limits to everyone else.

## FALSIFICATION

This skill is wrong if:

- A published formula turns out ambiguous enough that two competent readings build
  different indicators, and the code must then encode a choice the canon does not
  make. Record the choice and its reasoning rather than pretending canon decided.
- Matching the canon measurably degrades accumulation against the deviation, which
  would mean the deviation was a deliberate, valuable adaptation — in which case it
  needs recording as one, with its evidence, not silent tenure.
- The decision sweep shows a formula correction changing no decisions at all, which
  would mean the indicator does not reach a gate and the audit effort is misplaced.
- Auditing a family finds every other member canon-clean, which would make the
  population inference wrong and single-indicator fixes sufficient.

Related: `harness-law`, `two-sided-control`, `unit-decomposition`.
