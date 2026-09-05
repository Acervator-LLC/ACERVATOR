"""A documentation page describes the software, never how the work was run.

``PHRASES`` matches the workflow commentary that reaches a shipped page: a unit
that did not fix something, a repair left for later, a brief. ``pages`` is every
tracked Markdown page outside ``SKIP_DIRS``, and ``offending_lines`` reports the
lines that carry it. The rule has no exclusion list; a page that needs one has
prose to rewrite instead.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.fixtures.repo_tree import source_files

REPO_ROOT = Path(__file__).resolve().parent.parent

PHRASES = re.compile(
    r"named,?\s+not\s+fixed"
    r"|outside\s+(?:of\s+)?this\s+unit"
    r"|(?:in|for)\s+(?:a\s+)?(?:later|another|future)\s+unit"
    r"|could\s+not\s+be\s+(?:corrected|fixed|repaired)\s+in\s+this\s+unit"
    r"|not\s+fixed\s+in\s+this\s+unit"
    r"|left\s+(?:for|to)\s+(?:a\s+)?(?:later|another|future)\s+unit"
    r"|deferred\s+to\s+(?:a\s+)?(?:later|another|future)\s+unit"
    r"|this\s+unit\s+(?:did\s+not|does\s+not|cannot|could\s+not)\s+"
    r"(?:touch|fix|change|correct)"
    r"|(?:my|the)\s+brief\s+(?:says|forbids|does\s+not)",
    re.IGNORECASE,
)

# Trees that hold a past session's own record, kept as written.
SKIP_DIRS = ("docs-archive",)


def pages() -> list[str]:
    """Every tracked Markdown page the rule reads."""
    return sorted(
        rel
        for rel in (
            path.relative_to(REPO_ROOT).as_posix()
            for path in source_files()
            if path.suffix == ".md"
        )
        if not rel.startswith(SKIP_DIRS)
    )


def offending_lines(text: str, label: str) -> list[str]:
    """Every line of ``text`` that ``PHRASES`` matches."""
    return [
        f"{label}:{number}: {line.strip()[:96]}"
        for number, line in enumerate(text.split("\n"), start=1)
        if PHRASES.search(line)
    ]


@pytest.mark.parametrize("rel", pages())
def test_a_page_carries_no_process_commentary(rel: str) -> None:
    """A page says what is true of the tree, not what a unit did about it."""
    text = (REPO_ROOT / rel).read_text(encoding="utf-8", errors="replace")
    assert offending_lines(text, rel) == []


def test_the_rule_reports_a_planted_phrase() -> None:
    """The control for the scan above: planted commentary must be reported."""
    planted = "The generator is absent, so that is named, not fixed."
    assert offending_lines(planted, "planted.md") == [
        "planted.md:1: The generator is absent, so that is named, not fixed."
    ]


def test_the_rule_leaves_a_statement_of_fact_alone() -> None:
    """The other half of the control: a sentence about the tree must pass."""
    clean = "The generator is `tools/build_product_manual.py` and it builds the manual."
    assert offending_lines(clean, "clean.md") == []


def test_the_rule_reads_more_than_a_handful_of_pages() -> None:
    """A scan of an empty page set would be green about nothing."""
    found = pages()
    assert len(found) > 40, f"pages() found only {len(found)} pages"
