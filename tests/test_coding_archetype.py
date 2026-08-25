"""Pin tests for tools/harness/coding_archetype.py.

Verifies:
  - Module imports cleanly
  - Public surface: CodingArchetype class + ArchetypeReport + Finding
  - passed=True on known_good.py fixture
  - passed=False on known_bad.py fixture with all 5 ground-truth defects surfaced
  - falsification field populated
  - calibration loads
  - Bandit severity remap fires for B105 + B101

All references are to files that MUST exist in a shipped tree. If any
disappears, tests fail with the specific missing path.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.harness.coding_archetype import (
    ArchetypeReport,
    CodingArchetype,
    Finding,
    _BANDIT_SEVERITY_OVERRIDES,
)

REPO = Path(__file__).resolve().parent.parent
FIX = (
    REPO
    / "docs"
    / "audits"
    / "2026-07-24_coding_archetype_multi_agent_test"
    / "fixtures"
)


class TestSurface:
    def test_report_and_finding_are_the_shared_contract(self):
        """The names this module imports are the PUBLIC surface.

        They were imported and never used, so vulture reported two
        dead imports and the docstring's claim about the surface
        rested on nothing. Both are now exercised: `Finding` builds,
        and `ArchetypeReport` answers the three conditions of green.
        """
        finding = Finding(
            tool="t", severity="high", file="f", line=1, rule_id="R", message="m"
        )
        assert finding.to_dict()["severity"] == "high"
        report = ArchetypeReport(target="x")
        assert report.passed is False, "an unscanned report is not green"
        report.scanned = True
        report.tool_availability["ruff"] = "ok"
        assert report.passed is True
        report.findings.append(finding)
        assert report.passed is False

    def test_archetype_class_exists(self):
        arch = CodingArchetype()
        assert arch.name == "coding_quality"
        assert arch.version.startswith("2.")
        assert arch.calibration_name == "coding"

    def test_tools_declared(self):
        arch = CodingArchetype()
        assert "ruff" in arch.tools
        assert "mypy" in arch.tools
        assert "bandit" in arch.tools
        assert "vulture" in arch.tools

    def test_bandit_overrides_include_known_dangerous(self):
        for rule in (
            "B101",
            "B105",
            "B106",
            "B107",
            "B303",
            "B324",
            "B501",
            "B502",
            "B506",
            "B602",
            "B605",
            "B609",
        ):
            assert (
                _BANDIT_SEVERITY_OVERRIDES.get(rule) == "high"
            ), f"{rule} must remap to 'high'"


class TestFixturesExist:
    def test_known_good_exists(self):
        assert (FIX / "known_good.py").is_file()

    def test_known_bad_exists(self):
        assert (FIX / "known_bad.py").is_file()


class TestReviewGates:
    def test_known_good_passes(self):
        report = CodingArchetype().review(FIX / "known_good.py")
        assert report.passed is True
        # allowed: some low-severity ruff style findings; NO high/critical
        highs = [f for f in report.findings if f.severity in ("critical", "high")]
        assert highs == [], f"unexpected highs on known_good: {highs}"

    def test_known_bad_fails(self):
        report = CodingArchetype().review(FIX / "known_bad.py")
        assert report.passed is False
        highs = [f for f in report.findings if f.severity in ("critical", "high")]
        assert len(highs) >= 1, "known_bad must produce at least one high finding"

    def test_missing_target_is_not_green(self, tmp_path):
        """A scan that never happened is not a clean scan.

        This test used to assert `passed is True`, with the comment
        "no findings, so gate reads as pass". That was the defect
        written down as the contract. Measured 2026-08-13 against
        one confirmed-absent path, all five archetypes answered
        exit 0, passed=true, 0 findings and one line in `errors`
        that no caller read. The invariant is restated, not
        relaxed: the report must still RECORD the error, and it
        must no longer be green.
        """
        absent = tmp_path / "does_not_exist.py"
        assert not absent.exists()
        report = CodingArchetype().review(absent)
        assert report.scanned is False
        assert report.passed is False
        assert any("not found" in e.lower() for e in report.errors)
        assert any("never scanned" in r for r in report.why_not_green())

    def test_present_target_is_still_judged_on_its_findings(self):
        """The paired control: refusing an absent path must not
        refuse a present one. Without this, "nothing is green" and
        "the absent path is not green" look identical."""
        report = CodingArchetype().review(FIX / "known_good.py")
        assert report.scanned is True
        assert report.passed is True
        assert report.why_not_green() == []


class TestGroundTruthRecall:
    """All 5 hand-labeled defects (D1-D5) in known_bad.py must surface."""

    @pytest.fixture(scope="class")
    def report(self):
        return CodingArchetype().review(FIX / "known_bad.py")

    def test_D1_unused_import_caught(self, report):
        # Vulture unused-import or ruff F401
        hits = [
            f
            for f in report.findings
            if "unused" in f.message.lower()
            and "import" in f.message.lower()
            or f.rule_id == "F401"
        ]
        assert hits, "D1 unused_import not caught"

    def test_D3_missing_type_hints_caught(self, report):
        # mypy or ruff ANN family
        hits = [
            f
            for f in report.findings
            if f.rule_id.startswith("ANN")
            or "type" in f.message.lower()
            and "hint" in f.message.lower()
            or f.tool == "mypy"
            and "untyped" in f.message.lower()
        ]
        assert hits, "D3 missing_type_hints not caught"

    def test_D4_hardcoded_password_caught_high(self, report):
        # bandit B105 (with severity remap to high) or ruff S105
        hits = [f for f in report.findings if f.rule_id in ("B105", "S105")]
        assert hits, "D4 hardcoded_password not caught"
        assert any(
            f.severity == "high" for f in hits
        ), "D4 must be high severity after remap"

    def test_D5_assert_for_security_caught_high(self, report):
        # bandit B101 (remap to high) or ruff S101
        hits = [f for f in report.findings if f.rule_id in ("B101", "S101")]
        assert hits, "D5 assert_for_security not caught"
        assert any(
            f.severity == "high" for f in hits
        ), "D5 must be high severity after remap"


class TestFalsification:
    def test_falsification_populated_on_good(self):
        report = CodingArchetype().review(FIX / "known_good.py")
        assert report.falsification, "falsification field must be non-empty"
        assert len(report.falsification) > 100, "falsification must be substantive"
        assert "wrong if" in report.falsification.lower()

    def test_falsification_populated_on_bad(self):
        report = CodingArchetype().review(FIX / "known_bad.py")
        assert report.falsification

    def test_falsification_in_to_dict(self):
        report = CodingArchetype().review(FIX / "known_good.py")
        d = report.to_dict()
        assert "falsification" in d
        assert d["falsification"] == report.falsification


class TestCalibration:
    def test_load_calibration_returns_text(self):
        text = CodingArchetype().load_calibration()
        assert len(text) > 500
        assert "coding" in text.lower()

    def test_calibration_missing_raises_cleanly(self, monkeypatch):
        arch = CodingArchetype()
        # Point at a name that doesn't exist
        monkeypatch.setattr(arch, "calibration_name", "nonexistent_domain")
        with pytest.raises(FileNotFoundError):
            arch.load_calibration()
