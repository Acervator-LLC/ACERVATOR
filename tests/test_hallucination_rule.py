"""Behaviour tests for dev_harness/harness/rules/hallucination.py.

Each test builds a throwaway repository under `tmp_path` and scans a
file inside it, so no assertion depends on the length of any real
source file in this tree.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dev_harness.harness.rules import hallucination


def _repo(tmp_path: Path, cited_lines: int) -> Path:
    """Build a minimal repo whose src/cited.py holds `cited_lines` lines."""
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'x'\n", encoding="utf-8")
    src = tmp_path / "src"
    src.mkdir()
    body = "".join(f"x = {n}\n" for n in range(cited_lines))
    (src / "cited.py").write_text(body, encoding="utf-8")
    return tmp_path


def _h004(repo: Path, source: str) -> list:
    return [
        f
        for f in hallucination.scan(repo / "src" / "target.py", source)
        if f.rule_id == "H004"
    ]


class TestH004:
    def test_a_citation_past_the_end_of_its_file_is_reported(self, tmp_path):
        repo = _repo(tmp_path, cited_lines=40)
        found = _h004(repo, "# see src/cited.py:9173 for the delta\n")
        assert len(found) == 1, f"expected one H004, got {found}"

    def test_the_message_carries_both_the_claim_and_the_real_length(self, tmp_path):
        repo = _repo(tmp_path, cited_lines=40)
        message = _h004(repo, "# see src/cited.py:9173\n")[0].message
        assert "9173" in message, message
        assert "40 lines" in message, message

    def test_the_word_line_spelling_is_reported_too(self, tmp_path):
        repo = _repo(tmp_path, cited_lines=40)
        found = _h004(repo, "# promised at src/cited.py line 500\n")
        assert len(found) == 1, f"expected one H004, got {found}"

    def test_the_finding_names_the_line_the_claim_sits_on(self, tmp_path):
        repo = _repo(tmp_path, cited_lines=40)
        source = "a = 1\nb = 2\n# see src/cited.py:9173\n"
        assert _h004(repo, source)[0].line == 3

    @pytest.mark.parametrize(
        ("label", "source"),
        [
            ("the last line of the file", "# see src/cited.py:40\n"),
            ("the first line", "# see src/cited.py:1\n"),
            ("a file that is not on disk", "# see src/ghost.py:99999\n"),
            ("prose with no citation", "# the connector reads the ticker\n"),
            ("a version number", "# bumped to 3.24.94 in the banner\n"),
        ],
    )
    def test_stays_quiet(self, tmp_path, label, source):
        repo = _repo(tmp_path, cited_lines=40)
        assert _h004(repo, source) == [], f"H004 should be quiet on {label}"

    def test_the_severity_does_not_block_a_green_report(self, tmp_path):
        """H004 reports without stopping a run, as H001 and H003 do."""
        repo = _repo(tmp_path, cited_lines=40)
        assert _h004(repo, "# see src/cited.py:9173\n")[0].severity == "medium"

    def test_markdown_is_scanned_as_well_as_python(self, tmp_path):
        repo = _repo(tmp_path, cited_lines=40)
        found = [
            f
            for f in hallucination.scan(
                repo / "docs" / "note.md",
                "The reader is at `src/cited.py:9173`.\n",
            )
            if f.rule_id == "H004"
        ]
        assert len(found) == 1, f"expected one H004 in markdown, got {found}"
