# `docs/engineering-notes/2026-09-10_poa_blockchain_game_state_of_the_field.md`

Reference. This unit changed no product file, no contract and no test. It ran
web searches and web fetches, and wrote one engineering note plus one captured
raw-source file.

No pytest ran. No pytest file names a symbol this unit changed, because this unit
changed no symbol. Both CI lanes would skip with no Python changed and report
`PASSED — 0 lane(s) ran`, which records that no lane ran rather than a pass.

Raw captured source output: `artifacts/147-research-blockchain/raw_sources.txt`.
The repository gitignores that directory, because it holds captured output, and
`docs/` may not hold captured output. The findings live in the engineering note
named above.

## Where each file went, and why

```
docs/engineering-notes/             the note. CLAUDE.md gives docs/ the role of
2026-09-10_poa_blockchain_game_     human-written documentation only, and this
state_of_the_field.md               note is a human-written research finding
                                    with no captured output in it

artifacts/147-research-blockchain/  the raw fetched source text. CLAUDE.md
raw_sources.txt                     forbids captured output in docs/, src/ and
                                    tests/, and .gitignore line 112 covers
                                    artifacts/

tests/debug_reports/                this file, matching every sibling in that
2026-09-10_147_blockchain_          directory
game_research.md
```

The name check ran before the write: `ls tests/debug_reports/` returned 21 files
dated 2026-09-10 and none of them carried this name.

## The shared reproduction

Every figure in the note came from a `WebSearch` or a `WebFetch` on 2026-09-10.
The raw-source file lists each URL, what the page said verbatim, and the date the
page itself gives. Re-running the same fetches reproduces the readings, with the
caveat that three of the sources publish live numbers and will move:

```
l2beat.com/scaling/activity        live daily figures, re-read gives new numbers
l2beat.com/scaling/projects/redstone   live, and the project is archived
chainspect.app/dashboard           live, and the page states no snapshot date
```

The arithmetic in the note came from one run of divisions over the figures above
and the three figures this repository already measured and recorded in issue #147:
1,015 bytes an action, 1 MB per layer per world turn, 1,033 actions, 20 layers.
The full output sits in the raw-source file under `ARITHMETIC — method and output`.

## The instrument, proved before the verdict

```
docs_archetype  harness_fixtures/docs_archetype/known_good.md
                exit 0  passed=true
docs_archetype  harness_fixtures/docs_archetype/known_bad.md
                exit 1  passed=false
```

Both exit codes came back on the same line as the command that produced them, so
no pipe reported another command's status. `tool_availability` appeared in the
JSON for both runs.

## The verdict on the note

```
docs_archetype  docs/engineering-notes/2026-09-10_poa_blockchain_game_state_of_the_field.md
                exit 0   passed=true   0 findings
```

Read out of the JSON `passed` field, not off the exit code.

The run before it reported `passed=false` with 46 findings, all from vale:

```
high    1    a sentence opening vale's ThereIs rule rejects
medium  39   passive voice, and wordy pronoun-plus-verb forms
medium   6   weasel words
```

A rewrite of the prose cleared all 46. No rule changed.

## The hallucination rule

The note cites two paths inside this repository and both resolve in the worktree:

```
docs/engineering-notes/2026-09-10_poa_world_state_budget.md
artifacts/147-research-blockchain/raw_sources.txt
```

Every other citation in the note points at a public web page, with its own date,
and the raw-source file carries the verbatim wording each one supplied.

## What the operator sees differently

Nothing on screen. This unit answers a research question and writes it down.
