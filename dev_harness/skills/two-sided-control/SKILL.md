---
name: two-sided-control
description: Prove a check can fail before trusting that it passed. Use when adding or relying on any check that reports a pass/fail verdict — a test, an archetype rule, a gate, a probe, or a measurement script.
---

# Two-Sided Control

## The subject is CHECKS, not cases

This is not "also test the failure path". Testing more cases is the bloat
that gets waived. This runs on the **instrument**: before a green result
means anything, the instrument must be shown capable of going red.

An assertion that **passes on an incorrect state** is an ORACLE FALSE
NEGATIVE. One that **fails on a correct state** is an ORACLE FALSE
POSITIVE. Together they are ORACLE DEFICIENCIES (Jahangirova, Clark,
Harman, Tonella, ISSTA 2016; Terragni et al., ESEC/FSE 2020). The name is
borrowed on purpose — this is adoption of an existing practice, not a new
idea.

## Why this exists

Six incidents in one day, all in this repo, all with a green result:

| # | what happened | deficiency |
|---|---|---|
| 1 | an 8-row accept/reject table passed; a 2,868-case sweep found 113 silent behaviour changes, one of which sent a **zero-size order to a live exchange** | unclosed domain |
| 2 | a colour test read `cell.background().color().name()` — the MODEL. A stylesheet rule made Qt drop `BackgroundRole`, so the render went blank while the test stayed green | false negative |
| 3 | a rule's `known_bad` fixture exited 0. The rule detected both planted defects, but emitted at medium while the verdict only trips on high | false negative |
| 4 | an analyzer could never pass any pytest file — 2 findings per `assert` | false positive |
| 5 | a probe read `$?` after `$(basename $f)` had already reset it, and reported a checker blind when it was not | false negative |
| 6 | two regexes inventorying the same network returned 0 and 309 against a recorded 40 | both |

Measured externally, the same effect: Daikon-inferred assertions showed
**zero false positives on the tests that generated them** — the authors
call it "an expected result" — and scored **38%** against an independently
built validation set. An instrument built from the same source as the thing
it measures reports clean and is blind.

## THE TWO RULES

### Rule 1 — Two-sided control at the verdict surface

Every check that reports a pass/fail verdict must be observed:

- **FAILING** on a planted defect, and
- **PASSING** on a known-good fixture,

both read **at the surface the check reports through** — never at an
intermediate.

That last clause is the load-bearing one. A colour check must read the
rendered pixel, because that is what the operator sees. A gate check must
read the exit code, because that is what blocks. Reading an intermediate
tests the intermediate.

The planted defect must be **the kind of defect this check exists to
catch**. A plant that any check would catch proves nothing.

### Rule 2 — An enumerated table does not close a numeric domain

Where a decision turns on rounding, quantization, or a threshold, sweep the
domain or property-test it. Do not hand-write rows and call the set closed.

A hand-written table encodes the same mental model as the code. That is the
instrument agreeing with itself.

### Rule 3 — A TEST WITHOUT A DEMONSTRATED RED IS NOT A TEST

Operator, 2026-08-13: **"A test without a known good vs bad result is
useless on its face."**

**DO NOT FORCE A FAILURE. That is the wrong reading, and it is its own
defect.** Operator, correcting exactly this, 2026-08-13:

> "It does not need to be forced to fail and this is a key issue with your
> hallucinatory tendencies. You need to implement a test for which we
> understand what a failure looks like. You should not be forcing anything.
> Write the code. Test the code. It fails. You fix it. You test again."

Planting a defect to make my own test go red proves almost nothing. I choose
the plant, so I choose a defect I already know the test catches. That is the
instrument agreeing with itself at one remove — the residual this skill
already names, reintroduced as a ritual.

**THE REQUIREMENT IS COMPREHENSION, NOT MUTATION.** Before the test runs,
state what a failure would MEAN about the code. A test whose failure you
cannot interpret is useless whether it is red or green.

**THE ORDINARY DEVELOPMENT CYCLE SUPPLIES THE RED FOR FREE.** Write the
code. Run the test. It fails, genuinely, because the code is not right yet.
Fix it. Run again. That red is real, unchosen, and diagnostic. Nothing needs
manufacturing.

**Where a planted defect IS legitimate: an INSTRUMENT, not a test.** A
checker, a gate, an archetype, a measurement script — something whose whole
job is to report on other code, and which has no development cycle of its own
to fail in. Rule 1 governs those. A unit test of code you are writing is not
one of them.

Measured, 2026-08-13, item 9. Its two surface tests used
`inspect.getsource` plus a substring match to assert a widget existed. Both
passed. A text scan cannot see a widget that is CONSTRUCTED BUT NEVER ADDED
TO A LAYOUT, nor a field that never reaches the config. Green, and
worthless. The replacement drove the real widget, asserted
`parentWidget() is not None`, and read the value at the consumer.

**THE UNKNOWN, stated rather than hidden:** this repository has 3,922
passing tests. **How many have ever been observed red is not known.** A
suite's pass count measures the suite, not the code. Do not quote a test
count as evidence of correctness — quote what a specific test was shown to
catch.

#### You learn what a failure looks like by DRIVING it, never by predicting it

**A predicted failure mechanism is a hypothesis. A test written against the
prediction tests the prediction.**

Measured, 2026-08-13, the NaN row in `_reconcile_holdings`. The work order
predicted: a NaN lot makes the ratio NaN and "multiplies EVERY lot by NaN",
destroying the book. Reasonable, and wrong.

What the code actually does, observed by running it with lots `[30.0, nan]`,
scalar 48.73, venue 40.0:

1. drift-down fires, ratio `40/48.73 = 0.8208`
2. `30.0` becomes `24.6254…`, and `nan * 0.8208` stays `nan`
3. the survivor filter `l["units"] > 1e-12` reads `nan` as **False**
4. **the poisoned lot is silently DROPPED.** Two lots in, one lot out

The book ends up **finite, self-consistent and healthy-looking**, with one
lot's `initial_buy_price` gone for ever. That is worse than the predicted
outcome, because the predicted outcome is visible and this one is not.

**A test asserting "the book becomes NaN" would have PASSED on the real code
and shipped the defect.** The prediction and the reality disagree about the
observable, so the assertion built from the prediction is aimed at nothing.

The rule: **drive the real path with the hostile input and record what
happens.** Then write the assertion against the OBSERVED behaviour. Where
prediction and observation disagree, say so — that gap is the finding.

#### A fix can install an oracle false negative. Check the fix the same way.

Same unit, same day. The obvious widening — `internal = max(sum(lots),
scalar)` with no guards — introduces a NEW blindness: with an `inf` lot,
`max(inf, 48.73)` is `inf`, tolerance becomes `inf * 0.005 = inf`, and
`abs(venue - inf) <= inf` is **True**. The audit reports ALIGNED and goes
SILENT for ever.

The repair to a blind check produced a check that is blind in a new way.
Drive the fix against the same hostile domain that motivated it.

**What to write down instead of a mutation:** one sentence, before the run,
saying what a failure of this test would tell you about the code. If that
sentence cannot be written, the test has no defined meaning and the problem
is the test's design, not its colour.

    weak : "asserts the despawn setting is present"
    good : "if this fails, the value the operator set never reached the
            field the sweep reads, and the timer will silently never fire"

The second sentence names a consequence. The first names a substring.

#### A DOCSTRING THAT STATES A PROPERTY IS A CLAIM. Test it or delete it.

"Never raises", "always returns a float", "keeps X == Y true" are assertions
about behaviour, and no gate reads prose. Measured twice on 2026-08-13:

- `_despawn_aged_tranches` claimed `created - closed - discarded == standing`.
  The fold side implemented it; the STACK side had no discarded counter at all.
- `_settled_fill_label` claimed "Never raises". Driven with 16 value rows,
  **two raised** — an object whose `__eq__` raises escapes from `label != ""`.

Both were caught by an adversary driving the code, not by reading it. Either
prove the property over its closed domain, or do not write the sentence.

### Rule 4 — A MEASUREMENT WITHOUT A DEFINED INTERPRETATION IS NOT EVIDENCE

Operator, 2026-08-13, on scaling the emitter network:
**"Let's collect a bunch of data we do not know how to interpret." >.>**

Before adding an observation point, write down what its readings MEAN —
which value is healthy, which is a warning, which is a fault, and against
what threshold. An observation with no defined reading is not instrumentation.
It is volume, and volume hides the signals already present.

Measured, 2026-08-13: three of the platform's forty emitter pins pass
`actual` and `expected` as the IDENTICAL EXPRESSION, so their verdict
derives True on every call and can never fail. Multiplying that shape to a
thousand points multiplies noise, not insight. The operator named the same
class on 2026-08-08: "expected=none is functionally useless as designed."

The test is one question: **what reading would make me act differently?**
If no reading changes a decision, the point earns nothing and costs
attention.

Applying this everywhere is the failure mode. It does not apply to:

- **A check with no verdict.** A logging call, a report, an inventory. If
  nothing branches on it, there is nothing to be blind about.
- **Error-handling code as a category.** Measured: `try` and `finally`
  blocks, which run in normal flow, show coverage statistically
  indistinguishable from ordinary code (Cliff's delta 0.06-0.16, null
  hypotheses NOT rejected). The bias localizes to **syntax that only
  executes on failure**. Do not sweep `finally` blocks looking for it.
- **A loud, immediate failure.** If the thing crashes visibly when broken,
  the world is already the control.
- **Throwaway work.** Probes, one-off scripts, anything whose wrong answer
  costs a re-run.
- **A check already covered by a discriminating fixture pair.** Do not add
  a second control to satisfy the letter of the rule.

## THE WHOLE SUITE, EVERY TIME. A PROPOSED SHORTCUT WAS REFUSED.

I proposed narrowing the mutation and revert controls to "only the tests that
pin the behaviour", to save wall clock. **The operator refused it**, 2026-08-15:

> "No thanks. Keep it slow and robust. Too many chances for cheating and gaps.
>  I will not tolerate it."

and, setting the boundary a message earlier:

> "The harness cannot be weakened. I will not have hallucinated slop manifesting
>  throughout this queue."

**THE RULE: run the WHOLE suite at every point a suite is run.** Baseline,
post-change, every mutation, every revert, and the gate. No subset, no targeted
selection, no "only the pinning tests".

**WHY THE REFUSAL IS CORRECT, and this is the part worth keeping.** My proposal
was gated on three conditions I would have had to police on myself — chiefly
"you can NAME the tests that pin this behaviour". That is a judgement call, and a
judgement call inside a control is a gap, not a rule. A shortcut available
whenever the agent believes it understands the blast radius is a shortcut
available always. The same session produced a counter that could not see its own
loop's drops, a guard that admitted `inf`, and a reachability classification
excused by the harness's own omission — every one of them an agent confident it
knew what it was measuring.

**THE COST IS REAL AND IS ACCEPTED.** Measured 2026-08-15: the whole suite runs
560-844 seconds and grew from 4,677 to 6,172 tests in one day; roughly half the
wall clock of a promoting unit is verification. The operator has read those
numbers and chosen them.

**DO NOT RE-PROPOSE THIS.** A faster suite is a legitimate goal; a narrower
control is not. If the wall clock has to come down, make the SUITE cheaper —
parallelism, fixture reuse, collection cost — and never the coverage of a control.

### THE COST IS PAID PER UNIT, SO SIZE THE UNIT TO ONE CONTROL

**This rule is unchanged and is not the problem.** What was wrong was putting
seven controls inside one unit and then paying the rule seven times over,
SERIALLY, in a single agent.

Measured 2026-08-15, degenerate-window: 7 controls, **17 whole-suite runs in one
agent, 231 minutes of pytest, 82% of a 282-minute job.** The unit changed ONE
source file, and 13 of 235 test files name it — so 94.5% of every run was code
the unit had not touched. That last number is not an argument for running less;
it is an argument for not paying for it seven times in a row.

Split to one control per unit and the same seven controls run in seven agents
**concurrently**, for about the wall clock of one. Identical coverage, identical
count of runs, nothing narrowed. See `unit-decomposition`, splitting-test
question 7.

**The two failure modes this must not become:**
- Answering the control count by DELETING a control. That is the refused
  shortcut wearing a new name.
- Splitting into units that cannot each fail on their own, to make the count
  look right. A fragment that cannot state its own test is not a unit.

### AND USE THE CORES. THE SUITE IS THE THING TO SPEED UP, NOT THE CONTROL.

Measured 2026-08-15: `pytest-xdist` was installed and had never been used, on a
**24-core** machine running the suite single-threaded. That is the sanctioned
lever above, sitting untouched.

**It is not free and must be earned.** Parallel workers reorder tests, so an
order-dependent test can flip in either direction. Before any parallel
invocation is allowed near a gate, prove the **pass/fail SET is identical** to
serial — not the count, the set — and prove it with a planted order-dependent
test as the two-sided control. A matching total with a different set is exactly
the false green this skill exists to prevent.

## The cost argument, stated as the hypothesis it is

The rules scope to **`O(checks)`, not `O(cases)`** — a repository has far
fewer verdict-reporting checks than possible inputs, so cost does not scale
with input space.

**No verified cost figure supports this.** The one published anchor located
failed adversarial verification and is deliberately not cited. The
structural argument is all there is; treat it accordingly.

## NEVER RECONSTRUCT A BEFORE-STATE. READ IT FROM GIT.

A mutation control needs a pre-change file to compare against. **Building that twin by
textually reversing your own edit is fragile, and it failed twice on 2026-08-15.**

| failure | cost |
|---|---|
| the reversal span ended one line short of a counter write, so the twin raised `NameError` | **27 money controls went red on a fault in the RECONSTRUCTION, not the code** |
| a helper mapped every citation-shaped `file.py:NNNN` token instead of only self-citations, shifting 16 that named OTHER files | the gate went red and BLOCKED a sound, fully-proven repair |

**Both reds were false, and both cost a full unit to diagnose.** Neither said anything about
the code under test.

**THE STRUCTURAL FIX: `git show <commit>:<path>`.** That is the file, exactly — no span
arithmetic, no token mapping, nothing to drift as the file grows.

**THREE THINGS TO GET RIGHT:**

- **Verify the bytes.** git can normalise line endings on checkout. Check `core.autocrlf`,
  check for `.gitattributes`, and census CRLF against LF on what `git show` actually returns.
  This repo is MIXED per file, so assuming either is wrong.
- **Justify the commit.** It must be the state before YOUR change and after everything else
  the tests assume. Read the log; do not guess a hash.
- **THE TWIN MUST STILL DISCRIMINATE.** A twin that is byte-perfect and that no control can
  fail against proves nothing. Show the controls going RED on the twin and GREEN on the
  branch. That is the two-sided control applied to the control itself.

**AND ASK WHAT THE TEST IS FOR.** "My reconstruction equals the pre-change file" only ever
guarded the reconstruction. Once the twin comes from git that assertion is trivially true,
and the test's real job — proving the money controls ran against a genuine before-state —
has to be stated differently. **Restate it; do not delete it.**

## A FIXTURE SHAPED LIKE THE ASSERTION CANNOT FALSIFY IT

MEASURED 2026-08-15. An emitter pin asserted
`ok = (set(sections_present) <= {"config"})`. It reported **ok=False on the
operator's real state, on every load, permanently** — 37 of 37 of his bots carry
seven sections, and seven names are not a subset of one.

**It survived every fixture and all thirteen recorded runs**, because every one of
them fed a config-only entry. The test data had been built to match the assertion
rather than to match reality. The control ran, went green, and could never have
gone red.

**THE RULE: build the fixture from the REAL DATA SHAPE, read-only, not from the
predicate under test.** If the code reads `bot_state.json`, the fixture's shape
comes from `bot_state.json` — the key set, the nesting, the field types — not from
what makes the assertion convenient.

**THE TELL, and it is checkable:** ask what the fixture would look like if you had
never seen the assertion. If the answer differs from the fixture you have, the
fixture was derived from the check and proves nothing about the world.

**THIS IS AN ORACLE FALSE NEGATIVE WITH A SPECIFIC CAUSE** — not a wrong assertion,
and not a missing case. The assertion and the fixture agree with each other and
both disagree with production. It is the instrument-agrees-with-itself pattern this
whole skill exists for, arriving through the fixture rather than through the check.

**THE ADVERSARIAL MOVE THAT CATCHES IT:** drive every check against the operator's
real data shape before believing any of them. That is what found this one, and it
found it in a file the unit had already edited and reported as repaired.

## A STAND-IN THAT SERVES WHAT THE SOURCE NEVER SERVES IS THE SAME FIXTURE

MEASURED 2026-09-19. Four units read the Market Inspector's Scan Now green in
both variants and on both bundles. Every reading ran with sockets refused and a
loopback stand-in for the candle source. The stand-in answered candles on every
timeframe the scan asked for, including weekly. Coinbase serves granularities of
60, 300, 900, 3600, 21600 and 86400 seconds and no weekly one. The operator's own
press (his `system.log`, 07:36:51 to 07:38:18) read 120 markets, got no candles
on 1wk for all 120, found 0 hits after 87 seconds with nothing drawn while it
ran, and read `no ticker list` for stocks because no list source exists. He
pressed the button fourteen more times; each `press ignored` line went to the
log and never to him.

**Three fixtures were shaped like the assertion at once:**

- the stand-in served what the venue does not (weekly candles);
- the bundle launched with no network ended at `no candle`, and that empty end
  state was read as a reading of the button;
- the missing stocks list was written down as *his* ruling instead of fixed, so
  the unit's acceptance never met the class he presses.

**THE RULE, in three parts:**

1. **Shape the stand-in from the source's documented limits, and say them.** A
   brief that stands in for a venue, an exchange, a feed or an endpoint carries a
   `### Real conditions` section naming the source's documented response shape
   and limits with their figures (granularities, list endpoints, page sizes, rate
   limits), and the operator's own recorded responses where his logs hold them.
   The hook `block_stand_in_without_source.py` refuses a brief without it.
2. **An empty end state is a non-reading.** A bundle that ends at `no candle`,
   `no post`, `no tablet` or `0 of 0` did not exercise the feature. Report it as
   not read, and require the end state the operator will see: hits, or a refusal
   with its cause named on the screen he watches.
3. **What he sees while it runs is a contract member.** A press that works for
   87 seconds and shows nothing is a press that does nothing. Progress, the
   in-flight refusal and every fetch's block on the pane he watches are read at
   the widget, per variant, not only the end state.

**And the referee's own defect:** a missing data source, an unsupported request,
a thread guard refusing a feed — these are defects the unit fixes. Only a product
choice is his. Writing a defect down as *his line* is how it shipped twice.

## THE RESIDUAL — what this does NOT catch

**A check whose premise is wrong will pass its own two-sided control.**

Measured at scale: Just et al. 2014 found **63 of 357 real faults (18%)**
had no corresponding mutation operator, 44 of them algorithm modification
or simplification; and **118 of 480 (25%)** tests that demonstrably caught
a real fault killed zero additional mutants.

Planted-fault validation has a hard ceiling at specification-level and
wrong-algorithm error. Neither rule catches "we built the wrong thing".

## FALSIFICATION

This skill is wrong if:

- a two-sided control is added and, over ten changes, **never once fails**
  on the planted-defect side — the plant is too easy and proves nothing
- rule 2 sweeps find **zero disagreements** over ten numeric changes
- the controls become a maintenance burden exceeding the defects they
  surface
- an oracle false negative reaches live **behind a check that carried a
  passing two-sided control** — then the control was read at the wrong
  surface, and the rule needs rewriting rather than reapplying
- `O(checks)` turns out not to hold, and control count grows with cases

Related: `harness-law`, `unit-decomposition`, `branch-discipline`.
Research: `docs/audits/2026-08-11_happy_path_avoidance_research.md`.
