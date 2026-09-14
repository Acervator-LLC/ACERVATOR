---
name: canonized-workflow
description: The workflow every unit follows — W5H answered, OCIR proved, the gate run — and the Python hook that refuses a brief which skips a step. Load before dispatching anything.
---

# The canonized workflow

**A workflow that is not written into the brief is not followed.** Every gap on
this project came from a brief that asked for the part a picture shows.

Operator, 2026-09-13: *"IMPROVISED TOOLS. IMPROVISED COMMENTS. IMPROVISED
WORKFLOWS THAT ALWAYS LEAVE GAPS DUE TO SCAFFOLDING. IT MUST STOP."* and
*"I WANT PYTHON ENFORCEMENT."*

## The four parts, in every brief

### 1. W5H — what the unit must answer before it changes anything

- **who** builds or calls it, in the running program
- **what** changes when it runs
- **where** every site that names it
- **when** it runs, and what runs it again
- **why** it exists, quoted from the manual with its location, or **nothing**
  with the count that proves the absence
- **how** the path from his action to the value or the pixel at the end

Posted to the issue **before** a line of code changes, each answer carrying a
file and a line.

### 2. OCIR — what proves the answer

Every reading is shown to fail before it is trusted: the blinded run, the
planted control, the calibrated fixture pair. A zero is a claim about the
instrument until something makes the instrument report.

### 3. The gate — what a merge waits on

```bash
python -m tools.local_ci --all
```

Its verdict line is quoted, before and after. See Skill: harness-law for which
lanes must pass and which are known-empty.

### 4. The skill block — what the unit loads

Named bare, one per line, so the loader reads them:

```
Skill: harness-law
Skill: ocir
```

A skill named in backticks is invisible to the loader, and a rule that is not
loaded is not followed.

## The enforcement

`~/.claude/hooks/block_uncanonized_workflow.py` refuses an `Agent` dispatch
whose brief commissions work and omits any of the four. It fires only on a
commissioning brief — a question passes.

Proved both ways when it was written:

```
control, a complete brief          exit 0
no falsification                   exit 2
no gate                            exit 2
no six questions                   exit 2   missing: who, where, when, why, how
conversion, no workflow skill      exit 2
not commissioning                  exit 0
```

A hook nobody has watched refuse is not a hook. If this one stops refusing, it
is broken and that is a finding.

## Where a workflow lives

In a skill, never in a brief. A brief that states a rule inline is an
alternate grounding point, and it drifts the moment the skill changes. Name the
skill and let the unit load it — see Skill: ground-to-issue-and-manual.

When a workflow is missing from canon, writing it into a skill **is** the work.
Improvising it in one brief means the next unit does it differently, and the
difference is where the gap lives.

## Falsification

This skill is wrong if a brief passes all four parts and the unit still returns
work with a gap. Then a fifth part exists that the four do not reach, and
naming it is the work.
