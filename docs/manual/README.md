# Acervator Product Manual

Reference. The product manual, extracted from its PDF into markdown. The
transcription is verbatim in every part file: no wording was changed, shortened
or removed, and only whitespace was normalised.

Six part files hold that transcription alone.
[07-indicators.md](07-indicators.md) and [08-tabs.md](08-tabs.md) transcribe
the PDF and add sections of their own.
The PDF carries no body text for the parts the files below belong to, so they
transcribe nothing:
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

## Contents

| File | Part | Manual pages | Covers |
| ---- | ---- | ------------ | ------ |
| [01-title.md](01-title.md) | 1 | 1 | Title and the epigraph |
| [02-legal.md](02-legal.md) | 1 | 2 to 4 | Copyright, contact, legal disclaimers, algorithmic-trading risk |
| [03-executive-summary.md](03-executive-summary.md) | 1 | 5 to 7 | Executive summary, origin of the method, support addresses |
| [04-manual-parts.md](04-manual-parts.md) | 1 | 8 to 9 | The manual's own part list and tab list |
| [05-novel-concepts.md](05-novel-concepts.md) | 2 | 10 to 14 | Novel concepts and patent candidate catalogue, entries 1 to 17 |
| [06-trading-tab.md](06-trading-tab.md) | 3 | 14 to 27 | System architecture, then the Trading Tab walkthrough |
| [07-indicators.md](07-indicators.md) | 3 | 27 to 29 | Indicator Voting Panel and the twelve indicators |
| [08-tabs.md](08-tabs.md) | 3 | 29 to 44 | Main Window, Simulator, Paper Trader, Proof of Accumulation, Market Inspector, Bot Swarm, Asset Charts, History, Console, System Status, and the eleven Settings pages |
| [13-live-evidence.md](13-live-evidence.md) | 4 | — | The readers of the year-to-date venue record, the connectors, and what the exchange tests reach |
| [11-hop-protocol-and-rules-registry.md](11-hop-protocol-and-rules-registry.md) | 5 | — | The handoff file and its drift check, the rules registry, and the two versions of the development protocol |
| [12-adr-index-and-glossary.md](12-adr-index-and-glossary.md) | 6 | — | Where a decision is recorded, and the glossary anchored to the modules behind it |
| [09-updates-and-versioning.md](09-updates-and-versioning.md) | 7 | — | Version derivation, the six readers, the baked bundle value, the release gate |
| [14-development-chronicle.md](14-development-chronicle.md) | 8 | — | The three records of the work, the corrections that became the instruments, the audits they produced, and what they cost and missed |
| [10-live-trade-history.md](10-live-trade-history.md) | 9 | — | The live fill record, VWAP charts, trade grading, gate coverage |
| [FIGURES.md](FIGURES.md) | — | 15 to 44 | The figure inventory |

The Part column is the table's second job: it tells the build tool which manual
part a file belongs to. A row whose Part cell is an em dash is not manual text
and is not rendered. An em dash in the Manual pages column means a different
thing, that the PDF is not that file's source. The rows run in the order the PDF
prints them, the first row is the title page, and a new row here folds a further
file into its part.

`tools/build_product_manual.py` — `read_manifest` refuses a table and a
directory that disagree

```python
if not path.is_file():
    message = f"{readme.name} lists {name}, absent from {docs_dir}"
    raise FileNotFoundError(message)
...
if unlisted:
    message = f"{readme.name} omits {', '.join(unlisted)}"
    raise ValueError(message)
```

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
| [08-tabs/paper-trader.md](08-tabs/paper-trader.md) | What the step is, and the two live surfaces that still offer it |
| [08-tabs/proof-of-accumulation.md](08-tabs/proof-of-accumulation.md) | Identity, Merkle log, competitions, ACRV, the local chain |
| [08-tabs/market-inspector.md](08-tabs/market-inspector.md) | Signal table, opposing pairs, topology proposals, adopt |
| [08-tabs/bot-swarm.md](08-tabs/bot-swarm.md) | Nodes, Smart Wires, wire credits, the fold-tranche book |
| [08-tabs/asset-charts.md](08-tabs/asset-charts.md) | One candlestick panel per traded symbol |
| [08-tabs/history.md](08-tabs/history.md) | Venue trade history, grading, gate analysis |
| [08-tabs/console.md](08-tabs/console.md) | Python log tail and the emitter signal stream |
| [08-tabs/system-status.md](08-tabs/system-status.md) | Emitter Network and Watchdog, the two halves that run today |
| [08-tabs/settings.md](08-tabs/settings.md) | The User page, the Exchanges page, and what each of the eleven pages persists |
| [08-tabs/promotion-pipeline.md](08-tabs/promotion-pipeline.md) | How a strategy earns its way to real money |

## Figures

The manual carries 38 embedded images. They are captured output, so they are not
tracked. The extractor writes them to a directory under the repository root that
the ignore file excludes. [FIGURES.md](FIGURES.md) lists every one with its page,
index, file name, byte size, pixel size, and whether its page also carries text.

Where the extractor puts them:

```python
REPO_ROOT = Path(__file__).resolve().parents[1]     # tools/extract_product_manual.py
DEFAULT_FIGURES_DIR = REPO_ROOT / "artifacts" / "manual-figures"
```

That count of 38 covers the images the source PDF embeds. A deep walk of the
PDF's resource tree — every page's `/XObject`, recursing into every `/Form` —
returns the same 38, across 38 distinct objects, with none nested inside a form
and no inline image anywhere. Part 9 adds a second set:
[10-live-trade-history.md](10-live-trade-history.md) embeds 39 VWAP charts built
from the operator's venue export. They live one level down, in a directory of
their own under the same ignore rule, and [FIGURES.md](FIGURES.md) inventories
them beside the first set. Counting both sets, the built PDF embeds 77 images.

```
artifacts/manual-figures/       the manual's own 38 images
artifacts/vwap-charts/          the 39 charts of Part 9
```

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

The build writes the PDF beside the figures, under the same ignore rule. The
shipped copy of that render is tracked one directory up, at
[../Acervator-Product-Manual.pdf](../Acervator-Product-Manual.pdf). Three flags
move the input directory, the figures directory and the output file.

```python
DEFAULT_DOCS_DIR = REPO_ROOT / "docs" / "manual"        # tools/build_product_manual.py
DEFAULT_FIGURES_DIR = REPO_ROOT / "artifacts" / "manual-figures"
DEFAULT_OUTPUT = REPO_ROOT / "artifacts" / "manual" / "Acervator-Product-Manual.pdf"
# artifacts/ is gitignored, so the built PDF is not in the tree

parser.add_argument("--docs-dir", type=Path, default=DEFAULT_DOCS_DIR)
parser.add_argument("--figures-dir", type=Path, default=DEFAULT_FIGURES_DIR)
parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
```

The tool renumbers the parts of [04-manual-parts.md](04-manual-parts.md) from
one and sets its count word to match. It builds a table of contents down to the
second heading level, so every tab is a row with its own page number, and it
re-renders until each row names the page its heading reached. It exits non-zero
when a row names the wrong page, when a listed section is absent from the PDF,
when the part numbers repeat or skip, or when the count word disagrees with the
number of parts. A figure a part file references and `artifacts/manual-figures/`
does not hold stops the build by name.

## Other document producers in this repository

The handoff documents, the archived development chronicle and the
missing-reference guard all name `generate_essay.py`, and it is not in the tree.
A log over every branch, filtered to additions, deletions and renames, returns no
commit that ever added it. The same query for the Japanese producer returns three
commits, so the query does find a file that once existed.

The query and its control:

```
git log --all --diff-filter=ADR --name-only -- generate_essay.py       # no commits, not in the tree
git log --all --diff-filter=ADR --name-only -- generate_essay_ja.py    # three commits
```

| Producer | Output |
| -------- | ------ |
| `generate_essay_ja.py` | The Japanese product manual, as a PDF, through reportlab |
| `generate_essay_localized.py` | The Acervator technical essay in English, Japanese, Spanish, French and German |
| `save_pdf_report` in `src/core/version_sweep.py` | A version-sweep report, written to the reports directory outside the repository |
| `generate_splash.py` under `deploy/kiosk/splash/` | The AcervatorOS boot splash image |
