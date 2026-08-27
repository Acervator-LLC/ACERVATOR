# Happy Path Avoidance — research and verdict

2026-08-11. 105 agents, adversarial 3-vote verification on every claim.
Twelve claims survived. The claims that did not survive are named where
they matter, because a refuted claim is a result.

## Verdict, in one paragraph

**Ship a skill, but reject the name and the framing.** "Happy Path
Avoidance" points at test-case enumeration, which is exactly the bloat the
operator feared, and enumeration is the weaker half of the evidence anyway.
Ship instead a short skill whose subject is **checks, not cases**: every
check must have a demonstrated ability to fail AND a demonstrated ability
to pass, observed at the surface the check reports through. Name it for the
published practice so it reads as adoption rather than coinage. Two rules
cover all six local incidents. The efficiency argument is structural rather
than measured, and that limitation is stated below rather than hidden.

## A. Prior art

### A3 — the mechanism already has a name, and it is not a happy-path term

An assertion that **passes on an incorrect state** is an ORACLE FALSE
NEGATIVE. One that **fails on a correct state** is an ORACLE FALSE
POSITIVE. Together they are ORACLE DEFICIENCIES.

Terragni, Jahangirova, Tonella, Pezze (ESEC/FSE 2020), verbatim: "they are
prone to both false positives and false negatives, which are jointly called
oracle deficiencies", followed by "a false negative is an incorrect program
state in which the assertion passes (but should fail)". Attributed to
Jahangirova, Clark, Harman, Tonella, *Test Oracle Assessment and
Improvement*, ISSTA 2016, 247-258. Independently corroborated by Molina et
al., arXiv:2405.12766 (2024).

The two-sided structure maps the local incidents exactly:

- incident 3 — `known_bad` exits 0 → oracle **false negative**
- incident 4 — analyzer can never pass a test file → oracle **false positive**

This is the single most useful result in the report. The local hypothesis
("the instrument agreed with itself") is real, but it is a **test oracle**
problem, not a happy-path problem, and it has a nine-year-old literature.

### A2/A3 — the published mechanism for "can this check fail?"

**Planted-fault seeding.** The OASIs oracle assessor seeds artificial faults
and reports the corrupted states in which the assertion still returns true.
*Checked coverage* is the cheaper published sibling for the same job.

### A2 — mutation testing: guidance, not measurement

Mutation score **works as guidance for strengthening a suite and fails as a
measurement of its effectiveness.**

- Pushing to the highest mutation scores improves real fault detection at
  fixed suite size by 8% (top 25%) and 11% (top 10%) on Defects4J, and 18%
  and 46% on CoreBench, over randomly selected suites of the same size.
- But only about **1%** of generated mutants behave like the real fault.

Use it to find where a check is weak. Do not report the score as a quality
figure.

### A4 — happy-path bias is real, and narrower than the folklore

Measured: the bias localizes to **syntax that only executes on failure**,
not to "error-handling code" as a category. `try` and `finally` blocks —
which run during normal flow — show coverage statistically
indistinguishable from non-error-handling code (Cliff's delta 0.06 TRY_IC,
0.12 TRY_BC, 0.16 FINALLY_IC, 0.14 FINALLY_BC; null hypotheses NOT
rejected).

This is a cost-side result as much as a coverage one: it says where the
discipline pays and where it does not.

### The strongest external support is measured, not analogical

Daikon-inferred assertions showed **zero false positives on the initial
tests BECAUSE those same test traces generated them** — the authors call
this "an expected result" — while their mutation score against an
independently built validation set (Randoop + PIT, different tools from the
generation pipeline) averaged only **38%**.

That is the local hypothesis, measured by someone else, years ago: an
instrument built from the same source as the thing it measures reports a
clean result and is blind.

### Industrial evidence that a green check can be blind

Across **1,502 high-priority real Google bugs**, mutation testing would
have reported a fault-coupled live mutant on the bug-introducing change for
**1,043 (70%)** of them — and every one of those changes was **already
covered by existing tests**, so line coverage had no signal left to give.

## B. The cost side

### B — no verified cost figure survived

The one cost anchor located (diff-scoped mutation cutting a median 820
mutants per changelist to 7) **FAILED 3-vote verification and must not be
cited.**

The efficiency case therefore rests on the **unit of work**: the
recommended rules scope to `O(checks)`, not `O(cases)`. A repository has
far fewer verdict-reporting checks than it has possible inputs, so the cost
does not scale with input space. **This is a HYPOTHESIS**, not a
measurement, and its falsifiers are listed below.

## C. The LLM-specific angle — UNANSWERED

**Zero of the twelve surviving claims touch C1, C2 or C3.** No verified
evidence was produced on:

- LLM agents writing tests that cannot fail (tautological assertions,
  asserting on the mock rather than the behaviour)
- LLM confirmation bias in verification design
- published mitigations (independent verifier agents, adversarial critics,
  red-first as an anti-tautology device, differential testing, N-of-M voting)

**The novelty suspected in the brief is unverified.** Do not build the
skill on a claim about LLM-specific behaviour; build it on the oracle
literature, which is solid.

### A negative finding worth keeping

**Do not build on confirmation-bias psychology.** The most-cited software
paper linking confirmation bias to defects rests on defect data from five
developers, reports no significance test for that correlation, and concedes
it needs more data "to obtain statistically significant results". Its
quantitative bias index does not track defect ratio across those five.

## D. The deliverable

### D1 — verdict

Do NOT ship "Happy Path Avoidance". Ship a skill about **checks**, named
for the published practice (two-sided control / oracle deficiency).

### D2 — the smallest rule set is two rules, covering all six incidents

**RULE 1 — TWO-SIDED CONTROL AT THE VERDICT SURFACE.** Every check that
reports a pass/fail verdict must be observed FAILING on a planted defect
and PASSING on a known-good fixture — both read **at the surface the check
reports through**, never at an intermediate.

Catches incidents 2 (model vs pixel), 3 (`known_bad` exits 0), 4 (analyzer
can never pass), 5 (`$?` read the wrong command), 6 (both regexes wrong).

**RULE 2 — AN ENUMERATED TABLE DOES NOT CLOSE A NUMERIC DOMAIN.** Where a
decision turns on rounding, quantization or a threshold, sweep or
property-test the domain instead of hand-writing rows.

Catches incident 1 (8 rows passed, 113 silent changes).

### D3 — falsification

The skill is not earning its cost if:

- a two-sided control is added and, over ten changes, never once fails on
  the planted-defect side — the plant is too easy and proves nothing
- rule 2 sweeps find zero disagreements over ten numeric changes
- the controls themselves become a maintenance burden exceeding the defects
  they surface
- an oracle false negative reaches live behind a check that carried a
  passing two-sided control

### D5 — the residual, measured twice at scale

**Planted-fault validation has a hard ceiling at specification-level and
wrong-algorithm error.**

- Just et al. 2014: **63 of 357 real faults (18%)** fell in the "no such
  operator" category, 44 of them algorithm modification or simplification.
- **118 of 480 (25%)** tests that demonstrably caught a real fault killed
  zero additional mutants.

A check whose whole premise is wrong will pass its own two-sided control.
Neither rule catches "we built the wrong thing".

## What this changes locally

The six incidents were not six testing failures. Five were oracle
deficiencies and one was an unclosed numeric domain. The existing repo
memories already circle this — *calibrate the instrument*, *measure before
reporting*, *no harness no validity* — without naming it. The literature
name is **oracle deficiency**, and the mechanism is **planted-fault
seeding**.
