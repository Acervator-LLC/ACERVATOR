---
name: issue-authoring
description: How to author and maintain a feature issue for this operator. Load before writing or rewriting any issue body. Governs the concept statement, the build order, the concept-subsystem-status tables, and what never appears in a body.
---

# Issue Authoring

**One feature, one issue, and the body is the current state.** Comments hold history.

## Why the shape matters more than the prose

An issue body is read back as the grounding for the next unit's brief. An unanchored sentence in it becomes that unit's premise, and the unit builds on it. Measured 2026-09-11: two wrong claims reached briefs that way and the units built against them.

Operator, same day:

> "Writing issues this way is exactly what causes hallucinations. Substance is improved over all but you are using too many words and saying too much that makes no sense or is not relevant to what was worked on..."

> "We only want concepts, subsystems, and completion status under the PoA Issue."

> "No old quotes or notes. Actionable substance only."

**The volume is the defect, not a side effect of it.** A 1,392-line body rebuilt to 99 lines lost no decision and corrected five false statements that had been feeding briefs for weeks.

## The shape

```
# <Feature>

<the crystallised concept: what the thing IS, in present tense, 1-2 short paragraphs>

## The spine
<a code block: the few invariants everything else hangs from>

## <Verb set, where the feature has one>
| Verb | Subsystem | Status |

## W5H is the format for every issue

Operator, 2026-09-13: *"W5H will now be the format for ALL issues."*

Not the settings audit alone, and not the large issues alone. Every issue, every
row in it, and every unit dispatched against one.

**In the body.** An issue states the six questions once, near the top, so a
reader knows what an answered row looks like:

- **who** — what builds or calls the thing, in the running program
- **what** — what changes when it runs
- **where** — every site that names it
- **when** — at which moments it runs
- **why** — the manual sentence that says what it is for, quoted with its
  location. Where none exists, the answer is **nothing** with the count that
  shows it
- **how** — the path from the operator's action to the value or the pixel at
  the end of it

**Per unit.** The six answers are posted as a comment on the issue **before any
code changes**, each carrying a file and a line. A unit that changed code before
posting has broken the format, whatever the code does.

**Where the answer is nothing**, write nothing and give the count that proves
it. An absence stated with a figure is an answer; an absence left silent is a
gap.

**A row closes on one of five outcomes** — verified, fixed, completed, removed,
it waits — and a row that waits names the row it waits on.

**The evidence is the running program.** A value driven through the real path, a
picture of the screen, a count taken with a control that proves the search could
report. Never a passing check on its own: a check reports on code, and he reads
the program.

## A W5H miss informs OCIR

Operator, 2026-09-13: *"W5H misses inform OCIR."*

A question that could not be answered, or that was answered and later proved
wrong, is not a footnote in the report. It is a defect in how the thing was
measured, and it becomes a row in the OCIR catalogue.

Three kinds of miss, and each earns a row:

- **Unanswerable.** No route in the canon reaches the question. The row names
  the question and what would have to exist to answer it.
- **Answered wrongly.** The answer was stated and the running program then said
  otherwise. The row names the shape that produced the wrong answer, not the
  wrong answer itself.
- **Answered narrowly.** The answer was true of the filter and not of the world
  — a count taken with a pattern narrower than the thing being counted.

The row carries what every OCIR row carries: the shape, the measurement that
showed it, one question to ask before trusting a result of that kind, and the
command to run instead. A row with no measurement behind it is not written.

**This closes the loop.** W5H asks the six questions, OCIR records how the
answers went wrong, and the next brief carries the question that would have
caught it.

## Build order
### Layer 0 — <name>
| # | Concept | Subsystem | Status |
### Layer 1 — <name>
...

## Where the complexity sits
<a code block naming the structural doublings>

## <Decisions that unblock work>
| # | The decision |

## <Recommendations, labelled as the author's own>
```

## The four rules

**1. Every row carries an anchor that exists.** A path, a symbol, a constant. Verify each one on disk before it ships. A cited path that does not exist is what the documentation archetype's hallucination rule catches, and a body full of them teaches the next unit to cite things that are not there.

**2. Status is one of four words, and a blocked status names the decision.**

```
built      reachable and doing what the concept says
partial     some of it works; the status says which part does not
unbuilt     no subsystem serves it
blocked on <the decision>      the status column IS the action list
```

A concept blocked on an unset figure names that figure here and nowhere else. A separate owed-figure inventory is the thing that made the body soup.

**3. Build order follows the domain's natural layering, not the order of work.** Find how the field itself layers a system of this kind and use that. For a game: identity and currency, the body, the world, the non-combat verbs, combat, classes and abilities, groups, content, endgame, presentation. The order a team happened to build in is history and belongs in the comments.

**4. Name the structural doublings.** Two currencies, two clocks, two grids, one list serving two ladders. Each doubling forces every rule above it to be stated twice and is a live source of unset figures. Collapsing one removes more open questions than building anything new. This section is usually the most useful thing in a body.

## What never appears in a body

- A quote of the operator. His words live in the comments.
- A unit number, a branch name, a PR number, a commit.
- A bug history, a measurement reading, an archetype verdict.
- A sentence about what used to be true, what was discovered, or what a session did.
- A legend, a routing table, or any section describing the document itself.
- A derivation. Keep the conclusion; the reasoning is a comment or a design note.
- An empty table written to fill the shape.

## Decisions that unblock work

A table of the operator's **own** rules in conflict, or a rule with no reading. One line each, naming both halves. This is the highest-value section for him, because each row is a sentence only he can write, and every one of them is holding up code.

Do not pad it with questions an implementation choice answers. A question the code or a precedent already settles is the author's to decide, not his.

## Recommendations

Allowed, labelled as the author's own, at the end, and short. Never mixed into the status tables as if measured.

## Drafting and publishing

Draft in a **gitignored directory inside the repository**, gate it there, publish with `gh issue edit <n> --body-file`, then remove the draft and prove the tree is clean.

Gating from outside the repo reports every real path as dead: the hallucination rule finds its root by walking up for a `pyproject.toml`, or for a directory holding both `src/` and `tools/`. A scratch directory has neither. One unit read 76 false dead paths that way. See `ocir` row C131.

GitHub keeps the previous body in its own edit history, so a rewrite destroys nothing.

**The gate has to BLOCK the publish, not print beside it.** A reader that prints
`passed` and exits 0 either way lets a red body through, and it did: two sentences
the rule refuses reached a published body because the publish ran in the same
chained command. Make the reader exit non-zero on a false verdict, so the chain
stops:

```python
sys.exit(0 if report["passed"] else 1)
```

Then `gate && gh issue edit ...` cannot publish a body the archetype refuses. A
verdict nothing branches on is not a gate.


## A unit's absences become rows, before the next unit goes out

Operator, twice: *"Still Absent - Make sure these all get units if needed. Make it
a habit please. Might as well fill in as many related gaps under one Issue as we
can."*

Every unit brief ends by asking for a **Still Absent** list. When the report
arrives, each item on that list ends in exactly one of three places, and none of
them is a sentence in a reply:

- **a new row** in the issue's raised-units section, numbered in sequence
- **an addition to a row that already exists**, when the item is that row's
  subject
- **the issue's standing harness proposal**, when the item is a missing check,
  which is the operator's to accept and never a unit

A gap is a new unit or an addition to the current unit. It is never a caveat.

**And say so in the reply, naming the row numbers.** Placing them is half the
rule; he cannot see the issue body from the terminal, so an unreported placement
reads as a skipped one. He has asked twice — *"Make sure the Still Absent items
are added as Units"*, then *"Did not see the notice"* — after every item was
already placed. One line per report is enough:

```
Absences went in as rows 248-250.
```

Name any item that did NOT become a row, and where it went instead.


**Do this before the next unit is dispatched, not at the end of the issue.** The
habit holds only if it runs while the report is in front of you.

**Then count.** Read the row numbers out of the published body and check the
sequence has no gap:

```bash
gh issue view <n> --json body --jq .body > <gitignored path>/body.md
```

and count the rows against the highest number. A missing number means an item was
dropped between the report and the body, which is the one failure this section
exists to catch.

## An add-on unit resolves what it finds. It does not hand back a list.

Operator, 2026-09-13: *"we need to stop adding 6+ Still Absent items to these
subsequent Units that are already additional units. Start resolving everything
found in a Unit with the Unit it is found in if the Unit is already an add on.
Otherwise, this Issue may never get closed."*

The section above governs a unit that works an **original** row. Once a unit is
working rows that an earlier unit raised, the rule inverts: its findings are its
own work, not the next unit's.

**The arithmetic that forced this.** Six add-on units in one session returned 6,
7, 6, 5, 7 and 6 absences. Each closed 4 to 6 rows and opened about the same
number, so the open count did not fall. An issue whose rows grow as fast as they
close has no end state.

Every add-on brief carries this paragraph, in these terms:

> This unit is an add-on, so you resolve what you find. Do not hand back a list.
> Exactly two kinds of thing may come back unresolved, one line each: work that
> lands in a file another branch holds, named; and a decision that is his — a
> product capability, a surface he can see, or a sentence of his own prose.
> Never a code question.

**Two kinds, and no third.** "It is out of scope" is not one of them, and
neither is "it deserves its own unit". A finding inside the files the unit
already has open is that unit's work.

**Where the two survivors go.** A blocked file becomes a line inside the row it
belongs to, so the row stays open carrying its own remainder. A decision becomes
a one-line question in its row, phrased so he can answer it without reading
code. Neither becomes a new row.

**The count is the check.** After writing an add-on unit's outcomes, the highest
row number must not have moved. If it did, the unit handed back work and the
brief did not bind.

## No Still Absent. Fix it, then, in the unit that found it

Operator, 2026-09-13: *"THERE WILL BE NO STILL ABSENT OR STILL NEEDS SHIT
ACCEPTED FOR ANY W5H ITEMS GOING FORWARD. YOU FIX IT ALL. YOU DO IT RIGHT. YOU
DO IT THEN. YOU LEAVE NO GAPS. YOU APPLY HYPER FOCUS AND SEE IF THE OBSERVED
ABSENCE APPLIES TO THE WORK IN WHICH IT WAS OBSERVED."*

**The Still Absent section is retired**, and with it every phrasing of it:
owed, still needed, follow-on, next unit, out of scope for now. A brief that asks for one is
wrong and a report that carries one is not finished.

### The test, run on every absence the moment it is observed

**Does this absence apply to the work in which it was observed?**

- **Yes** — fix it now, inside that unit, with the same proof the unit owes for
  everything else. Not a row, not a note, not a queue entry. Then.
- **No** — it is not that unit's finding. Drop it. Do not caveat it, do not
  mention it in the report, do not open anything for it. Noticing something true
  while working elsewhere is drift, and it defends itself by feeling like
  diligence.

No third answer exists. "It is real but it belongs to another file" is the
second answer, and the second answer is silence.

### The one thing that still comes back

A decision that is his: a product capability, a surface he can see, or a
sentence of his own prose. One line, inside the item it belongs to, phrased so
he can answer it without reading code. Never a code question.

### Do not manufacture a gap by scheduling

An absence that is genuinely this unit's work, blocked only because another unit
holds the file, is a gap **I created** by running two units over one file. Run
one at a time instead. A scheduling collision is not an exemption.

### Why this rule exists

Measured 2026-09-13: six add-on units returned 6, 7, 6, 5, 7 and 6 absences
each. They closed four to six rows apiece and opened about as many, so the open
count never fell. Work that hands back as much as it finishes is not work.

## Folding one issue into another

When a feature's issues are consolidated: map every concept from the absorbed issue onto a concept in the host, report the mapping, add only what is missing, carry each absorbed blocker into its concept's status cell, then comment on the absorbed issue naming the host and close it. Its comments stay — they are the record.

## Falsification

This skill is wrong if a body written to it produces a brief whose premise the code contradicts. Then an unanchored row survived the anchor rule, and the rule needs tightening rather than reapplying.

Related: `docs-narrative` for prose shape and citation density, `ocir` for the gating rows, `manual-is-the-map` for the manual's own standard.
