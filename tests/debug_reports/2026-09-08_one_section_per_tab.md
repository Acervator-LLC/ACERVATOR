# One section per tab

Reference. The manual's contents listed ten tabs twice. This report records the
measurement, the move that closed eight of them, and the two rules that refuse
the shape from coming back.

## The error

The contents page of the built manual named ten tabs in two places each. The
rows below were read off the shipped PDF through the builder's own reader.

```
115  Simulator Tab (Hot Mess; Complete Rebuild In Progress)      204  Simulator Tab
121  Paper Trader Tab (To Be Built)                              227  Paper Trader Tab
123  Proof of Accumulation (Anonymized Trading Tournaments...)   234  Proof of Accumulation
124  Market Inspector Tab                                        240  Market Inspector Tab
127  Bot Swarm Tab                                               244  Bot Swarm Tab
133  Asset Charts                                                250  Asset Charts
135  History Tab                                                 254  History Tab
140  Console                                                     259  Console
144  System Status Tab (To Be Built)                             263  System Status Tab
146  Settings                                                    266  Settings
```

## Reproduction

```
python -m tools.build_product_manual
```

## The cause

Each screen is described in two files. `docs/manual/08-tabs.md` held one section
per screen, and `docs/manual/08-tabs/` holds one page per screen. Only one of
the two reached the PDF until the producer began carrying every listed page.
Both then appeared, so every screen with a page of its own gained a second
contents section.

## The correction

Eight sections moved out of `08-tabs.md` onto the per-tab page that is now the
tab's one home. Each moved section became a dated update subsection under that
page's own heading.

```
## 2026-09-08 08:17 - #117 - what the closed issues landed
   date       time    issues addressed    what the update did
```

The date leads so the subsections sort, and they run forward down the page. A
move with no issue behind it writes `no issue recorded` in that field. Every
date and time came from the commit that last changed the moved lines, read with
`git log -L`, and none was invented.

`08-tabs.md` keeps Main Window, the two screens another unit holds, the
conversion table, and one pointer line per moved screen. Its opening sentence
was rewritten to describe that shape.

Two headings were stale and now state what is true: the Simulator carries three
modes and the Paper Trader is built.

## What was not moved

`docs/manual/08-tabs/market-inspector.md` and
`docs/manual/08-tabs/asset-charts.md` are held by two other units, so the
Market Inspector and Asset Charts sections stayed in `08-tabs.md`. Both are
still named by two contents sections and `DOC011` reports both.

## Nothing was deleted

Every whitespace-separated token under `docs/manual` was counted before and
after. The tokens whose count fell each belong to one of six named corrections.

```
before  98,645 tokens
after   98,933 tokens
fell    58 tokens
```

```
the Simulator's stale label            (Hot Mess; Complete Rebuild In Progress)
the Paper Trader's stale label         (To Be Built)
eight moved section headings           the second heading the operator named
the part introduction                  rewritten for the new shape
one of two identical pointer lines     both named docs/manual/08-tabs/settings.md
two headings the archetype refused     a duplicate heading and a false citation
```

The control ran first. One sentence was cut from a copy of the tree and the same
count reported it, so the proof is watched to fail before it is read as passing.

```
control    one sentence deleted    exit 1, 37 tokens fell
proof      the branch as it lands  every fall named above
```

## The rules

`DOC011` refuses a contents page naming one tab in two sections. It reads the
rows through `read_toc_rows`, the reader `DOC006` already runs, and groups them
with `tab_key` against the per-tab pages under `docs/manual/08-tabs/`. A
subheading shared across those pages is not a tab, so `Bridge` on eight pages
and `What builds it` on seven raise nothing.

`DOC012` refuses a dated update that runs backwards under a tab. It reads the
dates through `story.entries`, the reader `DOC007` runs, so one date parser
serves the chronicle and the tab pages.

```python
def repeated_tab_rows(pdf_path: Path, docs_dir: Path) -> tuple[int, list[str]]: ...
def backward_update_rows(path: Path) -> list[str]: ...
```

## Verification

Both fixture pairs sit beside the pairs already there. No existing fixture was
edited.

```
harness_fixtures/docs_archetype/tab_sections_good.pdf   exit 0
harness_fixtures/docs_archetype/tab_sections_bad.pdf    exit 1
harness_fixtures/docs_archetype/tab_updates_good.md     exit 0
harness_fixtures/docs_archetype/tab_updates_bad.md      exit 1
```

The bad PDF returns one `DOC011` finding and the bad page two `DOC012`
findings. The four fixtures that were already there still separate.

```
known_good.md   exit 0      known_bad.md   exit 1
known_good.pdf  exit 0      known_bad.pdf  exit 1
```

`DOC011` was then run against the manual before and after the move. The count it
reports is the count read by hand off the contents page.

```
before the move   10 tabs named twice
after the move     2 tabs named twice, both held by another unit
```

## The rerun

```
part numbers: ok - parts 1 to 9, contiguous
count word: ok - count word 'nine' matches 9 parts
sections present: ok - 27 listed sections present
contents pages: ok - 235 contents rows land on the page they name
no raw markup: ok - 356 pages carry no raw markup
```

The contents of the written PDF were read back with `pypdf`. The reader was
calibrated on a phrase the contents carries and one it does not before the
counts below were read.

```
present  'Bot Swarm Tab'      True
absent   'Fleet Cannon Tab'   False
```

```
1  Simulator Tab          1  History Tab
1  Paper Trader Tab       1  Console
1  Proof of Accumulation  1  System Status Tab
1  Bot Swarm Tab          1  Settings
2  Market Inspector Tab   2  Asset Charts
```

## The runtime tree

The settings file was hashed before and after every run in this unit.

```
before  f366f42f0e49b4b3468f301b4f2f701669cc13005cfe1ebac7a56988ec376423
after   f366f42f0e49b4b3468f301b4f2f701669cc13005cfe1ebac7a56988ec376423
```
