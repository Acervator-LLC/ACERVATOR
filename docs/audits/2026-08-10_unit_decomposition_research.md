# Unit Sizing — report and SKILL

Deliverable saved for extraction at
`C:\Users\brown\AppData\Local\Temp\claude\C--Users-brown-OneDrive-Desktop-ACERTAVOR-PRODUCT-DOCUMENTATION-acervator-session25-CLOSE-hop5-v3-15-27\e918e69f-47d2-40e3-88e6-bea50b264478\scratchpad\unit_sizing_SKILL.md`
(148 lines; `tools.harness.docs_archetype` reports `passed=True`, 28 findings, no high/critical).

---

## Part 1 — Does this already exist?

**No. Build it.** Nothing published sizes a unit of work by the criterion that would have caught the measured failure.

What exists, in three groups.

**1. Splitting methods with no stopping rule.** SPIDR (Cohn) names five axes to cut on and then hands the decision back: *"I don't know that this story needs to be split into that many smaller sub-stories. That's for the team to decide based on the effort involved."* I fetched the article; it states no threshold. It generates candidate cuts. It cannot terminate a split.

**2. Methods with a real stopping rule, but the wrong measure.** Elephant Carpaccio publishes minutes per slice. Humanizing Work publishes stories per sprint. Mikado publishes an empirical leaf test. Matt Pocock's public `to-tickets` skill sizes by context window. **All four would have PASSED the failed item.** It was one diff, minutes to write, one context window. It was oversized in exactly one dimension none of them measure.

**3. Agent-ecosystem prior art.** The official `anthropics/skills` repository holds 17 skills (algorithmic-art, brand-guidelines, canvas-design, claude-api, doc-coauthoring, docx, frontend-design, internal-comms, mcp-builder, pdf, pptx, skill-creator, slack-gif-creator, theme-factory, web-artifacts-builder, webapp-testing, xlsx). None concerns decomposition or sizing. This is a verified absence — I listed the directory. The Claude Code best-practices page states no unit-size rule; its nearest line is about planning overhead (*"If you could describe the diff in one sentence, skip the plan"*) and it closes by asking *"The task too big for one pass?"* as an open question. A third-party `task-decomposition` skill exists and I fetched it: its only thresholds are "30-60 minutes"; its headline claim — *"Tasks properly decomposed achieve 3x higher completion rates and 60% fewer defects"* — carries no citation on the page. It does not occupy the gap.

**Adopt rather than build, in part.** Four mechanics are worth taking wholesale instead of reinventing: Mikado's naive-attempt-then-revert, Arrange-Act-Assert's one-Act rule, equivalence partitioning, and property-based testing. The new part is the sizing criterion itself.

**The missing criterion.** A unit is right-sized when its **accepted-input set is finite and written down before the build**. `isinstance(x, numbers.Real)` cannot be tabulated. `type(x) in (int, Decimal)` is exactly two rows. That single dimension is absent from every source I fetched.

**Boundary against `prompt-distillation` (read at `.claude/skills/prompt-distillation/SKILL.md`).** Distillation is CAPTURE: it runs on the operator's message and turns n asks into n tracked items, typed DIRECTIVE / CONSTRAINT / QUESTION / CORRECTION, so nothing is dropped. Unit sizing is SIZING: it runs on one already-captured item and turns it into k buildable units. They chain and do not overlap. The proof is the incident itself — "containment lift + atomic arrival" was captured correctly as one item, and still held five units. Distillation had already done its job.

---

## Part 2 — The evidence

Every URL below is one I fetched in this session.

**Named stopping rules that work.**

- **Mikado.** I downloaded the Manning chapter-1 PDF and extracted it locally with `pypdf` (18 pages, 29,175 chars → `C:\tmp\mikado.txt`), because WebFetch could not decode it. Verbatim: *"When there are errors, you should always roll back all changes. This is extremely important! Editing code in an unknown state is very error-prone."* And the leaf test: *"When you don't find any additional errors during the implementation of a prerequisite, you've come across a change that has no further prerequisites."* Commit gate: *"The code compiles. The tests run. The product is all good. The changes make sense to check in."*
  **REFUTED CLAIM, DROPPED.** An earlier draft attributed a 5–15 minute timebox (10 recommended) to Mikado. I searched the extracted text: zero hits for "timebox" or "time box", and the single occurrence of "minutes" is an end-of-chapter exercise — *"Set a timer for 15 minutes, refactor some code, and then undo!"* The timebox is a third party's advice, not the method's rule. It is not in the skill.
  https://manning-content.s3.amazonaws.com/download/3/558b9be-92a7-4ebf-90ba-c7fdd830aea7/MikadoMethod_CH01.pdf
- **Elephant Carpaccio.** *"Implementable (including user interface) in 2-6 minutes"*; *"No slice is just a mockup or UI, a data structure, or test case."* The fetch I ran returned a slice target of "15-20 demo-able user stories"; other slice counts appear elsewhere in the same document, so treat the count as soft and the 2-6 minutes and the prohibition as the load-bearing parts. https://docs.google.com/document/d/1TCuuu-8Mm14oxsOnlk8DqfZAA1cvtYu9WGv67Yj_sSk/pub
- **Humanizing Work.** Size target: *"by the time a story makes it to the top of your backlog, you should be able to fit 6 to 10 into a sprint."* Two tie-breakers: *"Choose the split that lets you deprioritize or throw away a story"* and *"Choose the split that gets you more equally sized small stories."* Meta-principle: focus on the complexity and reduce the variations through it. I did **not** read the flowchart PDF — WebFetch returned undecoded binary — so I cite only the guide page and make no claim about the flowchart's wording. https://www.humanizingwork.com/the-humanizing-work-guide-to-splitting-user-stories/
- **Canon TDD.** Step 1 is *"Write a list of the test scenarios you want to cover"*; step 2 is *"Turn exactly one item on the list into an actual, concrete, runnable test."* Beck's warning against converting the whole list at once is about rework, not about skipping the list. Directly relevant: the 13-shape table that eventually fixed the failure IS a Canon TDD test list. It arrived four rounds late because nobody wrote it at step 1. https://newsletter.kentbeck.com/p/canon-tdd
- **Three laws of TDD.** Law 2: *"You must not write more of a test than is sufficient to fail, or fail to compile."* Law 3: *"You must not write more production code than is sufficient to make the currently failing test pass."* Cycles: nano second-by-second, micro minute-by-minute, milli decaminute, primary hourly. http://blog.cleancoder.com/uncle-bob/2014/12/17/TheCyclesOfTDD.html
- **SPIDR — verified negative.** https://www.mountaingoatsoftware.com/blog/five-simple-but-powerful-ways-to-split-user-stories

**The floor.**

- **INVEST.** Testable: *"Writing a story card carries an implicit promise: 'I understand what I want well enough that I could write a test for it.'"* Small: *"Stories typically represent at most a few person-weeks worth of work."* https://xp123.com/invest-in-good-stories-and-smart-tasks/
- **Over-splitting.** *"While I have often said that smaller stories are generally better there comes a time when to split further is not worth the time it will take to make the split."* https://tcagley.wordpress.com/2014/10/31/spitting-users-stories-more-anti-patterns/
- **Batch-size economics.** B11: *"The Principle of Batch Size Economics: Economic batch size is a U-curve optimization."* B12: *"The Principle of Low Transaction Cost: Reducing transaction cost per batch lowers overall costs."*
  **REFUTED CLAIM, RESTATED.** These were presented as "Reinertsen principles B1-B13". The page I fetched is a third-party Creative Commons wiki, it lists 22 B-principles, and it does not name Donald Reinertsen in its content. I did not read *The Principles of Product Development Flow*. Cite it as a third-party restatement. https://spinemodel.info/flow-principles.html

**Closing an input domain in one pass.**

- **Equivalence partitioning (ISTQB/ASTQB).** *"Equivalence Partitioning (EP) divides data into partitions (known as equivalence partitions) based on the expectation that all the elements of a given partition are to be processed in the same way by the test object."* The word "expectation" is load-bearing: EP's completeness is an assumption about the implementation, never a proof. That is precisely the incident — `bool` is a subclass of `int` in Python, so the "int" partition silently held a value the money path must reject, and EP would have reported it covered.
- **Boundary value analysis — negative result.** *"BVA can only be used for ordered partitions."* The failed domain was a TYPE domain, which is unordered. BVA was structurally incapable of finding any of the 32 refutations. Do not prescribe it for type gates. https://astqb.org/4-2-black-box-test-techniques/
- **Property-based testing (Hypothesis).** Stopping rule is a count, not a proof: *"Once this many satisfying test cases have been considered without finding any failing test case, Hypothesis will stop looking"*, default 100, and the docs concede *"Hypothesis may miss uncommon bugs with default settings."* What it does add, and what would have collapsed four rounds into one: failures are shrunk, saved and replayed automatically. https://hypothesis.readthedocs.io/en/latest/reference/api.html
- **Seven property shapes** (Wlaschin), useful because the real obstacle is stated on the page: *"the universal complaint is: 'what properties should I use? I can't think of any!'"* https://fsharpforfunandprofit.com/posts/property-based-testing-2/

**Positive control I ran, not a citation.** Python 3.14 on this machine, comparing an open guard against an exact type test across nine shapes:

```
1              isinstance(x, numbers.Real)=True   type(x) in (int, Decimal)=True
True           isinstance(x, numbers.Real)=True   type(x) in (int, Decimal)=False
'1'            isinstance(x, numbers.Real)=False  type(x) in (int, Decimal)=False
1.0            isinstance(x, numbers.Real)=True   type(x) in (int, Decimal)=False
Decimal('1')   isinstance(x, numbers.Real)=False  type(x) in (int, Decimal)=True
Fraction(1,1)  isinstance(x, numbers.Real)=True   type(x) in (int, Decimal)=False
float-subclass isinstance(x, numbers.Real)=True   type(x) in (int, Decimal)=False
__float__ obj  isinstance(x, numbers.Real)=False  type(x) in (int, Decimal)=False
None           isinstance(x, numbers.Real)=False  type(x) in (int, Decimal)=False
```

The open guard admits `bool`, `Fraction` and a `float` subclass, and REJECTS `Decimal`. It does not mean what it reads as. The exact test is two rows. That is the whole argument for criterion 1.

**The five phrases, mapped.**

- *One variable at a time* — a real published rule. Agans, *Debugging: The 9 Indispensable Rules*, rule 5 "Change One Thing at a Time": *"Change one thing at a time. You've heard of the shotgun approach? Forget it."* Verified on a fetched page: https://embeddedartistry.com/blog/2017/09/06/debugging-9-indispensable-rules/ (the publisher's own site, debuggingrules.com, does not list the rules). Also already written down in Matt Pocock's public skill: *"Change one variable at a time"*, plus *"Cut inputs, callers, config, data, and steps one at a time"*. https://raw.githubusercontent.com/mattpocock/skills/main/skills/engineering/diagnosing-bugs/SKILL.md
- *One button at a time* — Arrange-Act-Assert. *"Such multi-step unit tests are usually better off being split into several tests."* https://xp123.com/3a-arrange-act-assert/
- *One behavior at a time* — Given/When/Then supplies the shape; Fowler's page defines Given, When and Then and, checked explicitly, gives **no** guidance on scenario size or number of When steps. The "one `When`" rule in the skill is therefore this repo's own, not inherited authority. https://martinfowler.com/bliki/GivenWhenThen.html
- *One signal at a time* — no published counterpart found. Nearest anchor is Beck's test desiderata: Specific — *"if a test fails, the cause of the failure should be obvious"*; Composable — *"I should be able to test different dimensions of variability separately and combine the results."* https://testdesiderata.com/
- *One algorithm at a time* — property shapes, above.

**Is "smaller is better for agents" folk wisdom? Largely, yes — say so.**
I found no ablation that varies task granularity for a coding agent and reports resolve rate. The strongest on-point experiment located is human, not agent: di Biase, Bruntink, van Deursen and Bacchelli, *The effects of change decomposition on code review — a controlled experiment*, PeerJ CS 2019, 28 developers. Result, verbatim: *"Change decomposition leads to fewer wrongly reported issues, influences how subjects approach and conduct the review activity (by increasing context-seeking), yet impacts neither understanding the change rationale nor the number of found defects."* https://pmc.ncbi.nlm.nih.gov/articles/PMC7924728/

Decomposition did **not** find more bugs. It cut **false positives**. That is exactly the 32-refutation cost, so it is the right promise to make — and "fewer bugs" is the wrong one.

**Claims dropped as refuted or unsourced, and not used anywhere above.** The Mikado timebox (checked and absent). The quotation "thinnest possible" attributed to Walking Skeleton and Tracer Bullets (in neither source; I fetched neither, so I assert nothing about them). Bloomberg Pomona merge rates, SkillJuror's +4.1%, and the 400-line SmartBear/Cisco review threshold (accurate per the verifier, but I did not fetch them). Least-to-most, decomposed prompting, self-planning and ExploraCoder figures (four papers were carried behind one URL; I fetched none, so none is cited). Kanban Guide WIP limits. QuickCheck's `cover`/`checkCoverage`. Zeller's ddmin — splitting-test question 5 is inspired by 1-minimality, but I did not fetch the source, so the skill states it as this repo's own rule. The structure-versus-behaviour split (question 3) is commonly attributed to Kent Beck's *Tidy First?*; I fetched neither the book nor the newsletter, so the skill carries the rule with no attribution.

**HYPOTHESIS, unproven.** That criterion 1 (closed accepted-input set) actually reduces adversarial rounds. The mechanism is plain and the incident fits it, but n=1. The FALSIFICATION section makes it measurable across ten items.

---

## Part 3 — THE SKILL

````markdown
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

Five YES: build it. Everything below is how to answer question 1, and
how to know when to stop splitting.

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
| 1 | Money-path type gate: one exact type test at one entry point | the 13-shape table, written BEFORE the code: int, bool, float, float subclass, `Decimal`, `Fraction`, `'1'`, `''`, `None`, object with `__float__`, `complex`, `numpy` scalar, `datetime`. Accepted = exactly 2. |
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
````

**To install:** copy the block into `.claude/skills/unit-sizing/SKILL.md`.