"""The comment audit counts what is really there, and its prover can fail.

A failure here means one of two things. Either the counter has gone blind
-- it is reading a ``#`` inside a string or a docstring as a comment, or
missing one that is really a comment. Or the prover has gone blind -- it
is calling two files the same when their executable code differs, or
calling a docstring edit a code change.

Both are worse than no tool. A blind counter reports a cleanup finished
that is not, and a blind prover signs off a change that moved real code.

Two kinds of expectation appear below and each says which it is:

* STATED -- the test writes its own fixture, so its exact numbers are
  known and typed out.
* DERIVED -- the test reads a real file it does not control, so every
  number comes from measuring, never from typing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tools import comment_audit as audit

REPO_ROOT = Path(__file__).resolve().parents[1]

# Two files under the hands-off `dev_harness` tree, so their comment profiles
# do not move under a cleanup unit.
UNEDITED_SPARSE = REPO_ROOT / "dev_harness" / "harness" / "claim_ledger.py"
UNEDITED_DENSE = REPO_ROOT / "dev_harness" / "harness" / "coding_archetype.py"

TRAPS = '''"""Module docstring naming issue #128 and v9.9.9 and 2026-01-01."""

MARKER = "not a comment: # v1.2.3 issue #77"


def helper():
    """Docstring naming MEM-999 and item 4."""
    return MARKER  # trailing comment, see #128 below


# own line one
# own line two v3.20.5
# own line three
VALUE = 1
'''


def write_module(directory: Path, body: str, name: str = "case.py") -> Path:
    """Write one Python file with Unix line endings and return its path."""
    path = directory / name
    path.write_text(body, newline="\n", encoding="utf-8")
    return path


def count_text(body: str) -> audit.FileCount:
    """Count one body of source held in the test, not on disk."""
    return audit.count_source(body, "case.py")


def strip_lines(text: str, rows: set[int]) -> str:
    """Return `text` with the numbered lines removed."""
    kept = [ln for n, ln in enumerate(text.splitlines(), 1) if n not in rows]
    return "\n".join(kept) + "\n"


def test_a_hash_inside_a_string_literal_is_not_a_comment():
    """STATED. The tokeniser is reading string bodies as comments."""
    count = count_text(TRAPS)
    assert count.own_line_comments == 3, count.as_dict()
    assert count.trailing_comments == 1, count.as_dict()


def test_the_string_literal_would_be_counted_by_a_text_search():
    """STATED positive control. The trap line really does hold a hash."""
    assert "#" in TRAPS.splitlines()[2]
    hash_lines = [n for n, ln in enumerate(TRAPS.splitlines(), 1) if "#" in ln]
    assert len(hash_lines) == 6, hash_lines
    count = count_text(TRAPS)
    counted = count.own_line_comments + count.trailing_comments
    assert counted == 4, (counted, hash_lines)


def test_a_hash_inside_a_comment_body_does_not_add_a_second_comment():
    """STATED. A second hash in one comment is being counted as its own."""
    count = count_text("x = 1  # see #128 below\n")
    assert count.trailing_comments == 1, count.as_dict()
    assert count.own_line_comments == 0, count.as_dict()


def test_a_comment_marker_is_not_read_as_an_issue_number():
    """STATED. The comment's own hash is reading as an issue number."""
    count = count_text("# 128 files were counted\n")
    assert count.identifiers == [], count.as_dict()


def test_an_issue_number_inside_a_comment_body_is_read():
    """STATED positive control for the marker test above."""
    count = count_text("# see #128 for the rest\n")
    kinds = [(i.kind, i.text) for i in count.identifiers]
    assert kinds == [("issue", "#128")], count.as_dict()


def test_a_comment_after_code_counts_as_trailing_not_own_line():
    """STATED. A trailing comment is landing in the own-line total."""
    count = count_text("value = 1  # trailing\n# own line\n")
    assert (count.own_line_comments, count.trailing_comments) == (1, 1)


def test_an_indented_comment_owns_its_line():
    """STATED. Leading whitespace is reading as code in front of the comment."""
    count = count_text("def f():\n    # indented\n    return 1\n")
    assert (count.own_line_comments, count.trailing_comments) == (1, 0)


def test_a_docstring_carrying_an_issue_number_reports_no_identifier():
    """STATED. A docstring is being scanned as though it were a comment."""
    body = '"""Docstring naming #128 and v9.9.9 and MEM-999."""\n\nX = 1\n'
    count = count_text(body)
    assert count.identifier_comments == 0, count.as_dict()
    assert count.own_line_comments == 0, count.as_dict()


def test_the_same_text_as_a_comment_reports_three_identifiers():
    """STATED positive control for the docstring test above."""
    count = count_text("# Comment naming #128 and v9.9.9 and MEM-999.\n")
    kinds = sorted(i.kind for i in count.identifiers)
    assert kinds == ["issue", "memory", "version"], count.as_dict()
    assert count.identifier_comments == 1, count.as_dict()


def test_three_consecutive_own_line_comments_make_one_block():
    """STATED. The block finder is missing a run at its lower bound."""
    count = count_text("# one\n# two\n# three\nX = 1\n")
    assert len(count.blocks) == 1, count.as_dict()
    assert count.block_lines == 3, count.as_dict()


def test_two_consecutive_own_line_comments_make_no_block():
    """STATED. The block finder is reporting a run below the block minimum."""
    count = count_text("# one\n# two\nX = 1\n")
    assert count.blocks == [], count.as_dict()
    assert count.block_lines == 0, count.as_dict()


def test_a_blank_line_between_comments_breaks_the_block():
    """STATED. Non-consecutive comment lines are being joined into one run."""
    count = count_text("# one\n# two\n\n# three\n# four\nX = 1\n")
    assert count.blocks == [], count.as_dict()
    assert count.own_line_comments == 4, count.as_dict()


def test_a_trailing_comment_between_two_comments_breaks_the_block():
    """STATED. A line holding code is being counted inside a comment run."""
    count = count_text("# one\n# two\nX = 1  # trailing\n# three\n# four\n")
    assert count.blocks == [], count.as_dict()
    assert count.trailing_comments == 1, count.as_dict()


def test_the_block_finder_reports_the_lines_the_run_covers():
    """STATED. The reported span does not match the run it names."""
    count = count_text("X = 1\n# one\n# two\n# three\n# four\nY = 2\n")
    assert len(count.blocks) == 1, count.as_dict()
    block = count.blocks[0]
    assert (block.start, block.end, block.lines) == (2, 5, 4), count.as_dict()


def test_a_six_digit_colour_does_not_read_as_an_issue_number():
    """STATED. A colour in a comment is inflating the issue count."""
    found = audit.outside_code_identifiers("background #225522 and border #183d18")
    assert found == [], found


def test_a_three_digit_issue_number_reads_as_an_issue():
    """STATED positive control for the colour test above."""
    found = audit.outside_code_identifiers("closes #128")
    assert found == [("issue", "#128")], found


@pytest.mark.parametrize(
    ("body", "kind", "text"),
    [
        ("shipped in v3.25.8 today", "version", "v3.25.8"),
        ("operator directive 2026-06-16", "date", "2026-06-16"),
        ("closes #147", "issue", "#147"),
        ("see issue 147 for the rest", "issue", "issue 147"),
        ("recorded as MEM-236", "memory", "MEM-236"),
        ("bug-2 proper fix", "item", "bug-2"),
    ],
)
def test_each_outside_code_identifier_kind_is_read(body, kind, text):
    """STATED. One kind of outside-code identifier is no longer detected."""
    assert (kind, text) in audit.outside_code_identifiers(
        body
    ), audit.outside_code_identifiers(body)


def test_plain_prose_carries_no_identifier():
    """STATED negative control. Ordinary comment prose is reading as an identifier."""
    assert audit.outside_code_identifiers("Venue fee, not the config estimate.") == []


def test_identifier_comments_counts_lines_and_not_hits():
    """STATED. Two identifiers on one line are counting as two comment lines."""
    count = count_text("# v3.1.0 on 2026-01-01\n")
    assert len(count.identifiers) == 2, count.as_dict()
    assert count.identifier_comments == 1, count.as_dict()


def test_a_file_that_will_not_parse_is_refused():
    """STATED. Broken source is being counted instead of refused."""
    with pytest.raises(audit.Refused):
        count_text("def broken(:\n")


def test_comment_blocks_honours_a_wider_minimum():
    """STATED. The block minimum is hard-wired instead of a parameter."""
    comments = audit.comment_tokens("# one\n# two\n# three\nX = 1\n")
    assert len(audit.comment_blocks(comments, minimum=audit.BLOCK_MINIMUM)) == 1
    assert audit.comment_blocks(comments, minimum=4) == []


def test_the_counter_reports_different_numbers_for_two_real_files():
    """DERIVED. The counter returns the same numbers whatever it reads."""
    report = audit.build_count_report([UNEDITED_SPARSE, UNEDITED_DENSE])
    assert report.files == 2, report.as_dict()
    profiles = {
        (c.own_line_comments, c.trailing_comments, len(c.blocks)) for c in report.counts
    }
    assert len(profiles) == 2, profiles


def test_one_real_file_holds_comments_the_other_barely_does():
    """DERIVED. The dense file no longer out-counts the sparse one."""
    report = audit.build_count_report([UNEDITED_SPARSE, UNEDITED_DENSE])
    by_path = {c.path: c for c in report.counts}
    sparse = by_path[next(p for p in by_path if "claim_ledger" in p)]
    dense = by_path[next(p for p in by_path if "coding_archetype" in p)]
    assert dense.own_line_comments > sparse.own_line_comments
    assert dense.block_lines > sparse.block_lines


def test_removing_every_line_the_counter_named_leaves_no_own_line_comment():
    """DERIVED. A reported comment line number does not point at a comment."""
    text = UNEDITED_DENSE.read_text(encoding="utf-8")
    before = audit.count_source(text, "dense")
    assert before.own_line_comments > 0, before.as_dict()
    rows = {c.line for c in audit.comment_tokens(text) if c.owns_line}
    after = audit.count_source(strip_lines(text, rows), "dense")
    assert after.own_line_comments == 0, after.as_dict()
    assert after.blocks == [], after.as_dict()


def test_the_totals_equal_the_sum_of_the_file_rows():
    """DERIVED. A total has drifted from the rows it claims to add up."""
    report = audit.build_count_report([REPO_ROOT / "tools"])
    assert report.files > 1, report.as_dict()
    assert report.own_line_comments == sum(c.own_line_comments for c in report.counts)
    assert report.blocks == sum(len(c.blocks) for c in report.counts)
    assert report.block_lines == sum(c.block_lines for c in report.counts)


def test_counting_a_directory_holding_no_python_file_is_refused(tmp_path):
    """STATED. An empty scan reports zeroes and reads as a clean result."""
    (tmp_path / "empty").mkdir()
    assert audit.main(["count", str(tmp_path / "empty")]) == 2


def test_counting_a_path_that_does_not_exist_is_refused(tmp_path):
    """STATED. A misspelt path counts nothing and reports success."""
    assert audit.main(["count", str(tmp_path / "no_such_file.py")]) == 2


def test_counting_a_real_directory_exits_zero(tmp_path):
    """STATED positive control. A directory holding a module is refused too."""
    write_module(tmp_path, "X = 1\n")
    assert audit.main(["count", str(tmp_path)]) == 0


def test_strict_exits_one_when_a_block_is_found(tmp_path):
    """STATED. The strict gate cannot report the thing it gates on."""
    path = write_module(tmp_path, "# one\n# two\n# three\nX = 1\n")
    assert audit.main(["count", str(path), "--strict"]) == 1


def test_strict_exits_zero_on_a_file_with_no_block_and_no_identifier(tmp_path):
    """STATED. The strict gate fails a file that is already clean."""
    path = write_module(tmp_path, "X = 1  # trailing\n")
    assert audit.main(["count", str(path), "--strict"]) == 0


def test_strict_exits_one_on_an_outside_code_identifier_alone(tmp_path):
    """STATED. A lone version name in a comment passes the strict gate."""
    path = write_module(tmp_path, "X = 1  # shipped in v3.25.8\n")
    assert audit.main(["count", str(path), "--strict"]) == 1


def real_module_text() -> str:
    """Return the source of one real file the prover tests drive."""
    return UNEDITED_DENSE.read_text(encoding="utf-8")


def test_one_changed_operand_reports_not_identical():
    """DERIVED. The prover signs off a change that moved executable code."""
    before = "import time\n\n\ndef tick():\n    return time.sleep(1000)\n"
    after = before.replace("1000", "1001")
    assert after != before
    verdict = audit.compare_sources(before, after, ("before", "after"))
    assert verdict.identical is False, verdict.as_dict()


def test_removing_every_comment_from_a_real_file_reports_identical():
    """DERIVED. The prover calls a comments-only cleanup a code change."""
    text = real_module_text()
    rows = {c.line for c in audit.comment_tokens(text) if c.owns_line}
    assert rows, "the real file under test holds no own-line comment"
    verdict = audit.compare_sources(text, strip_lines(text, rows), ("before", "after"))
    assert verdict.identical is True, verdict.as_dict()


def test_that_same_cleanup_is_not_identical_as_text():
    """DERIVED positive control. A byte comparison would have answered this."""
    text = real_module_text()
    rows = {c.line for c in audit.comment_tokens(text) if c.owns_line}
    assert strip_lines(text, rows) != text


def test_a_changed_docstring_reports_identical_and_names_its_owner():
    """STATED. A docstring edit is being reported as a change to code."""
    before = 'def helper():\n    """First."""\n    return 1\n'
    after = 'def helper():\n    """Second."""\n    return 1\n'
    verdict = audit.compare_sources(before, after, ("before", "after"))
    assert verdict.identical is True, verdict.as_dict()
    owners = [c["owner"] for c in verdict.changed_docstrings]
    assert owners == ["helper"], verdict.as_dict()


def test_a_method_docstring_is_named_by_its_class():
    """STATED. Two methods of one name cannot be told apart in the report."""
    before = 'class Bot:\n    def run(self):\n        """A."""\n        return 1\n'
    after = before.replace('"""A."""', '"""B."""')
    verdict = audit.compare_sources(before, after, ("before", "after"))
    assert [c["owner"] for c in verdict.changed_docstrings] == ["Bot.run"]


def test_an_unchanged_docstring_is_not_named():
    """STATED negative control. Every docstring is reported as changed."""
    before = 'def helper():\n    """Same."""\n    return 1\n'
    verdict = audit.compare_sources(before, before, ("before", "after"))
    assert verdict.changed_docstrings == [], verdict.as_dict()


def test_a_changed_string_that_is_not_a_docstring_reports_not_identical():
    """STATED. A string the program uses is being blanked with the docstrings."""
    before = 'def helper():\n    """Doc."""\n    return "value"\n'
    after = before.replace('"value"', '"other"')
    verdict = audit.compare_sources(before, after, ("before", "after"))
    assert verdict.identical is False, verdict.as_dict()


def test_a_crlf_copy_of_one_file_proves_identical():
    """DERIVED. Line endings are reaching the comparison."""
    text = real_module_text()
    verdict = audit.compare_sources(
        text, text.replace("\n", "\r\n"), ("before", "after")
    )
    assert verdict.identical is True, verdict.as_dict()


def test_a_file_that_will_not_parse_is_refused_by_the_prover():
    """STATED. Broken source is compared instead of refused."""
    with pytest.raises(audit.Refused):
        audit.compare_sources("X = 1\n", "def broken(:\n", ("before", "after"))


def test_prove_exits_zero_when_the_two_versions_match(tmp_path):
    """STATED. The prover's pass verdict does not reach the exit code."""
    before = write_module(tmp_path, "# a\n# b\n# c\nX = 1\n", "before.py")
    after = write_module(tmp_path, "X = 1\n", "after.py")
    assert audit.main(["prove", str(before), str(after)]) == 0


def test_prove_exits_one_when_the_two_versions_differ(tmp_path):
    """STATED. A moved operand does not reach the exit code."""
    before = write_module(tmp_path, "X = 1000\n", "before.py")
    after = write_module(tmp_path, "X = 1001\n", "after.py")
    assert audit.main(["prove", str(before), str(after)]) == 1


def test_prove_exits_two_on_a_path_that_does_not_exist(tmp_path):
    """STATED. A missing side is compared as though it were empty."""
    before = write_module(tmp_path, "X = 1\n", "before.py")
    assert audit.main(["prove", str(before), str(tmp_path / "gone.py")]) == 2


def test_a_comparison_carries_its_verdict_and_its_docstring_list():
    """STATED. The comparison record no longer reports both halves."""
    verdict = audit.Comparison(identical=True, changed_docstrings=[])
    rendered = verdict.as_dict()
    assert rendered["executable_code_identical"] is True
    assert rendered["changed_docstrings"] == []
