# Truth Archetype — Reference

Every claim below resolves against the tree. Ground truth: `TruthArchetype`
produces ZERO critical or high findings on this file, and the CLI exits 0. A
high finding here is a false positive and must be investigated.

## What each rule resolves

| rule | subject | ground truth |
|---|---|---|
| T001 | a cited path | the tree on disk |
| T002 | a cited symbol | every `def` and `class` in the tree |
| T003 | a cited issue number | the repository listing |
| T004 | a stated count | the count recomputed now |
| T005 | a runtime claim | the observation the sentence names |
| T006 | a completion claim | the evidence the sentence names |

## Where the code sits

`TruthArchetype` sits in `dev_harness/harness/truth_archetype.py` and hands back
the shared `ArchetypeReport` from `dev_harness/harness/report.py`.

`build_tree_index` walks the tree once and keeps every definition name.
`cli_exit` turns that report into the process exit code.

## Undecided is a spoken answer

A claim beyond the reach of this instrument becomes a T000 record at severity
info, carrying the word UNDECIDED and the reason the resolver stopped. Silence
never stands for a resolved claim.

## The fixture pair

The other half of the pair is `harness_fixtures/truth_archetype/known_bad.md`,
which carries one planted defect per rule.

## The item the scope rule grounds against

T007 needs one item. This file cites issue #128 once, and cites no other
number, so the scope rule reads that item and decides every subject in this
file against it. A file citing two numbers leaves it nothing to choose, and a
file citing none leaves the report short of a scope verdict.
