---
name: structurally-impossible
description: Load before writing or changing Python under src/. Put a property in the structure so the wrong value cannot be written, instead of checking for it afterwards. Invoke by name when the operator says the same number is in two places, or asks why one fix had to be made many times.
---

# Structurally impossible

**Put the property in the structure. Then the defect cannot be written.**

A check finds a wrong value after someone wrote it. A structure stops it being
written. `.claude/rules/tests.md` already states the preference: a shared method
makes drift structurally impossible, and that is stronger than any assertion
about the source.

This page holds eight rules. Each one says which archetype run reports on it.
Where no run reports, the page says so, and the rule then rests on judgement
alone.

## One value lives in one place

A value that two files both state can disagree, and nothing says which is right.

Measured in this tree: `SECONDS_PER_MINUTE = 60` is written out in eight source
files. The same reading gives six files for a cell alignment number and five for
seconds in an hour. Each is one decision held in many places.

```
git grep -hE '^[A-Z][A-Z0-9_]{3,} = [0-9]' -- 'src/*.py' \
  | sed -E 's/^[0-9]+://; s/ *#.*//' | sort | uniq -c | sort -rn
```

**No archetype run reports this.** The coding archetype was run on
`src/exchange/fetch_stall.py`, which carries one of the eight copies, and on
`src/trading/indicators/fvg.py`, whose four constants repeat nowhere. Both read
`passed=True` with all twelve analyzers `ok`, and neither reading held a finding
that named the repetition. `slop.py`, in `_find_duplicate_try_except`, reports
one try and except shape inside one file, and reads nothing across files. The
documentation archetype reports a repeated heading inside one page and nothing
wider.

So this rule is judgement. One module owns the value, and every other module
imports it.

## Check the data where it enters, and trust it inside

A value checked at the edge needs no second check deeper in. A value checked
deep in is checked in every path that reaches it, and one path always gets
missed.

**The coding archetype reports part of this.** `mypy` and `pyright` both read
`ok` and both report a value used where its type does not fit. `passed` for this
rule means neither tool reported a type error on the file. Where the check
physically sits is not something either tool reads, so that half is judgement.

## Keep the decision in a function that only computes

A function that reads a venue, writes state and decides in one body cannot be
driven on its own. Split the decision out. Give it values, take a value back.

**No archetype run reports this.** The phrase names nothing in any archetype
rule, and nothing in the other thirty-two skill pages. It is judgement.

The gain is measurable in this tree even so: `debugging` requires that a defect
is reproduced before it is fixed, and a function that only computes can be
reproduced from a value instead of from a running platform.

## Make the wrong value impossible to write, and parse outside data once

Where a type can carry only right values, a wrong one does not compile.

Measured in this tree, the cost of the opposite: `amount_precision` was named
for a count of decimal places and received a step size, and
`variable-naming-precision` records 886 of 929 markets sized wrong for a year
because nothing forced the name and the value to agree.

**The coding archetype reports part of this.** `mypy` and `pyright` report a
wrong type. `ruff` reports an unnamed number used in a comparison under rule
`PLR2004`; the run on `src/trading/indicators/fvg.py` reads *Magic value used in
comparison, consider replacing 3 with a constant variable*.

**Read the severity.** That finding is `low`, and the verdict trips only on
critical and high. A file reads `passed=True` while carrying it. `passed` alone
does not clear this rule; the finding list does.

## Running it twice ends in the same state

An action the operator can press twice, or that a crash interrupts, leaves one
state and not two.

Measured in this tree: `harness-law` records a method that left durable
half-applied state when a value conversion raised part way through a write, and
it did so behind a green gate.

**No archetype run reports this.** No rule in any archetype reads whether an
action can be repeated. It is judgement, and the way to settle it is to run the
action twice and compare the stored state.

## One writer, and the structure holds it to one

Where two paths write one thing, name one of them the writer and let the other
read. Where they do not need the same thing, give each its own.

Measured in this tree: `branch-discipline` records two jobs writing one scratch
file, and the second job read back content it had not written. It survived only
because the colliding value had the wrong shape.

**No archetype run reports this.** It is judgement. Name the writer in the
module that owns the value.

## Take complexity out before putting any in

Remove first, then add. A file that grows on every change ends up holding more
paths than anyone reads.

**The coding archetype reports part of this.** `vulture` reads `ok` and reports
what nothing reaches, under `dead-code`. The run on
`src/exchange/fetch_stall.py` held ten such findings and the run on
`src/trading/indicators/fvg.py` held four. `ruff` reports a function that holds
too many paths under rule `C901`, at a threshold of ten, and the reading on
`src/trading/indicators/fvg.py` is *compute is too complex (12 > 10)*.

**Both are `low`.** They do not move the verdict. Read them in the finding list.

**And removal is not deletion here.** `reachability-first` requires that an
unused file is quarantined first and deleted only when the operator calls for
it. A `vulture` finding is a reason to quarantine, never a licence to delete.

## Redesign rather than bolt a new requirement on

Where a change does not fit the shape that is there, the shape is the work. Ask
what the module would look like if the new requirement had always been in it.

**No archetype run reports this.** It is judgement, and it is bounded by two
rules already in force. `widest-true-reading` sets the bar at the widest reading
of the directive. `unit-decomposition` sizes the redesign into units that each
finish in one pass, so a redesign never lands half done.

## What reports on these eight rules

| rule | the run that reports | what `passed` covers |
|---|---|---|
| one value in one place | none | nothing; judgement |
| check at the entry | coding archetype, `mypy` and `pyright` | the type, not the place |
| a function that only computes | none | nothing; judgement |
| the wrong value cannot be written | coding archetype, `mypy`, `pyright`, `ruff` | type errors; `PLR2004` is low |
| running it twice | none | nothing; judgement |
| one writer | none | nothing; judgement |
| subtract before adding | coding archetype, `vulture` and `ruff` | `dead-code` and `C901`, both low |
| redesign rather than bolt on | none | nothing; judgement |

Five of the eight rest on judgement. Three route through runs that already
report, and in all three the findings are `low`, so the verdict does not move on
them. **A reader quoting `passed` has not cleared any rule on this page.** Quote
the rule id and the finding.

Nothing here adds a rule to any archetype. `dev_harness/harness/` is the
operator's, and a missing report is a proposal for him.

## The open proposal

No program in this harness reports one value written in several places. The
reading above is two-sided and the gap is real.

`pylint` reports repeated blocks under rule `duplicate-code`. `jscpd` reports
the same across languages and covers markdown as well as Python. Neither is
installed: both are absent from pip and from `node_modules`, while `ruff` and
`eslint` are present, which is the control showing the absence reads.

Neither reports a single repeated line at its default floor, so the eight-file
constant measured above needs the similarity floor set to two lines, or a low
token count. **Installing either is the operator's call.**

## Falsification

This page is wrong if:

- Any archetype run starts reporting one value written in several files. Then
  the first rule has a route and the proposal is closed.
- The three routed rules turn out to need no judgement, because the tools fully
  decide them. Then those three rows belong in `canonized-code-testing` and not
  here.
- A unit holding this page produces a repair that a rule here forbids. Then the
  rule is wrong and it comes to the operator, not to the code.
- The five judgement rules change nothing across ten units. Then they are
  ceremony and they are cut.

Related: `harness-law`, `canonized-code-testing`, `reachability-first`,
`variable-naming-precision`, `widest-true-reading`.
