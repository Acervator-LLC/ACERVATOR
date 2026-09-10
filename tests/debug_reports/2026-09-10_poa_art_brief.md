# The art brief — unit 20 of issue #147

Reference. This unit wrote two documents and changed no code. No pytest ran, because
the unit touched no Python, no JavaScript and no contract. The instrument here is the
Docs Archetype and nothing else.

Subjects: `docs/engineering-notes/2026-09-10_poa_art_brief.md`,
`docs/manual/08-tabs/proof-of-accumulation.md`,
`tests/debug_reports/2026-09-10_poa_art_brief.md`.

This unit drew nothing and commissioned nobody.

## The roster, counted

```
21 designs   the drawing jobs, across five tiers
23 names     21 attested in a pre-modern text, 2 the summit's own invention
 3 ranks     the decans, their daimones, their leitourgoi — tier 3, unspecified
```

Every one of the 21 attested names carries the text beside it in the brief. A name with
no text did not go in.

## The instrument reported on a planted fault, before any verdict counted

The calibration bodies are the pair in `harness_fixtures/docs_archetype`. Both ran on
this branch, and the exit code came off the same line as the command rather than
through a pipe.

```
python -m dev_harness.harness.docs_archetype harness_fixtures/docs_archetype/known_good.md
  exit 0

python -m dev_harness.harness.docs_archetype harness_fixtures/docs_archetype/known_bad.md
  exit 1   [archetype] not green: 1 critical/high finding(s)
```

The instrument discriminates, so a verdict from it means something.

## Every tool reported, and none was missing

A tool marked missing did not run, and silence from it never counts as a pass.
All seven reported on every run below.

```
proselint     ok
vale          ok
structure     ok
story         ok
updates       ok
scaffolding   ok
hallucination ok
```

## The brief — red before green, both read

The first run of the brief failed. The faults were the Docs Archetype's own prose
rules, and every fix was a rewrite of this unit's text rather than a change to a rule.

```
run 1   passed=False   73 findings   high=6  low=1  medium=66
run 2   passed=True    65 findings   high=0  low=1  medium=64
run 3   passed=True     5 findings   high=0  low=0  medium=5
run 4   passed=True     0 findings
```

Six high findings came from six sentence openings, and sixty-four more from passive
voice and wordiness. Two rewrite passes cleared every one.

```
write-good.So        4 sentences   an opening conjunction
write-good.ThereIs   2 sentences   an existential opening
write-good.Passive  40 sentences
write-good.TooWordy 22 phrases
write-good.Weasel    1 phrase
typography           1 quotation mark pair
```

```
python -m dev_harness.harness.docs_archetype docs/engineering-notes/2026-09-10_poa_art_brief.md
  exit 0   passed=True   0 findings
```

## The manual page — the baseline, and the page after the block landed

The page already carried findings before this unit touched it, so the verdict to read
is `passed`, never a count.

```
before the block     passed=True   183 findings   low=4  medium=179
after the block      passed=True   187 findings   low=4  medium=183
after the merge      passed=True   188 findings   low=4  medium=184
```

Four added findings belong to this unit's block. One is the repeated-zero reading of
the date stamp, which the page already carried five times, once per dated block. The
stamp format is the page's own convention and this block follows it. The merge brought
another unit's dated block onto the page, which accounts for the last finding.

```
python -m dev_harness.harness.docs_archetype docs/manual/08-tabs/proof-of-accumulation.md
  exit 0   passed=True
```

## The dated block runs forward

DOC012 compares dated headings inside one section and fails a stamp that precedes the
one above it. The new block carries the true clock reading at the time of writing, and
it follows the last block on the page.

```
the last block before this unit   2026-09-10 00:38
another unit's block, merged      2026-09-10 00:59
this unit's block                 2026-09-10 01:12
dated blocks on the page          18
DOC012 findings                   none
```

The merge hit a conflict on this page, because another unit appended its own dated
block to the same line. The resolution keeps both blocks, the earlier stamp first.
Against `origin/current` the page shows 143 insertions and zero deletions, so nothing
the other unit wrote went missing.

## The manual edit deletes and rewords nothing

The manual edit appends and changes nothing above it.

```
git diff --cached --numstat origin/current -- docs/manual/08-tabs/proof-of-accumulation.md
  143 insertions, 0 deletions
```

Zero deletions, so no sentence on that page moved, changed or disappeared. The only
minus line in the whole diff is the `--- a/` file header.

## Where each document went, and why

```
docs/engineering-notes/2026-09-10_poa_art_brief.md
    An art brief is human-written documentation, which is the only thing the
    repository's first hard rule allows under docs/. Every other PoA design note
    of this item sits in engineering-notes, including the sourcing research this
    brief inherits, and the repository's documentation rule groups documents by
    their area of reference.

docs/manual/08-tabs/proof-of-accumulation.md
    A pointer, not the brief. The manual describes the product; the brief tells
    an outside artist what to draw and what it costs. The page already points at
    an audit report and a debug report the same way.
```

## What the brief could not supply

Five gaps. In each one the excluded revival layer was the only available source, and
the brief names the gap instead of reaching for it.

```
a name for each of the ten husks     only the modern revival supplies one
a look for each husk                 no pre-modern source draws one
the thirty-six decan images          behind editions not in hand
a colour for Salt, Sulphur, Mercury  no design token carries one
the panel's absolute height          four heights on the path are content-sized
```

The last one is the figure this unit stopped on. The chrome strip, the tab strip, the
heading line and the state line all size to their content, so no declaration yields
the panel's absolute height. Reading it needs the program running, and this unit
authors nothing that observes. Every dimension in the brief carries a formula plus a
worked figure at a named assumption.

## The layout numbers, and the four that disagreed

Every number came out of
`src/gui/main_tabs/proof_of_accumulation_tab_surface.py`,
`src/gui/web/proof_of_accumulation_tab.js` and
`src/gui/web/proof_of_accumulation_tab.css`.

```
confirmed   120 participants, 40 to a page, eight groups of five, three pages
disagreed   the name truncates at eight characters, not twelve
disagreed   no mark slot exists; the row carries five text columns
disagreed   no health bar exists; health is a text span
disagreed   no role colour exists; no token names a Paracelsian principle
```

The twelve-character short form is real and belongs to two other fields, in
`src/competition/bot_identity.py` and `src/competition/trophy_generator.py`.

## Name collisions found, and reported rather than renamed

```
tier       five trophy rarities in src/competition/season_schedule.py, five loot
           tiers in the issue, and a rank running 1 to 5 in
           src/competition/poa_modes.py
Mercury     a planet, a Paracelsian principle and a metal, all in
           src/competition/rpg_classes.py
silver      the Silver Mirror's metal, and the Albedo stage's colour in
           src/competition/trophy_generator.py
```

## What the operator sees differently because of this unit

Nothing on screen. The tab still draws three empty zones, each carrying a sentence
that says it holds no pixel art. The change is that a document now specifies the
art, with a frame count beside every item, where a conversation specified it before.
