"""Behaviour of the product manual producer's table, fence and diagram rendering."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image as PillowImage
from pypdf import PdfReader

from tools.build_product_manual import (
    FRAME_WIDTH,
    build,
    column_widths,
    inline,
    parse_markdown,
    parse_mermaid,
    plain,
    verify_no_raw_markup,
)

ALIGNED = (
    "SMA(v, n)     mean of the last n values          _sma_tail\n"
    "sigma(v, n)   population deviation              _stdev_tail\n"
    "EMA(v, n)     seed = SMA(v, n) at index n-1            _ema"
)

DIAGRAM = """```mermaid
flowchart LR
    MI["Market Inspector<br/>scans markets"]
    SIM["Simulator<br/>Stone Tablet history"]
    LIVE["Live<br/>real orders"]

    MI --> SIM
    SIM --> LIVE
    MI -. "adopt" .-> LIVE
```"""

COVER = """# Rendering Fixture Cover

> An epigraph line.
"""

PART_LIST = """# Fixture Manual Parts

Currently there are two such sections with each focusing on ever smaller parts.

Part Title and Area of Focus

1 First Part • First Bullet

2 Second Part
"""

TABLE_MD = (
    "| Panel column | Voter | Weight | Module | Candles needed |\n"
    "| ------------ | ----- | ------ | ------ | -------------- |\n"
    "| BB | `bollinger_bands` | 1.0 | `bollinger.py` | 20 |\n"
    "| VTX | `vortex` | 0.9 | `vortex.py` | 15 |\n"
)

TABLES = (
    "# Table Section\n\n"
    "Prose above the table.\n\n" + TABLE_MD + "\n"
    "## Fenced Detail\n\n"
    "```\n" + ALIGNED + "\n```\n\n"
    "- SPENDABLE and LOCKED are the columns of\n"
    "  `SpendableProfitsWidget` in `src/gui/widgets/spendable_profits.py`.\n"
    "- REALISED takes `None` at both call sites.\n\n"
    "The chain reads [the title page](01-cover.md) and calls it "
    "*dissolvendus*, and **Record one** ends there. Archived "
    "ACERVATOR_HOP*.md files stay ACERVATOR_HOP*.md at the root.\n"
)

DIAGRAMS = "# Diagram Section\n\nProse above the diagram.\n\n" + DIAGRAM + "\n"

README = """# Rendering Fixture

## Contents

| File | Part | Manual pages | Covers |
| ---- | ---- | ------------ | ------ |
| [01-cover.md](01-cover.md) | 1 | 1 | The cover |
| [04-manual-parts.md](04-manual-parts.md) | 1 | 2 | The part list |
| [05-tables.md](05-tables.md) | 1 | 3 | Tables and fences |
| [06-diagrams.md](06-diagrams.md) | 2 | 4 | Diagrams |
"""

FIXTURE_FILES = {
    "README.md": README,
    "01-cover.md": COVER,
    "04-manual-parts.md": PART_LIST,
    "05-tables.md": TABLES,
    "06-diagrams.md": DIAGRAMS,
}


def _write(docs: Path, files: dict[str, str]) -> Path:
    docs.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (docs / name).write_text(text, encoding="utf-8", newline="\n")
    return docs


def _pdf_text(output: Path) -> str:
    return "\n".join(page.extract_text() or "" for page in PdfReader(str(output)).pages)


@pytest.fixture
def manual_tree(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Return the fixture docs directory, an empty figures directory and the output."""
    docs = _write(tmp_path / "manual", FIXTURE_FILES)
    figures = tmp_path / "figures"
    figures.mkdir()
    return docs, figures, tmp_path / "out" / "manual.pdf"


def test_a_pipe_table_parses_as_one_table_block_carrying_its_cells():
    blocks = parse_markdown(TABLES)
    tables = [block for block in blocks if block.kind == "table"]
    assert len(tables) == 1, f"expected one table block, got {[b.kind for b in blocks]}"
    assert tables[0].rows[0][0] == "Panel column", tables[0].rows
    assert tables[0].rows[1][1] == "`bollinger_bands`", tables[0].rows
    assert len(tables[0].rows) == 3, "the separator row should not become a data row"

    plainer = parse_markdown("# Heading\n\nProse with no table at all.\n")
    assert not [
        block for block in plainer if block.kind == "table"
    ], "a document with no pipe line still produced a table block"


def test_a_table_reaches_the_pdf_as_cells_and_not_as_a_line_of_pipes(manual_tree):
    docs, figures, output = manual_tree
    result = build(docs, figures, output)
    assert result.passed, f"checks failed: {result.checks}"

    text = _pdf_text(output)
    assert "Panel column" in text, "the table header never reached the page"
    assert "bollinger_bands" in text, "a table cell never reached the page"
    assert "| BB |" not in text, "the markdown row printed as literal pipes"

    literal = dict(FIXTURE_FILES)
    literal["05-tables.md"] = TABLES.replace(TABLE_MD, f"```\n{TABLE_MD}```\n")
    build(_write(docs.parent / "literal", literal), figures, output)
    assert "| BB |" in _pdf_text(
        output
    ), "the scan cannot see a pipe row, so its absence above proves nothing"
    ok, detail = verify_no_raw_markup(output)
    assert not ok, "a page printing markdown table rows was reported clean"
    assert "table row" in detail, detail


def test_a_fenced_block_reaches_the_pdf_without_backticks_and_keeps_its_columns(
    manual_tree,
):
    docs, figures, output = manual_tree
    build(docs, figures, output)

    text = _pdf_text(output)
    assert "`" not in text, "a backtick printed onto the page"
    for line in ALIGNED.split("\n"):
        assert line in text, f"the fence lost its internal spacing: {line!r}"
    assert (
        "SMA(v, n) mean of the last n values _sma_tail" not in text
    ), "the fence collapsed to single spaces"


def test_a_stray_backtick_is_reported_so_a_clean_page_means_something(manual_tree):
    docs, figures, output = manual_tree
    build(docs, figures, output)
    ok, detail = verify_no_raw_markup(output)
    assert ok, detail

    stray = dict(FIXTURE_FILES)
    stray["05-tables.md"] = TABLES.replace("Prose above", "Prose ` above")
    build(_write(docs.parent / "stray", stray), figures, output)
    ok, detail = verify_no_raw_markup(output)
    assert not ok, "a page carrying a backtick was reported clean"
    assert "backtick" in detail, detail


def test_a_backtick_a_fenced_block_quotes_is_source_and_not_a_leak(manual_tree):
    docs, figures, output = manual_tree
    quoted = dict(FIXTURE_FILES)
    quoted["05-tables.md"] = TABLES.replace(ALIGNED, f"{ALIGNED}\n# `tr_all` is one")
    build(_write(docs.parent / "quoted", quoted), figures, output)

    assert "`tr_all` is one" in _pdf_text(
        output
    ), "the quoted comment never reached the page, so a clean scan proves nothing"
    ok, detail = verify_no_raw_markup(output)
    assert ok, f"a backtick a code block quotes was called a leak: {detail}"

    loose = dict(FIXTURE_FILES)
    loose["05-tables.md"] = TABLES.replace(
        "Prose above the table.", "Prose above the `tr_all is one table."
    )
    build(_write(docs.parent / "loose", loose), figures, output)
    ok, detail = verify_no_raw_markup(output)
    assert not ok, "the same character left in prose was reported clean"
    assert "backtick" in detail, detail


def test_a_mermaid_block_never_reaches_the_pdf_as_source(manual_tree):
    docs, figures, output = manual_tree
    build(docs, figures, output)

    text = _pdf_text(output)
    assert "mermaid" not in text.lower(), "the mermaid keyword printed onto the page"
    assert "flowchart LR" not in text, "the mermaid header printed onto the page"
    assert "-->" not in text, "a mermaid arrow printed onto the page"
    assert "Diagram: flowchart, left to right" in text, "the diagram lost its caption"
    assert "Market Inspector" in text, "a diagram node label never reached the page"
    assert "adopt" in text, "a diagram edge label never reached the page"


def test_a_page_carrying_mermaid_source_is_reported(manual_tree):
    docs, figures, output = manual_tree
    leaking = dict(FIXTURE_FILES)
    leaking["06-diagrams.md"] = DIAGRAMS.replace("```mermaid", "mermaid").replace(
        "\n```", ""
    )
    build(_write(docs.parent / "leaking", leaking), figures, output)
    ok, detail = verify_no_raw_markup(output)
    assert not ok, "a page carrying an unfenced mermaid flowchart was reported clean"


def test_parse_mermaid_resolves_every_node_id_into_its_label():
    diagram = parse_mermaid(DIAGRAM.split("\n", 1)[1].rsplit("\n", 1)[0])
    assert diagram.caption == "Diagram: flowchart, left to right", diagram.caption
    assert diagram.edges == (
        (
            "Market Inspector — scans markets",
            "Simulator — Stone Tablet history",
            "",
            False,
        ),
        ("Simulator — Stone Tablet history", "Live — real orders", "", False),
        ("Market Inspector — scans markets", "Live — real orders", "adopt", True),
    ), diagram.edges
    assert not diagram.loose, diagram.loose


def test_a_diagram_with_no_link_keeps_its_lines_instead_of_being_dropped():
    diagram = parse_mermaid("sequenceDiagram\n    Alice: hello\n    Bob: reply\n")
    assert not diagram.edges, diagram.edges
    assert diagram.source == (
        "sequenceDiagram",
        "Alice: hello",
        "Bob: reply",
    ), diagram.source


def test_a_table_wider_than_the_frame_is_shrunk_to_it():
    wide = [
        ["Where", "The departure", "Measured effect"],
        ["z" * 90, "d" * 120, "m" * 110],
    ]
    widths = column_widths(wide)
    assert sum(widths) <= FRAME_WIDTH + 0.5, f"{sum(widths)} over {FRAME_WIDTH}"
    assert min(widths) > 0, widths

    narrow = [["A", "B"], ["one", "two"]]
    assert (
        sum(column_widths(narrow)) < FRAME_WIDTH / 2
    ), "a narrow table was stretched or shrunk instead of taking its natural width"


def test_a_wrapped_bullet_keeps_the_first_two_characters_of_its_second_line():
    blocks = parse_markdown(TABLES)
    bullets = [block.text for block in blocks if block.kind == "bullet"]
    assert len(bullets) == 2, bullets
    assert bullets[0].endswith(
        "`SpendableProfitsWidget` in `src/gui/widgets/spendable_profits.py`."
    ), bullets[0]
    assert bullets[1] == "REALISED takes `None` at both call sites.", bullets[1]


def test_inline_sets_a_code_span_in_mono_and_drops_its_backticks():
    marked = inline("the `bollinger.py` module")
    assert "`" not in marked, marked
    assert '<font face="Courier">bollinger.py</font>' in marked, marked
    assert plain("the `bollinger.py` module") == "the bollinger.py module"


def test_inline_keeps_a_link_label_and_drops_its_target():
    assert inline("read [the title page](01-cover.md) now") == (
        "read the title page now"
    )
    assert plain("read [the title page](01-cover.md) now") == "read the title page now"


def test_inline_marks_emphasis_but_leaves_a_glob_asterisk_alone():
    assert inline("**Record one** ends") == "<b>Record one</b> ends"
    assert (
        inline("calls it *dissolvendus*, then") == "calls it <i>dissolvendus</i>, then"
    )
    globbed = "Archived ACERVATOR_HOP*.md files stay ACERVATOR_HOP*.md at the root."
    assert inline(globbed) == globbed, inline(globbed)


def test_inline_marks_emphasis_that_wraps_a_code_span():
    marked = inline("**Record three begins `6e4f46b`, 18 August.**")
    assert marked.startswith("<b>Record three begins "), marked
    assert marked.endswith(", 18 August.</b>"), marked
    assert "*" not in marked, marked


def test_every_figure_the_manual_names_is_embedded_in_the_pdf(manual_tree):
    docs, figures, output = manual_tree
    build(docs, figures, output)
    assert sum(len(page.images) for page in PdfReader(str(output)).pages) == 0

    with_figure = dict(FIXTURE_FILES)
    with_figure["06-diagrams.md"] = DIAGRAMS + "\n![A fixture figure](p01-i0.png)\n"
    PillowImage.new("RGB", (48, 24), "white").save(figures / "p01-i0.png")
    build(_write(docs.parent / "figured", with_figure), figures, output)
    assert sum(len(page.images) for page in PdfReader(str(output)).pages) == 1
