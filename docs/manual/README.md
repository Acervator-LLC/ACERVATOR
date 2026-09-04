# Acervator Product Manual

Reference. The product manual, extracted from its PDF into markdown. The text is
verbatim: no wording was changed, shortened, added or removed. Only whitespace
was normalised.

## Contents

| File | Manual pages | Covers |
| ---- | ------------ | ------ |
| [01-title.md](01-title.md) | 1 | Title and the epigraph |
| [02-legal.md](02-legal.md) | 2 to 4 | Copyright, contact, legal disclaimers, algorithmic-trading risk |
| [03-executive-summary.md](03-executive-summary.md) | 5 to 7 | Executive summary, origin of the method, support addresses |
| [04-manual-parts.md](04-manual-parts.md) | 8 to 9 | The manual's own part list and tab list |
| [05-novel-concepts.md](05-novel-concepts.md) | 10 to 14 | Novel concepts and patent candidate catalogue, entries 1 to 17 |
| [06-trading-tab.md](06-trading-tab.md) | 14 to 27 | System architecture, then the Trading Tab walkthrough |
| [07-indicators.md](07-indicators.md) | 27 to 29 | Indicator Voting Panel and the twelve indicators |
| [08-tabs.md](08-tabs.md) | 29 to 35 | Portfolio panels, Market Inspector, Bot Swarm, Asset Charts, History, Simulator, Paper Trader, Proof of Accumulation, Console, System Status, Settings |
| [FIGURES.md](FIGURES.md) | 15 to 44 | The figure inventory |

Pages 36 to 44 carry a figure and no text, so no part file covers them.
[FIGURES.md](FIGURES.md) is their only record.

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

## Manual producers in this repository

No producer builds the English manual. The PDF is authored outside the
repository, and this directory is transcribed from it.

`generate_essay.py` is named by the handoff documents, the archived development
chronicle and the missing-reference guard, and it is not in the tree.
`git log --all --diff-filter=ADR` returns no commit that ever added it; the same
query for `generate_essay_ja.py` returns commits, so the query does find a file
that existed.

What does produce documents:

| Producer | Output |
| -------- | ------ |
| `generate_essay_ja.py` | The Japanese product manual, as a PDF, through reportlab |
| `generate_essay_localized.py` | The Acervator technical essay in English, Japanese, Spanish, French and German |
| `save_pdf_report` in `src/core/version_sweep.py` | A version-sweep report, written to the reports directory outside the repository |
| `generate_splash.py` under `deploy/kiosk/splash/` | The AcervatorOS boot splash image |
