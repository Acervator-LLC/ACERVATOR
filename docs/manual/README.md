# Acervator Product Manual

Reference. The product manual, extracted from its PDF into markdown. The
transcription is verbatim in every part file: no wording was changed, shortened
or removed, and only whitespace was normalised.

Six part files hold that transcription alone.
[07-indicators.md](07-indicators.md) and [08-tabs.md](08-tabs.md) transcribe
the PDF and add sections of their own.
Five files transcribe nothing, because the PDF carries no body text for the
parts they belong to:
[09-updates-and-versioning.md](09-updates-and-versioning.md),
[10-live-trade-history.md](10-live-trade-history.md) and
[13-live-evidence.md](13-live-evidence.md), written from the source
and from measurements over the operator's own venue export; and
[11-hop-protocol-and-rules-registry.md](11-hop-protocol-and-rules-registry.md)
and [12-adr-index-and-glossary.md](12-adr-index-and-glossary.md), written from
the source alone; and
[14-development-chronicle.md](14-development-chronicle.md), written from the
git history, the audits in [docs/audits](../audits), the operator's own
pre-git record, and a memory record kept across sessions. The `NN-` prefix of a file is its own name and carries no
meaning; the Part column below is what places a file in the manual.

## Three sources, and how to tell them apart

Every passage in this manual comes from one of three places. The Source column
in the table below says which, per file, and each migrated section repeats its
source in its own first paragraph, so a reader who opens a file in the middle
still knows what they are reading.

| Bucket | What it is |
| ------ | ---------- |
| ORIGINAL | The operator's own product manual, 44 pages and 38 figures. Transcribed verbatim into the part files. |
| UPDATES | Written this session from the source in this repository and from measurements over the operator's own venue export. |
| LEGACY | The superseded fourteen-part manual, 479 pages and 55 images. Carried across section by section, with every claim re-checked and every wrong value corrected in place. |

A file marked with more than one bucket holds a labelled section per bucket and
never blends them inside a section. Nothing in the ORIGINAL bucket was reworded
to accommodate a migration.

The LEGACY bucket is superseded, and "the original" always means the operator's
own 44-page manual. Where a legacy passage and the code disagree, the code is
the present state and the correction travels with the passage.

Every one of the 479 legacy pages is accounted for. The disposition of each
part, migrated or not, with the reason and the proof, is the migration ledger in
[docs/audits/manual-original-parts-audit.md](../audits/manual-original-parts-audit.md).
All 55 legacy images are inventoried, one row each, in
[FIGURES.md](FIGURES.md).

## Contents

| File | Part | Source | Manual pages | Covers |
| ---- | ---- | ------ | ------------ | ------ |
| [01-title.md](01-title.md) | 1 | ORIGINAL | 1 | Title and the epigraph |
| [02-legal.md](02-legal.md) | 1 | ORIGINAL | 2 to 4 | Copyright, contact, legal disclaimers, algorithmic-trading risk |
| [03-executive-summary.md](03-executive-summary.md) | 1 | ORIGINAL | 5 to 7 | Executive summary, origin of the method, support addresses |
| [04-manual-parts.md](04-manual-parts.md) | 1 | ORIGINAL | 8 to 9 | The manual's own part list and tab list |
| [05-novel-concepts.md](05-novel-concepts.md) | 2 | ORIGINAL | 10 to 14 | Novel concepts and patent candidate catalogue, entries 1 to 17 |
| [15-patent-portfolio.md](15-patent-portfolio.md) | 2 | LEGACY | — | The seventeen anchored inventions, the two with a corrected constant, and the seven with no code |
| [06-trading-tab.md](06-trading-tab.md) | 3 | ORIGINAL + LEGACY | 14 to 27 | System architecture, then the Trading Tab walkthrough |
| [07-indicators.md](07-indicators.md) | 3 | ORIGINAL + UPDATES + LEGACY | 27 to 29 | Indicator Voting Panel and the twelve indicators |
| [08-tabs.md](08-tabs.md) | 3 | ORIGINAL + UPDATES + LEGACY | 29 to 44 | Main Window, Simulator, Paper Trader, Proof of Accumulation, Market Inspector, Bot Swarm, Asset Charts, History, Console, System Status, and the eleven Settings pages |
| [13-live-evidence.md](13-live-evidence.md) | 4 | UPDATES | — | The readers of the year-to-date venue record, the connectors, and what the exchange tests reach |
| [11-hop-protocol-and-rules-registry.md](11-hop-protocol-and-rules-registry.md) | 5 | UPDATES + LEGACY | — | The handoff file and its drift check, the rules registry, and the two versions of the development protocol |
| [12-adr-index-and-glossary.md](12-adr-index-and-glossary.md) | 6 | UPDATES + LEGACY | — | Where a decision is recorded, and the glossary anchored to the modules behind it |
| [09-updates-and-versioning.md](09-updates-and-versioning.md) | 7 | UPDATES + LEGACY | — | Version derivation, the six readers, the baked bundle value, the release gate |
| [14-development-chronicle.md](14-development-chronicle.md) | 8 | UPDATES + LEGACY | — | The three records of the work, the corrections that became the instruments, the audits they produced, and what they cost and missed |
| [10-live-trade-history.md](10-live-trade-history.md) | 9 | UPDATES | — | The live fill record, VWAP charts, trade grading, gate coverage |
| [FIGURES.md](FIGURES.md) | — | ORIGINAL + LEGACY | 15 to 44 | The figure inventory |

Pages 36 to 44 carry a figure and no text, so the PDF gives a part file
nothing to transcribe for them. [08-tabs.md](08-tabs.md) describes each of
those nine figures under a heading of its own, and
[FIGURES.md](FIGURES.md) records where every figure is described.

[07-indicators.md](07-indicators.md) adds the twelve published formulae, the
departures the code takes from them, and the gate logic chain.
[08-tabs.md](08-tabs.md) adds a description of the running code under each
heading. Both keep every transcribed sentence unaltered.
[07-indicators.md](07-indicators.md) holds them in the PDF's order.
[08-tabs.md](08-tabs.md) orders its sections by the tab list in
[04-manual-parts.md](04-manual-parts.md): Main Window opens the part, and the
eleven Settings pages sit under one Settings heading. The subsystem files below
hold the longer form of the tab descriptions and none of them transcribe the
PDF.

## Part 3 subsystem detail

Written from the source, not from the PDF. Each file names the module behind a
screen, the symbols inside it, the bridge method that serves its renderer, and
the screen's state.

| File | Covers |
| ---- | ------ |
| [08-tabs/README.md](08-tabs/README.md) | Index of the files below, the live tab set, how a screen reaches its renderer |
| [08-tabs/portfolio-panels.md](08-tabs/portfolio-panels.md) | The header strip: spendable columns, counter cards, privacy dots |
| [08-tabs/simulator.md](08-tabs/simulator.md) | Fleet Replay, Stone Tablets, the gate-latch criterion, Nuclear Mode |
| [08-tabs/paper-trader.md](08-tabs/paper-trader.md) | What the step is, and the proof no module implements it |
| [08-tabs/proof-of-accumulation.md](08-tabs/proof-of-accumulation.md) | Identity, Merkle log, competitions, ACRV, the local chain |
| [08-tabs/market-inspector.md](08-tabs/market-inspector.md) | Signal table, opposing pairs, topology proposals, adopt |
| [08-tabs/bot-swarm.md](08-tabs/bot-swarm.md) | Nodes, Smart Wires, wire credits, the fold-tranche book |
| [08-tabs/asset-charts.md](08-tabs/asset-charts.md) | One candlestick panel per traded symbol |
| [08-tabs/history.md](08-tabs/history.md) | Venue trade history, grading, gate analysis |
| [08-tabs/console.md](08-tabs/console.md) | Python log tail and the emitter signal stream |
| [08-tabs/system-status.md](08-tabs/system-status.md) | Emitter Network and Watchdog, and the proof no tab exists |
| [08-tabs/settings.md](08-tabs/settings.md) | The User page, the Exchanges page, and what each of the eleven pages persists |
| [08-tabs/promotion-pipeline.md](08-tabs/promotion-pipeline.md) | How a strategy earns its way to real money |
The Part column is the table's second job: it tells
`tools/build_product_manual.py` which manual part a file belongs to. A file
carrying `—` is not manual text and is not rendered. The order of the rows is
the order the PDF prints them, and the first row is the title page. A row naming
a file that is not on disk, and a `NN-*.md` file this table does not list, both
stop the build. A `—` in the Manual pages column marks a file the PDF is not
the source of. Every part now has a file, and a new row here folds a
further file into its part.
contents, and a new row here folds a file into its part.

## Figures

The manual carries 38 embedded images. They are captured output, so they are not
tracked: `tools/extract_product_manual.py` writes them to
`artifacts/manual-figures/` under the repository root, a path `.gitignore`
excludes. [FIGURES.md](FIGURES.md) lists every one with its page, index, file
name, byte size, pixel size, and whether its page also carries text.

That count of 38 covers the images the source PDF embeds, and a deep walk of
the PDF's resource tree — every page's `/XObject`, recursing into every `/Form`
— returns the same 38, across 38 distinct objects, with none nested inside a
form and no inline image anywhere. Part 9 adds a second set:
[10-live-trade-history.md](10-live-trade-history.md) embeds 39 VWAP charts
built from the operator's venue export. Those live in
`artifacts/vwap-charts/`, a directory of their own under the same `.gitignore`
rule, and [FIGURES.md](FIGURES.md) inventories them beside the first set.
Counting both sets, the built PDF embeds 77 images.

## Extraction record

The source PDF and the operator's exchange CSV exports live outside this
repository and are not committed. `tools/extract_product_manual.py` takes the
PDF path as its `--pdf` parameter and writes both this directory and the figures
directory. It exits non-zero when the part files no longer hold every PDF token
in order.

`write_parts` compares each part file against the blocks the PDF produces. A
file holding a block the PDF does not produce stops the run before anything is
written; the refusal names the file, counts the blocks, and quotes the first
one. `--re-extract` rewrites the transcription and keeps those blocks where they
sit. That is the flag for a corrected PDF.

`PART_FILES` in that tool names the eight files the PDF is the source of. The
files under [08-tabs/](08-tabs/README.md),
[09-updates-and-versioning.md](09-updates-and-versioning.md),
[10-live-trade-history.md](10-live-trade-history.md),
[11-hop-protocol-and-rules-registry.md](11-hop-protocol-and-rules-registry.md),
[12-adr-index-and-glossary.md](12-adr-index-and-glossary.md) and
[13-live-evidence.md](13-live-evidence.md) and
[14-development-chronicle.md](14-development-chronicle.md) are not
among them and are never written.

- 44 pages, 9,759 whitespace-separated tokens, 38 embedded images.
- Page 24 and pages 36 to 44 extract zero visible characters.
- Every character decoded. Ten non-ASCII code points appear in the text: curly
  single and double quotes, bullet, em dash, en dash, ellipsis, copyright sign,
  and middle dot.

### Whitespace normalisation

The PDF holds justified text, so a line arrives with runs of spaces inside it and
a paragraph arrives broken across visual lines. Two normalisations were applied,
both whitespace only:

1. Inside a line, every run of spaces and tabs collapses to one space, and the
   lines of one paragraph join with one space between them.
2. Two paragraphs that straddle a page break join with one space. Both are in
   [04-manual-parts.md](04-manual-parts.md) and [06-trading-tab.md](06-trading-tab.md):
   the Asset Charts Tab entry that starts on page 8 and finishes on page 9, and
   the Scrumming Bot paragraph that starts on page 15 and finishes on page 16.

Compared token by token against the PDF, the transcription holds 9,759 tokens in
the same order, with no loss. The added sections in
[07-indicators.md](07-indicators.md) and [08-tabs.md](08-tabs.md) sit outside
that count. The five files the PDF is not the source of sit outside it in full.

### Headings

Heading level is markup, not text. Every heading takes its words from the manual,
with one exception: the H1 of [08-tabs.md](08-tabs.md) reads "Subsystem Tabs",
which is the manual's own phrase for those screens on page 14. Where the PDF runs
a bold heading into the paragraph beneath it, as it does for the two investment
notices in [02-legal.md](02-legal.md), the run stays one paragraph.

## Building the PDF

`tools/build_product_manual.py` renders this directory back into a PDF through
reportlab, taking its colours, type sizes and page grid from
`src/design_system.py`.

```
python -m tools.build_product_manual
```

The PDF is generated output, so it is not tracked: it is written to
`artifacts/manual/Acervator-Product-Manual.pdf`, beside the figures, under the
same `.gitignore` rule. `--docs-dir`, `--figures-dir` and `--output` move all
three.

The tool renumbers the parts of [04-manual-parts.md](04-manual-parts.md) from
one and sets its count word to match. It builds a table of contents down to the
second heading level, so every tab is a row with its own page number, and it
re-renders until each row names the page its heading reached. It exits non-zero
when a row names the wrong page, when a listed section is absent from the PDF,
when the part numbers repeat or skip, or when the count word disagrees with the
number of parts. A figure a part file references and `artifacts/manual-figures/`
does not hold stops the build by name.

## Other document producers in this repository

`generate_essay.py` is named by the handoff documents, the archived development
chronicle and the missing-reference guard, and it is not in the tree.
`git log --all --diff-filter=ADR` returns no commit that ever added it; the same
query for `generate_essay_ja.py` returns commits, so the query does find a file
that existed.

| Producer | Output |
| -------- | ------ |
| `generate_essay_ja.py` | The Japanese product manual, as a PDF, through reportlab |
| `generate_essay_localized.py` | The Acervator technical essay in English, Japanese, Spanish, French and German |
| `save_pdf_report` in `src/core/version_sweep.py` | A version-sweep report, written to the reports directory outside the repository |
| `generate_splash.py` under `deploy/kiosk/splash/` | The AcervatorOS boot splash image |
