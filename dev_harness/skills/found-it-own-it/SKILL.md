---
name: found-it-own-it
description: Everything you find is yours. Load before writing the words pre-existing, baseline, not mine, out of scope, or belongs to another unit about any defect. Invoke by name when the operator asks who owns a finding, or when a report is about to hand a defect to nobody.
---

# EVERYTHING YOU FIND IS YOURS

Operator rule, 2026-09-03. **Finding a defect makes it yours. No other owner
exists.**

---

## The forbidden move

Establishing that a defect predates your change, and stopping there. That is a
fact about history. History repairs nothing.

Same move, different clothes:

- "pre-existing on `origin/current`"
- "fails identically with my change stashed"
- "not caused by this unit"
- "belongs to whoever added it"
- "outside my scope"
- "that file has another owner"
- "named, not fixed"

**Measure the baseline anyway** — it tells you whether you caused the defect,
which changes the fix, not the ownership. Then fix it.

---

## What to do

1. Fix it in the same unit, with a check that fails without the fix.
2. Too large for this unit — build that unit now. Not a note, not an issue.
3. Genuinely impossible this session — carry it forward yourself, with the
   reason and the cost.

---

## The three exceptions

1. **Harness files.** Only the Coding Archetype edits an archetype, and only to
   ADD a hardening rule. `harness-law`.
2. **A fix that changes what a number means.** Recalibrating a constant around a
   defect, or altering a figure the operator reads, is his decision. Name it
   with the measurement and the consequence.
3. **A dead screen** — nothing constructs it — where the defect is in the dead
   widget, not in code you are writing.

Not exceptions: a file another unit touched, a test someone else wrote, a
failure that predates you, anything "adjacent".

---

## OCIR has four letters

Observe is the first quarter. Iterate means change the thing and measure again.

If your report is a list of findings, ask what changed on disk. Nothing means
the unit is unfinished.
