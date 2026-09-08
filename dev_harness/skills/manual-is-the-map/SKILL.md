---
name: manual-is-the-map
description: The product manual is the orientation point. Load when closing an issue, shipping a feature, or reporting work complete — the manual entry changes in the same unit, or the work is not done.
---

# The manual is the map

The product manual is where the operator orients. He does not read code. When
the software changes and the manual does not, the map stops matching the ground
— and he is navigating by the map.

**A unit that changes what the software does, changes the manual in the same
unit.** Not afterwards, not in a follow-up, not on a list.

## What triggers an update

```
an issue closes                  the entry citing it loses the citation
a feature ships                  "In development." becomes real code
a proposal is built              "Proposed, not present" becomes the shipped block
a setting gains a reader         "nothing reads it" becomes what reads it
a control is removed             the entry says so, or goes
a number changes meaning         the entry carries the new meaning
a screen becomes reachable       it stops being listed as not built
```

## The entry standard does not change

His line first, byte-identical. Then what it does today. Then exactly one of: a
code block of real code, a block marked "Proposed, not present", or the sentence
"In development." At most two inline code spans in a paragraph or bullet.

**No sentence of the operator's is ever deleted or reworded.** Prove it with the
token multiset and both its controls before you land.

## The check

```
python C:/Users/brown/AppData/Local/Temp/claude/manual_drift.py <tree>
```

It reports three kinds of drift: an issue the manual cites as open that GitHub
has closed, an entry saying "In development." whose named symbol now exists in
the tree, and a proposal marked "Proposed, not present" that is present. Exit 1
while any remains.

Run it when you close an issue and when you land a feature. A green from it is
not proof the manual is right — it proves only that these three drifts are
absent. Reading the entry is still the job.

## Why this is a rule and not a habit

Measured this session: 95 settings carried a description and no code block, six
code citations named the wrong module, three passages proposed removing
constants a repair had already removed, and a screen that no longer exists had a
full walkthrough. Every one of those was written true and went stale because the
code moved and the page did not.

The operator's words, 2026-09-05: *"Need a SKILL or rule to update the manual
with issues being cleared or features being built out. It will serve as our
guide and orientation point going forward."*

## The one thing that makes this cheap

Update the entry while the change is in front of you. The unit that shipped the
feature knows the config key, the range, the default and every reader — it
measured them to build the thing. A later unit has to rediscover all of it.

## The PDF is part of the delivery

Operator, 2026-09-05: *"If the Manual received updates, you have to be sure to
reproduce the PDF before this specific item is considered sync'd. This
should also be a per unit action."*

He reads `docs/Acervator-Product-Manual.pdf`. The markdown under `docs/manual/`
is the source; the PDF is what reaches him. A source edit that does not reach
the render has not reached him at all.

**A unit that edits any page under `docs/manual/` rebuilds and commits the PDF
in the same unit.** Not at the end of a session, not when somebody notices.

```
python -m tools.build_product_manual      five verifiers green, 77 figures
read the COMMITTED copy back              page count and image count
python .../pdf_fresh.py                   exits 1 while the PDF is behind
```

Reading the committed copy back matters. A build that succeeded and a commit
that carries the built bytes are two different claims, and a 200-page binary
fails silently.

The freshness check is part of `sync_check.py` as well, so a tree can be on the
right commit with nothing unpushed and still be out of step. Both must be clean
before an item counts as delivered.
