"""v3.24.20 — pin tests for the docs-archetype calibration.

WHY THIS EXISTS
===============
The docs gate blocked on typography and nothing else. Measured across 40
markdown files under docs/ and the repo root:

    typography.symbols   747   96.6%   <- promoted to HIGH, so it blocked
      .curly_quotes      735
      .ellipsis           10
      .copyright           2
    misc.illogic           0           <- also HIGH, never fired
    security               0           <- also HIGH, never fired
    all other families    26    3.4%

So 100% of the gate's blocking signal was straight-vs-curly quotes, while
the two families that would catch something substantive had never fired.

Worse, proselint has no markdown model: it lints fenced blocks and inline
code spans as English. Two false positives this produced in the real repo:

  * ``O(R)`` — Big-O over reservations — matched
    ``typography.symbols.trademark`` and was reported as "use the symbol".
  * ``DB_PASSWORD = "hunter2"`` inside a code span was linted as prose.

Acting on either would have corrupted the code sample. These tests pin
both halves of the fix: code is stripped before linting, and typography is
advisory rather than blocking.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from tools.harness.docs_archetype import (  # noqa: E402
    _normalize_proselint_severity,
    _strip_markdown_code,
)

# ── the stripper ─────────────────────────────────────────────────


def test_line_count_is_preserved_exactly():
    """Line numbers in findings must still resolve against the real
    file, so the stripper blanks lines rather than removing them.

    Measured with ``split("\\n")`` rather than ``splitlines()``: the
    latter drops a phantom trailing element, which masks exactly the
    off-by-one this test exists to catch.
    """
    src = "para one\n\n```python\nx = 1\ny = 2\n```\n\npara two\n"
    assert len(_strip_markdown_code(src).split("\n")) == len(src.split("\n"))


def test_fenced_block_contents_are_removed():
    src = 'intro\n```python\nDB_PASSWORD = "hunter2"\n```\noutro'
    out = _strip_markdown_code(src)
    assert "hunter2" not in out
    assert "intro" in out
    assert "outro" in out


def test_tilde_fences_are_handled():
    src = "intro\n~~~\nraw = 'code'\n~~~\noutro"
    out = _strip_markdown_code(src)
    assert "raw" not in out


def test_inline_code_spans_are_removed():
    src = 'The flag `DB_PASSWORD = "hunter2"` is hardcoded.'
    out = _strip_markdown_code(src)
    assert "hunter2" not in out
    assert "is hardcoded" in out


def test_prose_outside_code_survives():
    """The stripper must not silence real prose findings."""
    src = "This is a very unique process.\n`code`\nAt the end of the day."
    out = _strip_markdown_code(src)
    assert "very unique" in out
    assert "end of the day" in out


def test_unclosed_fence_does_not_swallow_nothing():
    """A doc with an odd number of fences must still return all lines.

    Regression pin: the first implementation used ``str.splitlines`` and
    ``"\\n".join``, which do not round-trip when the final line is blanked
    and the input has no trailing newline. That silently dropped the last
    line and broke the line-number guarantee.
    """
    src = "a\n```\nb\nc"
    assert len(_strip_markdown_code(src).split("\n")) == 4


def test_empty_input_is_safe():
    assert _strip_markdown_code("") == ""


def test_big_o_in_a_table_is_not_code_stripped():
    """Regression guard. `O(R)` in a table cell is NOT in backticks, so
    the stripper leaves it — which is why the severity demotion below is
    the half of the fix that actually handles it."""
    src = "| fn | now | better |\n|---|---|---|\n| f | O(R) | O(1) |"
    assert "O(R)" in _strip_markdown_code(src)


# ── severity calibration ─────────────────────────────────────────


def test_typography_is_advisory_not_blocking():
    """735 of 747 blocking findings were this one check."""
    for check in (
        "typography.symbols.curly_quotes",
        "typography.symbols.ellipsis",
        "typography.symbols.trademark",
        "typography.symbols.copyright",
        "typography.diacritical_marks",
    ):
        assert (
            _normalize_proselint_severity(check, "warning") == "low"
        ), f"{check} must not block the docs gate"


def test_substantive_families_still_block():
    """The demotion must not disarm the gate entirely."""
    for check in ("misc.illogic.misc", "security.credentials"):
        assert (
            _normalize_proselint_severity(check, "warning") == "high"
        ), f"{check} must still block"


def test_unknown_family_defaults_to_medium():
    assert _normalize_proselint_severity("weasel_words.misc", "warning") == "medium"


def test_suggestion_severity_maps_low():
    assert _normalize_proselint_severity("cliches.misc", "suggestion") == "low"


# ── end-to-end: the gate verdict ─────────────────────────────────


def test_code_heavy_audit_doc_passes_the_gate(tmp_path):
    """An audit report whose body is quoted source code is the normal
    deliverable in this repo. It must not be blocked for containing
    straight quotes inside its code samples."""
    from tools.harness.docs_archetype import DocsArchetype

    doc = tmp_path / "audit.md"
    doc.write_text(
        "# Finding\n\n"
        "How-to: reproduce the defect.\n\n"
        "The call at `main.py:1107` reads a name bound only under a\n"
        "conditional.\n\n"
        "```python\n"
        'DB_PASSWORD = "hunter2"\n'
        "if _autostart_bot_count > 0:\n"
        "```\n\n"
        "| fn | now | better |\n|---|---|---|\n| f | O(R) | O(1) |\n",
        encoding="utf-8",
    )

    report = DocsArchetype().review(doc)
    blocking = [f for f in report.findings if f.severity in ("high", "critical")]
    assert (
        report.passed
    ), f"code-heavy audit doc blocked by: {[f.rule_id for f in blocking]}"
