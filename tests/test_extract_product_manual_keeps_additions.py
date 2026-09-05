"""`write_parts` never drops a block a part file gained after its extraction.

Each test drives the real `write_parts` over a fixture directory under
`tmp_path`, and none of them read or write the manual in the repository.
`blocks` builds one `Block` per `PART_FILES` boundary, and
`insert_after_first_block` puts a section between two of them. Every refusal
test is paired with a `write_parts` run that must still succeed.
"""

from pathlib import Path

import pytest

from tools.extract_product_manual import (
    PART_FILES,
    AddedContentError,
    Block,
    added_blocks,
    missing_blocks,
    write_parts,
)

ADDED = "## Added by hand\n\nA section written from the source, not the PDF."


def blocks(marker: str = "text") -> list[Block]:
    """Return one Block per PART_FILES boundary, each carrying unique text."""
    keys: list[tuple[int, int]] = []
    for _name, start, end, _title in PART_FILES:
        keys.extend((start, end))
    return [
        Block(page=page, index=index, lines=[f"page {page} block {index} {marker}"])
        for page, index in keys
    ]


def insert_after_first_block(path: Path, text: str) -> None:
    """Put text between the first and second blocks of path, not at its end."""
    head, _, tail = path.read_text(encoding="utf-8").partition("\n\n")
    path.write_text(f"{head}\n\n{text}\n\n{tail}", encoding="utf-8", newline="\n")


class TestAFirstExtraction:
    def test_an_empty_directory_gains_every_part_file(self, tmp_path):
        docs = tmp_path / "manual"
        assert not docs.exists(), "the fixture must start with no manual directory"

        write_parts(blocks(), docs)

        assert sorted(path.name for path in docs.glob("*.md")) == sorted(
            name for name, *_rest in PART_FILES
        )

    def test_every_part_file_carries_its_transcription(self, tmp_path):
        docs = tmp_path / "manual"
        write_parts(blocks(), docs)

        empty = [name for name, *_rest in PART_FILES if not (docs / name).read_text()]

        assert not empty, f"part files written with no text: {empty}"


class TestTheRefusal:
    def test_a_clean_re_run_does_not_refuse(self, tmp_path):
        docs = tmp_path / "manual"
        write_parts(blocks(), docs)

        write_parts(blocks(), docs)

    def test_an_added_block_refuses(self, tmp_path):
        docs = tmp_path / "manual"
        write_parts(blocks(), docs)
        insert_after_first_block(docs / "07-indicators.md", ADDED)

        with pytest.raises(AddedContentError):
            write_parts(blocks(), docs)

    def test_the_refusal_names_the_file_that_was_extended(self, tmp_path):
        docs = tmp_path / "manual"
        write_parts(blocks(), docs)
        insert_after_first_block(docs / "07-indicators.md", ADDED)

        with pytest.raises(AddedContentError) as caught:
            write_parts(blocks(), docs)

        message = str(caught.value)
        assert "07-indicators.md" in message, message
        assert (
            "01-title.md" not in message
        ), f"the refusal names a file that gained nothing: {message}"

    def test_the_refusal_quotes_the_first_added_line(self, tmp_path):
        docs = tmp_path / "manual"
        write_parts(blocks(), docs)
        insert_after_first_block(docs / "07-indicators.md", ADDED)

        with pytest.raises(AddedContentError) as caught:
            write_parts(blocks(), docs)

        assert "## Added by hand" in str(caught.value), str(caught.value)

    def test_the_refusal_writes_no_part_file(self, tmp_path):
        docs = tmp_path / "manual"
        write_parts(blocks(), docs)
        insert_after_first_block(docs / "07-indicators.md", ADDED)
        (docs / "01-title.md").unlink()

        with pytest.raises(AddedContentError):
            write_parts(blocks(), docs)

        assert not (
            docs / "01-title.md"
        ).exists(), "a part file was rewritten before the refusal"

    def test_re_extract_writes_the_part_file_the_refusal_withheld(self, tmp_path):
        docs = tmp_path / "manual"
        write_parts(blocks(), docs)
        insert_after_first_block(docs / "07-indicators.md", ADDED)
        (docs / "01-title.md").unlink()

        write_parts(blocks(), docs, re_extract=True)

        assert (docs / "01-title.md").exists()


class TestReExtraction:
    def test_it_keeps_a_section_added_to_a_part_file(self, tmp_path):
        docs = tmp_path / "manual"
        write_parts(blocks(), docs)
        insert_after_first_block(docs / "07-indicators.md", ADDED)

        write_parts(blocks(), docs, re_extract=True)

        assert ADDED in (docs / "07-indicators.md").read_text(encoding="utf-8")

    def test_it_keeps_the_transcription_the_added_section_sits_between(self, tmp_path):
        docs = tmp_path / "manual"
        write_parts(blocks(), docs)
        before = (docs / "07-indicators.md").read_text(encoding="utf-8")
        insert_after_first_block(docs / "07-indicators.md", ADDED)

        write_parts(blocks(), docs, re_extract=True)

        after = (docs / "07-indicators.md").read_text(encoding="utf-8")
        for block in before.strip("\n").split("\n\n"):
            assert block in after, f"re-extraction dropped {block!r}"

    def test_a_revised_transcription_reaches_the_file(self, tmp_path):
        docs = tmp_path / "manual"
        write_parts(blocks(), docs)
        insert_after_first_block(docs / "07-indicators.md", ADDED)
        assert "revised" not in (docs / "07-indicators.md").read_text(encoding="utf-8")

        write_parts(blocks("revised"), docs, re_extract=True)

        assert "revised" in (docs / "07-indicators.md").read_text(encoding="utf-8")

    def test_a_revised_transcription_still_keeps_the_added_section(self, tmp_path):
        docs = tmp_path / "manual"
        write_parts(blocks(), docs)
        insert_after_first_block(docs / "07-indicators.md", ADDED)

        write_parts(blocks("revised"), docs, re_extract=True)

        assert ADDED in (docs / "07-indicators.md").read_text(encoding="utf-8")


class TestASubdirectoryOfTheDocsDir:
    def test_it_is_never_written(self, tmp_path):
        docs = tmp_path / "manual"
        write_parts(blocks(), docs)
        nested = docs / "08-tabs"
        nested.mkdir()
        detail = nested / "simulator.md"
        detail.write_text("Fleet Replay and Stone Tablets.\n", encoding="utf-8")
        before = detail.read_bytes()

        write_parts(blocks("revised"), docs, re_extract=True)

        assert detail.read_bytes() == before

    def test_the_same_comparison_sees_a_part_file_change(self, tmp_path):
        docs = tmp_path / "manual"
        write_parts(blocks(), docs)
        part = docs / "07-indicators.md"
        before = part.read_bytes()

        write_parts(blocks("revised"), docs, re_extract=True)

        assert part.read_bytes() != before


class TestTheBlockAlignment:
    def test_added_blocks_is_empty_for_an_untouched_file(self):
        fresh = ["# One", "Two", "Three"]

        assert added_blocks(list(fresh), fresh) == []

    def test_added_blocks_reports_an_interleaved_addition(self):
        fresh = ["# One", "Two", "Three"]
        existing = ["# One", "Added", "Two", "Three"]

        assert added_blocks(existing, fresh) == ["Added"]

    def test_missing_blocks_is_empty_when_the_file_holds_them_all(self):
        fresh = ["# One", "Two", "Three"]
        existing = ["# One", "Added", "Two", "Three"]

        assert missing_blocks(existing, fresh) == []

    def test_missing_blocks_leads_with_the_dropped_block(self):
        fresh = ["# One", "Two", "Three"]
        existing = ["# One", "Three"]

        assert missing_blocks(existing, fresh)[0] == "Two"
