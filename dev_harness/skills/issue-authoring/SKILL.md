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

## Folding one issue into another

When a feature's issues are consolidated: map every concept from the absorbed issue onto a concept in the host, report the mapping, add only what is missing, carry each absorbed blocker into its concept's status cell, then comment on the absorbed issue naming the host and close it. Its comments stay — they are the record.

## Falsification

This skill is wrong if a body written to it produces a brief whose premise the code contradicts. Then an unanchored row survived the anchor rule, and the rule needs tightening rather than reapplying.

Related: `docs-narrative` for prose shape and citation density, `ocir` for the gating rows, `manual-is-the-map` for the manual's own standard.
