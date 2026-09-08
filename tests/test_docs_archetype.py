"""Pin tests for dev_harness/harness/docs_archetype.py.

Verifies:
  - Module + public surface
  - passed=True on known_good.md, passed=False on known_bad.md
  - Structure rules DOC001 (no H1), DOC003 (no Diataxis signal),
    DOC005 (duplicate heading) fire on the bad fixture
  - proselint invocation produces findings
  - Vale is either 'ok' or 'missing' (never crashes)
  - falsification populated
  - calibration loads
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dev_harness.harness.docs_archetype import DocsArchetype

REPO = Path(__file__).resolve().parent.parent
FIX = REPO / "harness_fixtures" / "docs_archetype"


class TestSurface:
    def test_archetype_class_exists(self):
        arch = DocsArchetype()
        assert arch.name == "documentation_quality"
        assert arch.version.startswith("1.")
        assert arch.calibration_name == "docs"

    def test_tools_declared(self):
        arch = DocsArchetype()
        assert "proselint" in arch.tools
        assert "structure" in arch.tools
        assert "vale" in arch.tools


class TestFixturesExist:
    def test_known_good_md(self):
        assert (FIX / "known_good.md").is_file()

    def test_known_bad_md(self):
        assert (FIX / "known_bad.md").is_file()


class TestReviewGates:
    def test_known_good_passes(self):
        report = DocsArchetype().review(FIX / "known_good.md")
        assert report.passed is True
        highs = [f for f in report.findings if f.severity in ("critical", "high")]
        assert highs == [], f"unexpected highs on known_good: {highs}"

    def test_known_bad_fails(self):
        report = DocsArchetype().review(FIX / "known_bad.md")
        assert report.passed is False


class TestGroundTruthRecall:
    """Labeled defects in known_bad.md must surface."""

    @pytest.fixture(scope="class")
    def report(self):
        return DocsArchetype().review(FIX / "known_bad.md")

    def test_D1_no_h1_title(self, report):
        hits = [f for f in report.findings if f.rule_id == "DOC001"]
        assert hits, "DOC001 (no H1 title) not caught"

    def test_D2_no_diataxis_signal(self, report):
        hits = [f for f in report.findings if f.rule_id == "DOC003"]
        assert hits, "DOC003 (no Diataxis mode) not caught"

    def test_D3_duplicate_heading(self, report):
        hits = [f for f in report.findings if f.rule_id == "DOC005"]
        assert hits, "DOC005 (duplicate heading) not caught"
        assert hits[0].severity == "high"

    def test_D4_prose_defects_caught_by_proselint(self, report):
        # At minimum: weasel, cliche, corporate speak, "utilize"
        proselint_hits = [f for f in report.findings if f.tool == "proselint"]
        assert (
            len(proselint_hits) >= 5
        ), f"expected many proselint hits on defective prose, got {len(proselint_hits)}"

    def test_D5_curly_quotes_caught(self, report):
        hits = [
            f
            for f in report.findings
            if "curly" in f.message.lower() or "typography.symbols" in f.rule_id
        ]
        assert hits, "curly-quote typography defect not caught"


class TestToolAvailability:
    def test_proselint_status_reported(self):
        report = DocsArchetype().review(FIX / "known_good.md")
        assert "proselint" in report.tool_availability
        assert report.tool_availability["proselint"] in ("ok", "missing", "error")

    def test_vale_missing_does_not_crash(self):
        """Vale isn't installed here; the archetype must handle gracefully."""
        report = DocsArchetype().review(FIX / "known_good.md")
        assert report.tool_availability.get("vale") in ("ok", "missing", "error")
        # If missing, an error message should exist explaining it
        if report.tool_availability.get("vale") == "missing":
            assert any("vale" in e.lower() for e in report.errors)


class TestFalsification:
    def test_populated_on_bad(self):
        report = DocsArchetype().review(FIX / "known_bad.md")
        assert report.falsification
        assert (
            "documentation" in report.falsification.lower()
            or "diataxis" in report.falsification.lower()
        )

    def test_falsification_in_to_dict(self):
        report = DocsArchetype().review(FIX / "known_good.md")
        assert "falsification" in report.to_dict()


class TestCalibration:
    def test_load_calibration(self):
        text = DocsArchetype().load_calibration()
        assert "diataxis" in text.lower()
        assert "google" in text.lower() or "microsoft" in text.lower()


class TestStructureAnalyzer:
    """DOC005 duplicate-heading detection edge cases."""

    def _write_and_review(self, tmp_path, content):
        p = tmp_path / "doc.md"
        p.write_text(content, encoding="utf-8")
        return DocsArchetype().review(p)

    def test_duplicate_h2_fires_doc005(self, tmp_path):
        # Lines: 1='# Title', 2='', 3='Mode: Reference.', 4='',
        #        5='## Step', 6='', 7='text', 8='', 9='## Step'
        report = self._write_and_review(
            tmp_path,
            (
                "# Title\n\nMode: Reference.\n\n"
                "## Step\n\ntext\n\n"
                "## Step\n\ntext\n"
            ),
        )
        hits = [f for f in report.findings if f.rule_id == "DOC005"]
        assert len(hits) == 1
        assert hits[0].line == 9  # second "## Step" is line 9

    def test_case_insensitive_duplicate(self, tmp_path):
        report = self._write_and_review(
            tmp_path, ("# Title\n\nMode: Reference.\n\n" "## STEP\n\n" "## step\n")
        )
        hits = [f for f in report.findings if f.rule_id == "DOC005"]
        assert len(hits) == 1  # normalized to lowercase

    def test_no_duplicate_no_doc005(self, tmp_path):
        report = self._write_and_review(
            tmp_path,
            (
                "# Title\n\nMode: Reference.\n\n"
                "## Step One\n\ntext\n\n"
                "## Step Two\n\ntext\n"
            ),
        )
        hits = [f for f in report.findings if f.rule_id == "DOC005"]
        assert hits == []


class TestContentsRows:
    """DOC006 reads the contents rows a PDF prints and checks the page each names."""

    def test_known_good_pdf_exists(self):
        assert (FIX / "known_good.pdf").is_file()

    def test_known_bad_pdf_exists(self):
        assert (FIX / "known_bad.pdf").is_file()

    def test_known_good_pdf_passes(self):
        report = DocsArchetype().review(FIX / "known_good.pdf")
        assert report.passed is True, report.why_not_green()
        assert report.tool_availability["contents"] == "ok"

    def test_known_bad_pdf_fails(self):
        report = DocsArchetype().review(FIX / "known_bad.pdf")
        assert report.passed is False, "shifted page numbers were accepted"

    def test_every_shifted_row_is_reported(self):
        report = DocsArchetype().review(FIX / "known_bad.pdf")
        hits = [f for f in report.findings if f.rule_id == "DOC006"]
        assert len(hits) == 3, [f.message for f in hits]
        assert all(f.severity == "high" for f in hits), [f.severity for f in hits]

    def test_a_finding_names_the_row_its_page_and_what_that_page_carries(self):
        report = DocsArchetype().review(FIX / "known_bad.pdf")
        first = next(f for f in report.findings if "Alpha Section" in f.message)
        assert "page 3" in first.message, first.message
        assert "Beta Section" in first.message, first.message

    def test_a_row_naming_a_page_the_pdf_does_not_have_is_reported(self):
        report = DocsArchetype().review(FIX / "known_bad.pdf")
        hits = [f for f in report.findings if "names page 5 of 4" in f.message]
        assert hits, [f.message for f in report.findings]

    def test_a_pdf_with_no_contents_rows_is_unread_not_clean(self, tmp_path):
        from reportlab.pdfgen.canvas import Canvas

        empty = tmp_path / "no_contents.pdf"
        canvas = Canvas(str(empty))
        canvas.drawString(72, 700, "This document prints no contents rows.")
        canvas.save()

        report = DocsArchetype().review(empty)
        status = report.tool_availability["contents"]
        assert status.startswith("unread"), status
        assert report.passed is False, "a PDF with nothing to read reported clean"
