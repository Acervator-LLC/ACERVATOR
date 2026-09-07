---
name: found-it-own-it
description: Everything you find is yours - defects and decisions both. Load before writing the words pre-existing, baseline, not mine, out of scope, or belongs to another unit about any defect, and before writing your call, up to you, both are yours, let me know which, or should I about any decision. Invoke by name when the operator asks who owns a finding, when a report is about to hand a defect to nobody, or when he says stop deflecting.
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

## A decision is a finding too

Operator, 2026-09-07: *"Need a skill or rule that prevents inactionable
deflections back to me. You have to make these decisions and close them out.
There should be enough information in the manual, the issue, or canonized
researchable data to close these gaps of self-doubt."*

**A gap you hand back is the same forbidden move as a defect you hand back.**
The clothes are different and the shape is identical: you established a fact,
stopped, and made him do the closing.

Same move, different clothes:

- "both need a severity change, so both are yours"
- "your call" / "up to you" / "let me know which"
- "should I raise it or leave it"
- "awaiting your ruling"
- naming two options and picking neither

**Three grounds close any of them, and one of the three always applies:**

```
the issue body          what the item says the work is
the Product Manual      the page the item names
the published standard  GICS, Wilder, Botes and Siepman, the API's own docs
```

**Read one. Decide. Report the decision with the ground it stands on.** A
decision with its ground is not a deflection, however briefly it is stated.

Where the ground is genuinely silent, the widest true reading of the item
decides it, and you record which reading you took. Silence is not a blocker.
`widest-true-reading`.

---

## The only three things that reach him

```
does it work
does it match spec
is it worth doing
```

He decides product and spec — a surface, a name, a target, what the application
IS. Everything under that is implementation and it is yours.
`do-not-escalate-implementation-choices`.

**A blocked capability is not a deflection.** The environment refusing a write,
a wall on the billing, a credential you must never hold — say it in one line
with the exact thing that would unblock it, then carry on with everything else.
That is a fact he alone can change, not a decision you declined to make.

---

## OCIR has four letters

Observe is the first quarter. Iterate means change the thing and measure again.

If your report is a list of findings, ask what changed on disk. Nothing means
the unit is unfinished.
