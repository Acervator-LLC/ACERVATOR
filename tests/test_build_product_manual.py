"""Behaviour of the product manual producer: its manifest, its renumbering and its
contents page numbers."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest
from PIL import Image as PillowImage

from tools.build_product_manual import (
    DEFAULT_DOCS_DIR,
    Part,
    build,
    build_styles,
    load_manual,
    paginate,
    parse_part_list,
    planned_entries,
    read_manifest,
    render_once,
    repair_count_word,
    verify_count_word,
    verify_part_numbers,
    verify_sections_present,
    verify_toc_pages,
    written_toc_misses,
)

COVER = """# Fixture Cover

> An epigraph line.
"""

ALPHA = """# Alpha Section

A paragraph of alpha prose that the renderer lays out on the page.

## Alpha Detail

More alpha prose, enough to occupy a line or two of the frame.
"""

PART_LIST = """# Fixture Manual Parts

Currently there are two such sections with each focusing on ever smaller parts.

Part Title and Area of Focus

1 First Part • First Bullet

3 Second Part

3 Third Part
"""

BETA = """# Beta Section

A paragraph of beta prose.

## Beta Detail

More beta prose to fill the page.
"""

GAMMA = """# Gamma Subsystem

A paragraph of gamma prose that the renderer lays out on the page.
"""

README = """# Fixture Manual

## Contents

| File | Part | Manual pages | Covers |
| ---- | ---- | ------------ | ------ |
| [01-cover.md](01-cover.md) | 1 | 1 | The cover |
| [02-alpha.md](02-alpha.md) | 1 | 2 | Alpha |
| [04-manual-parts.md](04-manual-parts.md) | 1 | 3 | The part list |
| [05-beta.md](05-beta.md) | 2 | 4 | Beta |

## Part 2 subsystem detail

| File | Covers |
| ---- | ------ |
| [05-beta/gamma.md](05-beta/gamma.md) | Gamma |
"""

FIXTURE_FILES = {
    "README.md": README,
    "01-cover.md": COVER,
    "02-alpha.md": ALPHA,
    "04-manual-parts.md": PART_LIST,
    "05-beta.md": BETA,
    "05-beta/gamma.md": GAMMA,
}


def _fixture_docs(root: Path) -> Path:
    docs = root / "manual"
    docs.mkdir(parents=True, exist_ok=True)
    for name, text in FIXTURE_FILES.items():
        path = docs / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
    return docs


@pytest.fixture
def manual_tree(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Return the fixture docs directory, an empty figures directory and the output."""
    docs = _fixture_docs(tmp_path)
    figures = tmp_path / "figures"
    figures.mkdir()
    return docs, figures, tmp_path / "out" / "manual.pdf"


def test_a_built_manual_passes_every_check(manual_tree):
    docs, figures, output = manual_tree
    result = build(docs, figures, output)
    assert result.entries, "the fixture manual produced no contents rows"
    assert result.passed, f"checks failed: {result.checks}"


def test_a_contents_row_naming_the_wrong_page_is_rejected(manual_tree):
    docs, figures, output = manual_tree
    result = build(docs, figures, output)
    first = result.entries[0]

    truthful, _ = verify_toc_pages(output, [first])
    assert truthful, f"{first.text!r} was not found on its own page {first.page}"

    moved = dataclasses.replace(first, page=first.page + 1)
    ok, detail = verify_toc_pages(output, [moved])
    assert not ok, f"a row moved off its heading was accepted: {detail}"
    assert first.text in detail, detail


def test_the_printed_contents_rows_read_back_as_the_rows_that_were_planned(
    manual_tree,
):
    docs, figures, output = manual_tree
    result = build(docs, figures, output)

    rows, misses = written_toc_misses(output)

    assert rows == len(result.entries), (
        f"{rows} rows read off the contents page against "
        f"{len(result.entries)} rendered"
    )
    assert misses == [], misses


def test_a_listed_section_missing_from_the_pdf_is_rejected(manual_tree):
    docs, figures, output = manual_tree
    manual = load_manual(docs, figures)
    trimmed = dataclasses.replace(manual, rows=manual.rows[:-1])
    paginate(trimmed, output)

    ok, detail = verify_sections_present(output, (trimmed.cover, *trimmed.rows))
    assert ok, f"the rendered sections were reported absent: {detail}"

    ok, detail = verify_sections_present(output, (manual.cover, *manual.rows))
    assert not ok, "a section left out of the PDF was reported present"
    assert manual.rows[-1].path.name in detail, detail


def test_a_repeated_part_number_is_rejected():
    parts = (Part(1, "One", ()), Part(2, "Two", ()), Part(2, "Three", ()))
    ok, detail = verify_part_numbers(parts)
    assert not ok, "a repeated part number was accepted"
    assert "repeated" in detail, detail


def test_a_gap_in_the_part_numbers_is_rejected():
    parts = (Part(1, "One", ()), Part(2, "Two", ()), Part(4, "Four", ()))
    ok, detail = verify_part_numbers(parts)
    assert not ok, "a gap in the part numbers was accepted"


def test_the_renumbered_part_list_is_contiguous_from_one():
    parts = parse_part_list(PART_LIST).parts
    assert [part.number for part in parts] == [1, 2, 3]
    ok, detail = verify_part_numbers(parts)
    assert ok, detail


def test_renumbering_leaves_every_title_as_written():
    part_list = parse_part_list(PART_LIST)
    assert [part.title for part in part_list.parts] == [
        "First Part",
        "Second Part",
        "Third Part",
    ]
    assert part_list.parts[0].bullets == ("First Bullet",)


def test_the_operator_part_list_renumbers_without_repeat_or_gap():
    source = (DEFAULT_DOCS_DIR / "04-manual-parts.md").read_text(encoding="utf-8")
    part_list = parse_part_list(source)
    assert part_list.parts, "no part was parsed from the manual part list"
    ok, detail = verify_part_numbers(part_list.parts)
    assert ok, detail
    for part in part_list.parts:
        assert part.title in source, f"{part.title!r} is not the manual's own wording"


def test_a_stale_count_word_is_rejected():
    stale = "Currently there are seven such sections in the manual."
    ok, detail = verify_count_word(stale, 9)
    assert not ok, "a count word naming seven was accepted against nine parts"
    assert "seven" in detail, detail


def test_the_repaired_count_word_matches_the_number_of_parts():
    stale = "Currently there are seven such sections in the manual."
    ok, detail = verify_count_word(repair_count_word(stale, 9), 9)
    assert ok, detail


def test_the_fixture_count_word_follows_its_part_count():
    part_list = parse_part_list(PART_LIST)
    assert "there are three such sections" in part_list.intro
    ok, detail = verify_count_word(part_list.intro, len(part_list.parts))
    assert ok, detail


def test_the_first_pass_numbers_are_wrong_and_the_second_pass_settles(manual_tree):
    docs, figures, output = manual_tree
    manual = load_manual(docs, figures)
    styles = build_styles()
    seed = planned_entries(manual, styles)
    assert seed, "the fixture manual planned no contents rows"

    landed = render_once(manual, seed, output, styles)
    assert landed != seed, "the seeded page numbers were already correct"
    assert paginate(manual, output) == landed


def test_a_readme_row_naming_an_absent_file_is_refused(manual_tree):
    docs, _figures, _output = manual_tree
    assert read_manifest(docs / "README.md", docs), "the intact manifest read empty"

    (docs / "05-beta.md").unlink()
    with pytest.raises(FileNotFoundError, match="05-beta.md"):
        read_manifest(docs / "README.md", docs)


def test_a_part_file_the_readme_omits_is_refused(manual_tree):
    docs, _figures, _output = manual_tree
    assert read_manifest(docs / "README.md", docs), "the intact manifest read empty"

    (docs / "06-gamma.md").write_text("# Gamma\n", encoding="utf-8", newline="\n")
    with pytest.raises(ValueError, match="06-gamma.md"):
        read_manifest(docs / "README.md", docs)


def test_a_page_in_a_subdirectory_takes_the_part_its_heading_names(manual_tree):
    docs, _figures, _output = manual_tree
    rows = read_manifest(docs / "README.md", docs)

    carried = {row.path.relative_to(docs).as_posix(): row.part for row in rows}
    assert carried.get("05-beta/gamma.md") == 2, f"the manifest carried {carried}"


def test_a_page_under_a_part_heading_renders_after_that_part_s_own_files(manual_tree):
    docs, _figures, _output = manual_tree
    rows = read_manifest(docs / "README.md", docs)

    order = [row.path.relative_to(docs).as_posix() for row in rows]
    assert order[-2:] == ["05-beta.md", "05-beta/gamma.md"], f"the order was {order}"


def test_a_page_in_a_subdirectory_the_readme_omits_is_refused(manual_tree):
    docs, _figures, _output = manual_tree
    assert read_manifest(docs / "README.md", docs), "the intact manifest read empty"

    (docs / "05-beta" / "delta.md").write_text(
        "# Delta\n", encoding="utf-8", newline="\n"
    )
    with pytest.raises(ValueError, match="05-beta/delta.md"):
        read_manifest(docs / "README.md", docs)


def test_every_markdown_file_under_the_manual_is_carried_or_listed(manual_tree):
    docs, _figures, _output = manual_tree
    rows = read_manifest(docs / "README.md", docs)

    carried = {row.path for row in rows}
    unaccounted = sorted(
        item.name
        for item in docs.rglob("*.md")
        if item not in carried and item.name != "README.md"
    )
    assert not unaccounted, f"neither carried nor the manifest: {unaccounted}"


def test_an_absent_figure_stops_the_build_by_name(manual_tree):
    docs, figures, output = manual_tree
    (docs / "02-alpha.md").write_text(
        ALPHA + "\n![Alpha figure](p01-i0.png)\n", encoding="utf-8", newline="\n"
    )
    with pytest.raises(FileNotFoundError, match="p01-i0.png"):
        build(docs, figures, output)

    PillowImage.new("RGB", (32, 16), "white").save(figures / "p01-i0.png")
    assert build(docs, figures, output).passed
