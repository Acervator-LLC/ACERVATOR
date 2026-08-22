---
name: unit-sizing
description: Load at the START of any coding, refactor, bug-fix, test or engineering task, BEFORE the first edit. Sizes one work item into units small enough to be built and verified completely in one pass, so an adversary cannot discover the same defect class serially over several rounds. Triggers whenever a task is not already scoped to one variable, one button, one behavior, one signal or one algorithm. Invoke by name when the operator asks to break work down, chunk a task, or size a unit.
---

# Unit Sizing

## Boundary against prompt-distillation

`prompt-distillation` runs on the MESSAGE. It turns n asks into n tracked
items so none is dropped. This skill runs on ONE tracked item. It turns
one item into k units that can each be built and verified in one pass.
Distillation asks "how many things did you ask for". Sizing asks "is this
one thing actually one thing". Run distillation first, then run this on
every item it emits.

## Why this exists

One queue item — "containment lift + atomic arrival" — took four
adversarial review rounds and produced 32 refutations. It silently held
five units: a money-path type gate, an atomic write block, a ledger
container contract, an emitter with its own verdict logic, and a
reconciliation limitation. The adversary found the type gate's holes
SERIALLY, about one new input shape per round: bool, numeric string,
Decimal, Fraction, float subclass, object with `__float__`. 25 of the 32
refutations reported a measured runtime outcome, so those were real
defects, not prose churn.

The item was small by every published measure — one diff, one context
window, minutes to write. It was large in the one dimension no published
measure covers: its ACCEPTED-INPUT SET was unbounded.

## THE THIRD FAILURE: CONTROLS MULTIPLY, AND THEY MULTIPLY SERIALLY

**ONE UNIT, ONE CONTROL.** This is a hard sizing bound and it is the most
expensive one to get wrong.

The no-subset rule is correct and is not negotiable: every baseline, every
mutation, every revert and the gate run the WHOLE suite. What that rule costs
depends entirely on how many controls you put in one unit, because the runs
inside one agent are SERIAL.

Measured 2026-08-15, on the degenerate-window unit:

| | |
|---|---|
| whole suite, one run | 522-679 s |
| controls declared in the unit | 7 |
| suite invocations inside ONE agent | **17** |
| pytest wall clock in that agent | **231 min** |
| the whole job | 282 min |
| share of the job that was pytest | **82%** |
| source files the unit changed | 1 (`ta_engine.py`) |
| test files naming that file | 13 of 235 |
| share of every run that was unedited code | **94.5%** |

Seven controls in one unit cost 231 minutes. **The same seven controls, in
seven units, cost about one run** — they run in parallel agents. Identical
coverage, identical rigour, nothing narrowed. The only thing that changed is
where the controls sit.

**SO: COUNT THE CONTROLS BEFORE YOU BUILD.** If the unit needs a second
mutation, a second revert, or a second before/after comparison, it is a second
unit. `k` controls in one unit is a `k`-fold serial multiplier on the single
most expensive operation in the workflow.

**THIS IS NOT A LICENCE TO DROP A CONTROL.** Splitting keeps every one of them.
A unit that answers the count by deleting a control has failed, not passed.

## THE SECOND FAILURE: A SIZED UNIT ABSORBS ITS NEIGHBOURS

Splitting is half the job. A unit can be sized correctly and still fail by
reaching sideways into behaviour that belongs to another item.

Measured, 2026-08-12, three times in one session:

| unit being built | what it reached into | how it got in |
|---|---|---|
| ladder SPACING | the MERGE rule | a read step and a test row |
| tranche CONSUMPTION | DISTRIBUTION modes | offered as a design option |
| remnant TOP-UP | the `operator_initiated` tag | raised as a question for the operator |

The operator's response was the same each time: "They are separate fucking
items, bro." And: "UNIT DISCIPLINE. DO YOU UNDERSTAND."

None of those was a sizing error. Each unit was one thing. The defect was
importing a second thing beside it.

### THE ONE-VERB TEST

**A unit owns exactly one verb.** Write the unit's claim as a sentence. If
it needs a second verb, you have crossed a boundary.

    spacing      PLACES a rung
    merge        COMBINES tranches close in price
    consumption  SPENDS a tranche
    distribution ALLOCATES money across rungs

- "quadratic PLACES rungs at n² × gap" — one verb. In scope.
- "the merge rule still applies after spacing" — PLACES and COMBINES. Out.
- "what happens to the tag when tranches merge" — that is merge's verb.

### NAME THE NEIGHBOURS BEFORE THE FIRST EDIT

List every adjacent behaviour that has its own spec, and write **not this
unit** beside each. Put that list in the work order, not in your head. A
neighbour that is never named is a neighbour that gets absorbed.

### THREE WAYS A NEIGHBOUR GETS IN, all of them quiet

1. **As context.** "Read what the merge rule does" inside a spacing unit.
   Reading it invites reasoning about it.
2. **As a test row.** "X still holds after my change", where X is the
   neighbour's property. Running the neighbour's EXISTING suite as a
   REGRESSION check is fine and correct. Asserting the neighbour's
   behaviour as a property of THIS unit is not. The tell: a regression run
   names a test FILE; a boundary breach names a BEHAVIOUR.
3. **As a question.** Surfacing a neighbour's design choice for a ruling.
   If the answer changes the neighbour, it belongs to the neighbour's unit.
   Asking is not neutral — it costs the operator a decision they already
   made somewhere else.

### WHEN THE SPEC ALREADY ANSWERS IT, THERE IS NO QUESTION

The most expensive version of this is asking about something the operator
has already specified. Before raising anything, search their own words. A
question they already answered reads as not having listened, because it is
not having listened.

## THE SPLITTING TEST

Answer all five BEFORE the first edit. Any NO means split, then re-run
the test on each part.

1. **CLOSED.** Can you write the unit's complete accepted-and-rejected
   input table now, before any code, and is that table finite?
2. **ONE ACT.** Does one Arrange-Act-Assert prove it — one setup, one
   call, one set of claims? A second Act is a second unit.
3. **ONE KIND.** Is the change behavioural or structural, not both? Work
   that moves code AND changes what the code does is two units.
4. **NO SURPRISES.** Build it naively for real. Did that produce zero
   unplanned prerequisites? Every error is a separate unit: write it
   down, then REVERT. Do not push through from an unknown state.
5. **NOT DELETABLE.** Remove any one part. Does the rest stop being
   shippable? If a part can be deleted and the rest still ships, that
   part is its own unit.
6. **CLEAN GROUND.** Is every file in the touch set ALREADY `passed=true`
   on every archetype that applies to it, measured on the unmodified live
   tree, BEFORE the first edit? A red file is not a place you can ship
   from. See below.
7. **ONE CONTROL.** Count the controls this unit needs — every mutation,
   every revert, every before/after comparison. Is the count exactly one?
   Each additional control is another WHOLE-SUITE run, SERIAL, inside one
   agent. Seven controls measured 17 runs and 231 minutes. Split, and the
   same seven cost about one run in parallel. Never answer this question
   by deleting a control.

Seven YES: build it. Everything below is how to answer question 1, and
how to know when to stop splitting.

## QUESTION 6: MEASURE THE GROUND BEFORE YOU WRITE THE TOUCH SET

**A unit cannot be greener than the files it lands in.** Harness law says
`passed=False` is INVALID. One already-red file in the touch set therefore
makes the whole unit unshippable, however good the work is.

Measured, 2026-08-13, item 9 (tranche despawn timer). Five files in the
touch set. `src/gui/bot_wizard.py` was already red on the unmodified live
tree: `coding_archetype` 4 highs, `gui_archetype` 2 highs. The build
cleared 3 of the 4 coding highs and still could not report green, because
three survivors were pre-existing and none was fixable inside its
authority — one needed a forbidden `type: ignore`, the other two were
accessibility findings on two unrelated classes.

The whole unit blocked on a file it did not need. The despawn setting is
read with `getattr(config, "tranche_despawn_days", 0)`, so a bot created
without the key already defaults to Off. The wizard field added nothing
the unit required.

**Run the archetypes on the touch set BEFORE writing the work order.**
It costs a minute. Then:

| ground | what to do |
|---|---|
| all green | proceed |
| a file is red and the unit NEEDS it | the red is its own unit, and it goes FIRST |
| a file is red and the unit does not need it | **drop it from the touch set** |

Dropping is usually right, and it is usually a boundary fix rather than a
compromise: the red file is often the second surface, and the second
surface is usually the absorbed neighbour.

**Record the baseline number either way.** "Compare against the pinned
baseline, never against zero" applies to harness findings exactly as it
applies to measurements. A build that walks into a file with 4 highs and
leaves 1 has to be able to say so, and cannot say so without the baseline.

### THE TOOL EXISTS. RUN IT.

```bash
python -m dev_harness.touchset baseline <path> [<path>...] --pin <file>
```

Refuses (exit 1) if any file is already red, naming the file and the
archetype. Refuses (exit 2) if a path does not exist, **before** running
any archetype — because all five exit 0 and report `passed=true` on a
missing path, so a verification that scanned nothing would otherwise read
as a pass. Writes a pin recording each file's verdicts, line-ending kind
and forbidden-directive count.

```bash
python -m dev_harness.touchset check --pin <file> --against <island>
```

Compares the island to the **pin**, never to zero. Exit 1 on: a red file,
a forbidden-directive count that INCREASED, a line-ending kind that
flipped, or a path that vanished. A pre-existing directive count is not
this unit's to clear; an increase always is.

Measured on the live tree, `src/gui/bot_wizard.py` — the file that cost
item 9 an entire round:

    REFUSED: 1 archetype verdict(s) are already red
    on the UNMODIFIED tree, before this unit edits anything.
      src/gui/bot_wizard.py: coding_archetype passed=False (4 high/critical).

Cost: about 55 s to baseline two large files. Run it once per unit, not
once per edit.

**WHAT IT CANNOT CATCH, so it is not oversold.** It counts; it does not
judge. It cannot tell you whether the change is COMPLETE (7 of 10 sites
converted lands green), whether a DOCSTRING TELLS THE TRUTH (a comment
asserting an invariant the code lacks passes every gate), or whether the
touch set is the RIGHT set (a file that should have been in the unit is
invisible to it). Those three are exactly what blocked rounds 2 and 3 of
item 9, and they stay human.

## The five categories, made operational

| Category | The buildable unit | Its test |
|---|---|---|
| **One variable** | one factor moved, every other factor pinned | re-run the same measurement with only that factor changed; compare against the pinned baseline, never against zero |
| **One button** | one control, one handler, one state transition | drive the control in a state that really exists; assert the one state change, the one call it makes, and the disabled case |
| **One behavior** | one `When` | Given/When/Then with exactly one When; a second When means a second unit |
| **One signal** | one emitter, one field, one verdict | force fire and no-fire; read the field the CONSUMER reads, not an adjacent cache |
| **One algorithm** | one function with one stated property | one property over the whole closed input domain, plus the partition table below |

## Bound the input domain in ONE pass

Serial discovery is the measured failure. Close the set before you build.

- **Name the accepted set by exact membership, never by an open
  predicate.** `type(x) in (int, Decimal)` accepts exactly two things and
  can be tabulated. `isinstance(x, numbers.Real)` accepts a set you
  cannot enumerate by reading it, and it does not mean what it looks
  like. Measured, Python 3.14: `bool` passes it, `Decimal` FAILS it,
  `Fraction` passes, a `float` subclass passes.
- **A TYPE IS NOT A DOMAIN. Close the VALUE range too.** Exact type
  membership closes which types are accepted. It says nothing about which
  VALUES those types carry, and `float` carries four that break
  arithmetic: `nan`, `inf`, `-inf`, `-0.0`. `type(float('nan')) is float`
  is True, so the strictest possible type gate still admits them.

  Measured, 2026-08-13, item 9 (`_despawn_threshold_days`). The gate was
  `type(_raw) is int or type(_raw) is float` — exact membership, exactly
  as this skill prescribes. `int(nan)` then raised `ValueError` and
  `int(±inf)` raised `OverflowError`, from a call site outside any `try`,
  so the exception left the method and propagated out of `tick`. The
  stated contract was "a non-numeric or negative setting is treated as
  OFF, before any comparison runs". NaN is numeric by type, was not
  treated as off, and did not merely fail to delete — it took the tick
  down.

  Reachability was low: both spinboxes are integer-only and clamped. It
  was not zero: `json.dumps(float('nan'))` emits bare `NaN` and
  `json.loads('NaN')` returns it, both verified, so a hand-edited or
  corrupted state file reaches it.

  **If `float` is in the accepted set, the input table needs value rows,
  not only type rows:** `nan`, `inf`, `-inf`, `-0.0`, and the boundary
  values of whatever range the unit claims. `math.isfinite` is the test;
  it is one call and it closes the hole.
- **Equivalence partitioning, written first.** List every partition of
  the accepted set and every rejected partition. One test row per
  partition. A partition is an EXPECTATION that the code treats those
  values alike — it is not a proof, so run every row rather than
  reasoning about it.
- **Then one property over the closed set** (property-based testing).
  It samples rather than proves — Hypothesis stops at `max_examples`,
  default 100 — but it shrinks failures and replays them for ever, so a
  shape found once cannot come back in a later round.
- **Use both.** Partitioning fails when your reasoning is wrong.
  Sampling fails when the sample misses. They fail independently.

**Mid-flight split trigger.** If a review round surfaces a NEW accepted
input shape, the unit was oversized. Stop. Do not patch that shape and
continue — that is round 1 of 4. Close the set, write the table, re-run
the splitting test.

## THE INVERSE TEST — k INSTANCES ARE ONE ITEM. STOP PATCHING AND BUILD THE DETECTOR.

Everything above asks whether one item is secretly k units. **This asks the opposite, and
it is the more expensive mistake.** Operator, 2026-08-15:

> "This is an explicit demonstration of a hallucinatory failure to troubleshoot to root
>  cause. We have to stop this from happening. It should not have taken 8 passes."

**THE RULE: the SECOND instance of a defect shape is a CLASS. The next unit's deliverable
is a DETECTOR, not a third fix.**

### THE OPERATIONAL TELL, and it is unambiguous

**If the ADVERSARY of unit N finds instance N+1, you were patching instances.**

An adversary is supposed to find what the build missed *inside its own scope*. When it
keeps finding the *next member of the same family*, the scope was drawn around a symptom.

### MEASURED, TWICE IN ONE DAY

**ELEVEN DEFECTIVE EMITTER PINS, EIGHT OF THEM IN SCOPE, HANDLED ONE AT A TIME.** The
count itself was got wrong twice before it settled — first reported as twelve, because one
pin carries two shapes and was double-counted, then corrected against the live tree. Four
shapes — identical `actual`/`expected`, a
hard-coded `actual`, an `expected` naming a quantity the code does not measure, and inverted
fields — all one root: `signal_contract` derives `ok = bool(actual == expected)` and
**nothing requires the expectation to be derived independently of the observation.** Eight
passes each found "another pin". The class was never named until the operator named it.

**FOUR ORDER-DEPENDENT MONEY SITES OVER FOUR UNITS.** `float(x) or 0.0` does not catch
`nan`, because `nan` is truthy. Each unit closed one site; each unit's adversary found the
next. The fourth reaches `guarded_place_order`, where `nan < min_amount` is False, so a NaN
order amount passes the last gate before the venue.

**AND THE THIRD SWEEP FOUND WHAT THE FIRST TWO STRUCTURALLY COULD NOT:** method 1 enumerated
ordering calls by name; method 2 started from mapping reads; **neither can see an instance
attribute.** A universe defined by the shape you already found cannot contain the shape you
have not.

### WHAT TO DO AT INSTANCE TWO

1. **NAME THE ROOT IN ONE SENTENCE.** Not "these pins are broken" — the contract, the idiom,
   the missing constraint. If it takes a paragraph, it is not the root yet.
2. **ENUMERATE THE POPULATION BY A METHOD THAT DOES NOT PRESUPPOSE THE INSTANCES YOU HAVE.**
   Then enumerate it AGAIN by a different method and reconcile the counts. Two universes
   that agree are evidence; one is a guess.
3. **BUILD THE DETECTOR.** For this repo that means an archetype rule with positive and
   negative fixtures — the gate then refuses the shape, and the class cannot regrow. Only an
   archetype may author it; the referee's deliverable is a specified rule.
4. **THEN fix the instances**, in one unit per genuinely distinct repair, with the detector
   proving the population is closed.

### THE COST OF GETTING THIS WRONG, MEASURED

Each instance-level unit today ran 100–190 minutes and consumed 400–900k tokens. Eight
passes at that rate is a day. **One detector would have found all twelve pins in one run** —
the classifier that eventually did it was calibrated 14/14 against a control module and took
a single agent.

### THE HONEST BOUNDARY

**Do NOT declare a class from one instance.** One defect is a defect; the population
inference needs a second. And a detector that cannot discriminate is worse than patching —
it reports green over the whole family and everyone stops looking. **The detector ships with
its own two-sided control or it does not ship.**

## LOWER BOUND — when splitting further makes it worse

Recombine when a fragment:

- **cannot fail a test on its own.** If you cannot state its test, it is
  not a unit.
- **is only a mockup, a data structure, or a test case.** Those are
  slices of one layer, not units.
- **cannot be shipped or deprioritised independently** of its siblings.
- **costs more to gate than to build.** Batch size is a U-curve, not a
  race to the minimum. If the release gate dominates the unit, make the
  gate cheaper before splitting again.
- **exists only to make the plan look thorough.** Splitting is for
  building, not for planning.

## Worked example — the failure, split correctly

| # | Unit | Its test |
|---|---|---|
| 1 | Money-path type gate: one exact type test at one entry point | the 13-shape TYPE table, written BEFORE the code: int, bool, float, float subclass, `Decimal`, `Fraction`, `'1'`, `''`, `None`, object with `__float__`, `complex`, `numpy` scalar, `datetime`. Accepted = exactly 2. **Plus the VALUE rows that table misses, because it accepts `float`:** `nan`, `inf`, `-inf`, `-0.0`. |
| 2 | Atomic write: temp file plus replace, one path | interrupt between write and rename; assert the old file is intact and no partial file survives |
| 3 | Ledger contract: one accepted container type at the ledger boundary | accept/reject table over container types, same shape as unit 1 |
| 4 | Emitter: one event, one field, one verdict rule | force fire and no-fire; assert the field the consumer reads |
| 5 | Reconciliation limitation: one stated bound, and the check that enforces it | a test that fails when the bound is exceeded |

Units 3, 4 and 5 can each be deleted and unit 1 still ships. That is
splitting-test question 5 answering NO for the original item.

## What is borrowed, and what is not proven

Mikado supplies question 4, including the mandatory revert. Arrange-Act-
Assert supplies question 2. Equivalence partitioning and property-based
testing supply the domain rule. Question 1 and question 5 are this
repo's own; no published method sizes a unit by its accepted-input set.

Honest limit: **no study shows that smaller units make a coding agent
more correct.** The strongest on-point experiment located (di Biase et
al., 2019, 28 subjects, human code review) found that decomposition
"leads to fewer wrongly reported issues" while it "impacts neither
understanding the change rationale nor the number of found defects".
Fewer spurious findings and a shorter review loop is the claim this
skill supports. Fewer bugs is not.

## FALSIFICATION

This skill is wrong if:

- A unit that answered YES to all five questions still needs a second
  adversarial round to close its input domain.
- The accepted-input table for a shipped unit cannot be reconstructed
  from the tests in the repo.
- `prompt-distillation` gains a sizing test, which would make this skill
  a duplicate.
- Splitting an item into k units costs more gate runs than the rounds it
  saved. Then the U-curve has turned: make the gate cheaper, not the
  units smaller.
- Tracked over ten items, sized items average more than one round of
  NEW input shapes. The test is then not catching what it claims.
- Question 6 drops a file the unit genuinely needed, and the unit ships
  incomplete. The question would then be licensing scope cuts rather than
  finding absorbed neighbours. The tell is whether the dropped file was a
  second surface or a required path: name which, every time.
- A touch set measured green at work-order time still blocks at promote
  because live moved underneath it. Question 6 would then need to run at
  promote as well as at sizing, which is `development-island`'s staleness
  rule and not this skill's.
- The value-domain rule fires on a unit with no float in its accepted set
  and costs rows that can never be reached. Then it is being applied by
  habit rather than by reading the accepted set.

On the boundary rule specifically:

- The one-verb test rejects a unit the operator considers correctly
  scoped. The verbs would then be drawn at the wrong grain.
- Naming the neighbours produces a list so long it is not read. The item
  was then oversized and should have gone back through the splitting test.
- A neighbour is absorbed anyway, and it was named in the work order. The
  naming is then decoration, and the rule needs an enforcing check rather
  than a written instruction — the same lesson as blocking hooks versus
  injected prose.
- Regression runs of a neighbour's suite start catching real breaks, which
  would mean the units are coupled in the code even though they are
  separate in the spec. That is a code finding, not a skill failure, but it
  falsifies the claim that these are independent units.