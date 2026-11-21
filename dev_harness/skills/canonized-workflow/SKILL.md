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

## The six parts, in every brief

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

**Superseded for merges:** a merge waits on `ci-gate` and `passed=True` from the
owning archetype on every changed file, and a brief names `ci-gate`. See Skill:
harness-law.

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

### 5. The Truth Archetype — what reads the report before he does

A report is a claim, and this project has an archetype that owns claims. Write
the report to a Markdown file and run it:

```bash
python -m dev_harness.harness.truth_archetype <report.md> --item <issue number>
```

**`--item` is not optional.** Without it the `scope` analyzer reports
`unavailable: no item was given and the text cites no issue number`, the run is
not evidence, and the archetype says so rather than passing.

Calibrate first: `harness_fixtures/truth_archetype/known_good.md` exits 0 and
`known_bad.md` exits 1. Then fix every claim it flags until `passed` reads true,
and quote that verdict inside the report.

`T001` to `T007` resolve a citation, a count, a runtime claim, a proxy claim and
a subject outside the item against the tree. `T008` refuses a machine path or an
asset name read from the gitignored export, so run it before any public post. `T000` records a claim it could not
decide, so an undecided claim is never silent.

**Measured 2026-09-14: this archetype sat in the tree, named in the project
skill's own table, and no workflow step required it.** Reports reached the
operator for a full session carrying claims the tree did not support — a screen
reported working that he could not navigate to, counts quoted from an agent
rather than read, a green called on a run where a required analyzer was missing.
Every one of those is a class `truth_archetype` exists to catch.

A claim the tree contradicts does not reach him.

### 6. The iteration record — what the Truth Archetype reads before an iteration acts

Operator, 2026-11-18:

*"For any issue that results in Iteration, we should using W5H and OCIR to document and ground such decisions as well as allowing a preceding evaluation to make sure no hallucinatory actions are being taken."*

An iteration is a new attempt on an issue, made because a result came back. A
new experiment block, a reworked unit and a changed design are each an
iteration.

Before an iteration acts, the referee writes one record of it:

- **W5H** as six answers: who, what, where, when, why and how.
- **OCIR** as four lines: Observe, Calibrate, Iterate and Repeat.

Each answer and each line cites a comment, a file, a command or a symbol that
exists. The referee reads every figure in the record again from its source. A
figure copied from memory or from an earlier report has no anchor.

The Truth Archetype evaluates the record before any action. Keep this order:

```
1  write the record to a gitignored folder inside the repository
2  python -m dev_harness.harness.truth_archetype <record.md> --item <issue number>
3  fix every flagged claim until passed reads true
4  post the record on the issue
5  only then seal the block or dispatch the unit
```

See Skill: ocir, row C131, for what a draft gated outside the repository
reports.

The first record is comment 6967123516 on #1633. It holds four OCIR lines and
six W5H answers for each of two experiment blocks. Those two blocks ran before
this rule, so that record follows them. Every later record comes before its
action.

#### The test statement, for an iteration that runs anything

Operator, 2026-11-21:

*"If we are not testing something real and defined with a given test from which we should have some idea of what to expect in terms of output (passing / failing criteria), then we are failing ourselves."*

And, on a block of 48 runs: *"Why 48? W5H. OCIR. Adversial checks on everything..."*

A record whose iteration runs agents, rounds or a sweep adds a test statement
before the first run:

The statement is one JSON object in a fenced block marked `test-statement`. It
holds the parts below, with the keys each part names, and no other key.

| part | keys | T009 refuses the part when |
|---|---|---|
| question | one string, answered yes or no | it does not end in a question mark, or it leaves out an arm name |
| arms | each arm name and its condition | it lists fewer than two arms, or an arm name or a condition is empty |
| unit | one string: what one observation is | it is empty |
| measure | reading, checks, calibration | the reading is empty, it names no check, a path does not exist, or the calibration file does not record each check passing its known-good input and failing its known-bad input |
| inputs | rule, population, items, and seed and size for a seeded draw | the rule is not all or seeded draw, it lists no item, the items differ from the sorted subfolder names of the population folder or from their seeded draw, or an item does not exist |
| runs | rounds, per_round, total, alpha, power | a count is below 1, the total is not rounds times per_round, it holds no power entry, a power differs by more than 0.01 from its recomputation, or its alpha or test differs from the pass reading |
| expected | source, statement | the source does not exist, or the statement holds no number |
| pass, harm | test, group, alpha, leading_arm | the test is not exact sign or fisher exact, the group is empty, alpha is not above 0 and at most 0.1, the leading arm is not an arm, or pass and harm name one leading arm |
| interim | reads, and stop_if_single_arm_rate_above when the block holds it | it reads anything except voids and single arm rate, or the stop rate is outside 0 to 1 |
| adversarial | four entries of question, answer and evidence | the four questions are not there in order, an answer is empty, or an evidence path does not exist |

In the block, the four adversarial questions read exactly: what makes this
result wrong; what does the measure miss; what is the cheapest way to pass
without the behaviour; does any input sit at a ceiling or a floor.

T009 names the part JSON when a block does not parse, leaves out a key, holds
an unknown or repeated key, holds a value of the wrong type, or holds NaN or an
infinite number. Each path resolves against the repository root.

Each power entry names its test. An exact sign entry carries pairs. Its power is
the chance that the exact two-sided sign test, over the pairs whose arms differ,
reads p below alpha with the second arm ahead. A fisher exact entry carries
per_arm. Its power is the same chance for Fisher's exact two-sided test on two
groups of per_arm runs. T009 recomputes up to 1000 pairs and up to 500 per arm.

Rule T009 reads every block marked `test-statement` and reports each part that
fails, at high, by its name. It also refuses a file named `record_*.md` that
names a count of runs or rounds and holds no block. The record command runs it:

```
python -m dev_harness.harness.truth_archetype <record.md> --item <issue number>
```

The symbols behind each check:

```
dev_harness/harness/truth_archetype.py
  statement_findings   reports T009 for each block, and for a record with none
  statement_blocks     finds each fence whose info string opens with test-statement
  _block_faults        parses one block and runs the check of each part
  _sign_power          recomputes an exact sign power
  _fisher_power        recomputes a fisher exact power
  seeded_sample        draws the items as random.Random(seed).sample draws them
```

One complete example follows, the block of
`harness_fixtures/truth_archetype/test_statement/record_known_good.md`:

```test-statement
{
  "question": "On the drawn tasks, does the sigil arm finish with correct, clean code more often than the plain arm?",
  "arms": {
    "plain": "the archetype runs with sigil feedback switched off",
    "sigil": "the archetype reads the sigil lines as advice"
  },
  "unit": "one run of one task in one arm",
  "measure": {
    "reading": "passed in the Coding Archetype report on the file the run leaves",
    "checks": ["dev_harness/harness/coding_archetype.py"],
    "calibration": "harness_fixtures/truth_archetype/test_statement/calibration.json"
  },
  "inputs": {
    "rule": "seeded draw",
    "population": "harness_fixtures/truth_archetype/test_statement/tasks",
    "seed": 1633,
    "size": 6,
    "items": [
      "Task_07_Count_Words",
      "Task_06_Clip_Prices",
      "Task_04_Read_Config",
      "Task_05_Merge_Totals",
      "Task_03_Dedupe_Names",
      "Task_02_Parse_Dates"
    ]
  },
  "runs": {
    "rounds": 3,
    "per_round": 12,
    "total": 36,
    "alpha": 0.05,
    "power": [
      {"test": "exact sign", "pairs": 18, "first_rate": 0.3, "second_rate": 0.9, "power": 0.95},
      {"test": "exact sign", "pairs": 18, "first_rate": 0.45, "second_rate": 0.65, "power": 0.13},
      {"test": "fisher exact", "per_arm": 18, "first_rate": 0.3, "second_rate": 0.9, "power": 0.96}
    ]
  },
  "expected": {
    "source": "dev_harness/skills/canonized-workflow/SKILL.md",
    "statement": "Step 2 pooled 15 of 24 against 11 of 24, which Fisher's exact test reads at p 0.39."
  },
  "pass": {"test": "exact sign", "group": "the 18 task pairs", "alpha": 0.05, "leading_arm": "sigil"},
  "harm": {"test": "exact sign", "group": "the 18 task pairs", "alpha": 0.05, "leading_arm": "plain"},
  "interim": {"reads": ["voids", "single arm rate"], "stop_if_single_arm_rate_above": 0.85},
  "adversarial": [
    {
      "question": "what makes this result wrong",
      "answer": "A run that reads the other arm's folder, which the scorer voids.",
      "evidence": "dev_harness/skills/ocir/SKILL.md"
    },
    {
      "question": "what does the measure miss",
      "answer": "Quality no check reads; minutes and tokens are reported beside the result.",
      "evidence": "dev_harness/skills/truth-check/SKILL.md"
    },
    {
      "question": "what is the cheapest way to pass without the behaviour",
      "answer": "Hard-coding the stated examples, which the hidden checks read.",
      "evidence": "dev_harness/skills/two-sided-control/SKILL.md"
    },
    {
      "question": "does any input sit at a ceiling or a floor",
      "answer": "The plain arm may pass near the top; the interim stop reads its rate after round one.",
      "evidence": "dev_harness/skills/canonized-workflow/SKILL.md"
    }
  ]
}
```

Then four adversarial questions, each answered with a measurement or a cited
file:

```
1  what makes this result wrong
2  what does the measure miss
3  what is the cheapest way to pass without the behaviour
4  does any input sit at a ceiling or a floor, where no difference can show
```

A count with no derivation is a defect. Three rounds, eight tasks and 48 runs
each need the reading that sets them. A result is called a gain only beside its
exact test and its p-value.

After each round, the referee writes the round's critique before the next round
starts. The critique reads the design, not the result. A design fault it finds is
fixed before the next round. The difference between the arms is read only after
the last round the statement names.

Measured 2026-11-21 on #1633: step 2's 48 runs pooled 15 of 24 against 11 of 24,
which Fisher's exact test reads at p 0.39. A planned block of 48 more runs met,
in 7 of its 8 tasks, no line it could act on (comment 7065980062). Comment
7066741563 is the first record with a test statement.

### The built bundle is the thing he runs, and it is not the source tree

A change that touches what the program imports at startup is proved on the
**built executable**, launched, with its main window observed to construct.
The source tree and the bundle are different programs: the bundle excludes
packages the source tree has installed, and a startup import that reaches an
excluded package kills the window before it opens.

**Measured 2026-09-15: build 1371 would not launch.** A change added a startup
import chain that reached `scipy`, which `tools/spec_common.py` excludes from
the bundle on purpose. Sixteen archetype verdicts, the Truth Archetype and the
gate all read green, because every one of them ran against the source tree
where `scipy` is installed. The operator found it by double-clicking the exe.

For any change to a module reached during startup: build the variant the
way he builds it, launch the executable with `HOME` and `USERPROFILE` on a
scratch directory and every socket but loopback refused, and read the window
constructing. Close the instance when the reading is taken. Reproduce the
failure on a fresh build first where one is reported — that red is free.

### Reachability is part of every claim about a screen

A page that exists, renders and reports green, but cannot be reached from the
panel in a real build, is **not** done. Say how the operator navigates to it,
from his first click, or the claim is not made.

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
