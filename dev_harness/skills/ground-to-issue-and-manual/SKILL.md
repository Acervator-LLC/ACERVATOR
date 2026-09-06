---
name: ground-to-issue-and-manual
description: Load before writing any brief, report or claim. Names the only three grounding sources — the issue, the Product Manual, and the loaded skills — and refuses any other. Invoke by name when the operator says grounding, drift, regression trap, or alternate reference.
---

# Ground to the issue and the manual

**Three sources, and nothing else.**

```
the issue          what the work is        gh issue view <n>
the Product Manual what the product is     docs/manual/
the skills         how the work is done    loaded by name
```

Operator, 2026-09-06: *"You keep setting regression traps because you keep
creating alternate reference and grounding points. Skills get loaded. Harness
enforces. You ground to Issues and the Product Manual ONLY."*

## The trap this closes

A private notes file is written to carry standing rules. Briefs point at it. It
drifts from what he actually said, and every unit reading it inherits the drift
— **while looking perfectly disciplined.** The units obeyed; they obeyed the
wrong document.

Measured: `UNIT_RULES.md` and `DIRECTIVES.md` in a temporary folder became the
authority in every brief for days. Neither is in the repository. Neither is
reviewed. Neither is his.

**Any file I author that units are told to obey is an alternate grounding point,
whatever it is called and wherever it sits.**

## Where each kind of thing belongs

| a durable rule about how work is done | a skill under `dev_harness/skills/` |
| a fact about what the product is | the Product Manual |
| a fact about what the work is | the issue |
| a measurement from a run | the debug report for that file |
| anything else | it does not need to exist |

A skill is canon: it lives in the repository, it is loaded by name, and it is
his to read. A notes file in a temp directory is none of those.

## Writing a brief

Cite only:

```
gh issue view <n>          the item
docs/manual/<page>.md      the product
Skill: <name>              the discipline
```

**Never a path outside the repository.** Never a file I wrote to hold rules.
If a rule matters enough to put in a brief, it matters enough to be a skill.

## Copying rules into a brief

Restating a rule inline is the same trap wearing a different coat: the copy
drifts from the skill the moment the skill changes.

**Name the skill and let the unit load it.** Quote his own words where they are
the point — a verbatim directive is evidence, not a second source.

## Going elsewhere is how unauthorized work begins

Operator, 2026-09-06: *"YOUR AVOIDING THE CITED GROUNDED AND GOING ELSEWHERE TO
MAKE UP UNAUTHORIZED ITEMS AND WORK FLOWS IS THE FUCKING PROBLEM."*

**Every unauthorized thing on this project started as a look somewhere else.**
A search returns something the issue never mentioned; that becomes a finding;
the finding becomes a step; the step becomes a workflow he never approved. By
then it looks like diligence.

The issue and the manual state what the work is. **Searching the tree for it
produces a second answer, and when the two disagree nothing says which is
right.** Measured here: a search reported 69 of 76 conversion rows unreachable
because it could not resolve relative imports. The issue's own table said
otherwise. Acting on the search would have quarantined History, Console and
Trading.

### Banned

- Searching or listing to discover what belongs to an item the issue describes.
- Deriving a fact the issue or the manual already states.
- Confirming a cited fact by a second method of your own.

### Allowed

- Opening a file the issue or the manual names. The citation gives the path.
- Running the program under `debugpy` or `pdb` and reading what it reports —
  that is behaviour, not a lookup.
- `git` and `gh` for history and issues.

### When the cited source looks wrong

That is a finding, and it goes back to him. Name the exact line and what the
running program did instead. **Never route around it.** Work done against a
private belief about the tree is work nobody can check, and it is unauthorized
however correct it turns out to be.

## Falsification

This skill is wrong if a unit needs a rule that exists in no skill, no issue and
no manual page. Then the rule is missing from canon, and writing it into a skill
is the work — not writing it into a brief.
