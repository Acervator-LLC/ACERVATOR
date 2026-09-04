# Acervator Product Manual

Reference. The product manual, extracted from its PDF into markdown. The text is
verbatim: no wording was changed, shortened, added or removed. Only whitespace
was normalised.

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
| [08-tabs.md](08-tabs.md) | 3 | 29 to 35 | Portfolio panels, Market Inspector, Bot Swarm, Asset Charts, History, Simulator, Paper Trader, Proof of Accumulation, Console, System Status, Settings |
| [FIGURES.md](FIGURES.md) | — | 15 to 44 | The figure inventory |

Pages 36 to 44 carry a figure and no text, so no part file covers them.
[FIGURES.md](FIGURES.md) is their only record.

The Part column is the table's second job: it tells
`tools/build_product_manual.py` which manual part a file belongs to. A file
carrying `—` is not manual text and is not rendered. The order of the rows is
the order the PDF prints them, and the first row is the title page. A row naming
a file that is not on disk, and a `NN-*.md` file this table does not list, both
stop the build. Parts 4 to 9 have no file yet; they print a part page and appear
in the contents, and a new row here folds a file into its part.

## Figures

The manual carries 38 embedded images. They are captured output, so they are not
tracked: `tools/extract_product_manual.py` writes them to
`artifacts/manual-figures/` under the repository root, a path `.gitignore`
excludes. [FIGURES.md](FIGURES.md) lists every one with its page, index, file
name, byte size, pixel size, and whether its page also carries text.

## Extraction record

The source PDF and the operator's exchange CSV exports live outside this
repository and are not committed. `tools/extract_product_manual.py` takes the
PDF path as its `--pdf` parameter and rewrites both this directory and the
figures directory. It exits non-zero when the markdown it wrote no longer holds
every PDF token in order.

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

Compared token by token against the PDF, the markdown holds 9,759 tokens in the
same order, with no addition and no loss.

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
