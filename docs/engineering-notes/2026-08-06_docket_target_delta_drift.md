# DOCKET — Robust Target Delta tracking / value drift across bots

**Filed** 2026-08-06 · **Reported by** operator
**Status** OPEN — deliberately not investigated yet
**Scheduled for** the Trading Tab audit (operator's call)

---

## 1. The report, verbatim

> "Robust Target Delta tracking. Seeing value drift across multiple
> bots. Seems to have increased since doing our API optimizations but
> this could be a false correlation. We will fix this during the
> Trading Tab audit."

## 2. What is being claimed, and what is not

**Claimed:** target-delta values are drifting across multiple bots, and
the drift appears to have grown since the API optimisation work.

**Explicitly NOT claimed:** that the API work caused it. The operator
flagged the correlation as possibly false in the same breath. That
caveat is part of the report and must survive into the investigation —
the obvious suspect being visible is exactly the condition under which
a real cause gets missed.

## 3. Why this is not being chased now

Recorded, not investigated, on operator instruction. Two reasons that
make that the right call rather than merely the instructed one:

1. It belongs to the Trading Tab audit, where the surrounding surface
   (target balance, anchor, delta display, per-bot sizing) will be read
   as a whole. Pulling one thread out of that now means reading the
   same code twice and reasoning about it with less context.
2. "Seems to have increased" is an impression, not a measurement. The
   first real step is quantifying the drift — per bot, over time —
   which needs a deliberate measurement pass, not a drive-by.

## 4. What the investigation will need

Written down now so the reasoning that produced this entry is not lost:

- **A measurement before a hypothesis.** Per-bot target delta sampled
  over a window, so "drift" becomes a number with a direction and a
  rate rather than an impression. Without that there is no way to tell
  a fix from a coincidence.
- **A falsifier for the API-correlation.** The optimisation work is
  datable from the git history that starts at `861611a` and from the
  CHANGELOG; drift measured on windows either side of it either shows a
  step change or does not. If it does not, the correlation dies early
  and cheaply.
- **The competing explanations, stated up front.** Accumulation is
  path-dependent: target balance grows with folds, anchors move, fees
  accrue, and quote conversion re-values holdings. Some drift may be
  correct behaviour that is merely being displayed without context.
  Distinguishing "the number is wrong" from "the number is right and
  surprising" is the first fork.
- **Whether it is display or state.** A wrong number on screen and a
  wrong number in `scrumming_state` are different defects with
  different blast radii. `anchor_target_balance` is persisted for all
  35 bots, so if the drift is in state it is durable.

## 5. The method — operator-specified

> "We should track and compare what the platform is displaying to what
> the API is sending us. If there is a mutation between these, we should
> identify it."

This is the right shape and it should drive the investigation rather
than be one technique among several. It converts an impression
("seeing value drift") into a **differential** with a definite answer:
capture the exchange's number and the displayed number for the same
bot at the same instant, and either they agree or they do not.

Its strength is that it does not require a hypothesis first. Every
explanation — display bug, stale cache, unit/quote conversion, a
genuine accumulation effect, the API work — predicts something
different about WHERE the two series diverge, so the measurement
partitions the causes instead of testing them one at a time.

**What that requires:**

- **Both endpoints captured, timestamped, from the same tick.** Comparing
  a displayed value against an API value fetched seconds later measures
  latency, not mutation. The capture has to be paired at the source.
- **Every hop between them enumerated first**, because "a mutation" is
  only findable if the pipeline is known: exchange response ->
  connector parse -> data pool / cache -> phantom balance and quote
  conversion -> bot state -> the widget's own formatting. Each hop is a
  candidate, and at least one (quote conversion) legitimately changes
  the number.
- **A distinction between transform and corruption.** Some hops SHOULD
  alter the value. The question is not "did it change" but "did it
  change by exactly the amount the transform accounts for". That means
  recording the expected transform per hop, not just the values.
- **Held across a restart**, since `anchor_target_balance` is persisted
  for all 35 bots. If the two series diverge only after a restart, the
  cause is in persistence rather than display.

**Deliberately not built yet.** This is instrumentation on the live
trading path, and it belongs in the Trading Tab audit with the rest of
that surface. Recording the method now so it is not re-derived, and so
the measurement is designed before anyone starts reading code with a
suspect already in mind.

## 6. Cross-references

- Trading Tab audit — not yet scheduled; this entry is one of its
  inputs.
- `docs/engineering-notes/2026-08-05_remediation_methodology.md` — the 66-cascade
  sequence. This is not currently in it and should be added to the
  Trading Tab cascade when that is scoped.
- `anchor_target_balance` persistence is touched by C01 only insofar as
  C01 stops the record being deleted; C01 changes no target value.
