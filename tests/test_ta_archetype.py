"""The TA archetype's fixture pair, one reconstruction per live rule.

`dev_harness/harness/ta_archetype.py` names this file in its module docstring
and in the `falsification` string every report carries. Until
2026-08-13 the file did not exist: the archetype claimed a falsifier
nobody could run, and the harness's own H001 rule reported the dead
citation on every scan of it.

Method. Each rule gets a known-bad body and a known-good body, in
`docs/audits/2026-08-13_ta_archetype/fixtures/`. The bodies live in
their own files rather than inline, because this archetype grades the
literal source it is pointed at -- a test carrying a known-bad body in a
string would be graded as one.

The rules, as MEASURED, not as documented:

  TA001  a docstring promising an average over an undivided `sum(...)`
  TA002  a one-sided clamp on a bounded quantity
  TA003  a threshold constant outside its indicator definitional range
  TA004  a dimensionless ratio compared against an absolute magnitude
  TA010  range normalisation with no zero guard         (chart)
  TA011  fixed-precision rounding of a price, MEDIUM    (chart)

STATED BLIND SPOT, measured while writing this: TA001 keys on a literal
`sum(...)` call. An accumulation loop that promises an average and never
divides is NOT reported -- the first draft of the known-bad fixture used
exactly that shape and came back clean. The rule's domain is the
`sum(...)` form, and this file pins that domain rather than a wider claim
the code does not support.

TA011 is MEDIUM by design, so a file carrying only that finding still
reports passed=True. Its test asserts the FINDING, not the verdict;
asserting the verdict would silently pass if the rule went dead.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dev_harness.harness.ta_archetype import TAArchetype

FIX = REPO_ROOT / "docs" / "audits" / "2026-08-13_ta_archetype" / "fixtures"

# rule -> (blocks the gate?)
BLOCKING_RULES = ("TA001", "TA002", "TA003", "TA004", "TA010")
ADVISORY_RULES = ("TA011",)
ALL_RULES = BLOCKING_RULES + ADVISORY_RULES


def _review(name: str):
    path = FIX / name
    assert path.is_file(), f"fixture missing: {path}"
    return TAArchetype().review(path)


class TestFixturesExist:
    @pytest.mark.parametrize("rule", ALL_RULES)
    def test_bad_fixture_exists(self, rule):
        assert (FIX / f"known_bad_{rule.lower()}.py").is_file()

    @pytest.mark.parametrize("rule", ("TA001", "TA002", "TA003",
                                      "TA010", "TA011"))
    def test_good_fixture_exists(self, rule):
        assert (FIX / f"known_good_{rule.lower()}.py").is_file()


class TestEveryRuleFiresOnItsOwnIncident:
    """POSITIVE CONTROLS. A rule that fires on nothing buys nothing."""

    @pytest.mark.parametrize("rule", ALL_RULES)
    def test_rule_fires(self, rule):
        report = _review(f"known_bad_{rule.lower()}.py")
        assert report.scanned is True
        hits = [f for f in report.findings if f.rule_id == rule]
        assert hits, (
            f"{rule} did not fire on its own reconstruction; the rule is "
            f"dead and every clean report it appears in says nothing")

    @pytest.mark.parametrize("rule", BLOCKING_RULES)
    def test_blocking_rule_blocks(self, rule):
        report = _review(f"known_bad_{rule.lower()}.py")
        assert report.passed is False

    def test_ta011_is_advisory_and_still_reported(self):
        """MEDIUM by design: reported, not a gate."""
        report = _review("known_bad_ta011.py")
        hits = [f for f in report.findings if f.rule_id == "TA011"]
        assert len(hits) == 1
        assert hits[0].severity == "medium"
        assert report.passed is True


class TestTheCorrectedBodiesAreClean:
    """NEGATIVE CONTROLS. Without these, "always red" would pass above."""

    @pytest.mark.parametrize("rule", ("TA001", "TA002", "TA003",
                                      "TA010", "TA011"))
    def test_good_fixture_is_clean(self, rule):
        report = _review(f"known_good_{rule.lower()}.py")
        assert report.scanned is True
        assert report.findings == [], (
            f"the corrected {rule} body reported "
            f"{[(f.rule_id, f.message) for f in report.findings]}")
        assert report.passed is True


class TestTA001Domain:
    """The rule's closed domain, stated rather than assumed."""

    def test_accumulation_loop_is_outside_the_domain(self, tmp_path):
        """MEASURED, not predicted. Documented so nobody reads a clean
        TA001 report as "this function divides"."""
        path = tmp_path / "accumulate.py"
        path.write_text(
            '"""A module."""\n'
            '\n'
            '\n'
            'def smooth(values, period):\n'
            '    """Return the average of the first `period` values."""\n'
            '    total = 0.0\n'
            '    for value in values[:period]:\n'
            '        total += value\n'
            '    return total\n',
            encoding="utf-8")
        report = TAArchetype().review(path)
        assert not [f for f in report.findings if f.rule_id == "TA001"], (
            "TA001 now sees accumulation loops; widen this test rather "
            "than delete it")


class TestReportShape:
    """G4: the count a reader sees must be the count the report carries."""

    def test_by_severity_is_published_and_sums_to_the_findings(self):
        payload = _review("known_bad_ta002.py").to_dict()
        assert "by_severity" in payload, (
            "the gate sums this key to print the finding count; a missing "
            "key sums to 0 and prints '0 findings' over a real report")
        assert sum(payload["by_severity"].values()) == len(
            payload["findings"]) == 1

    def test_a_zero_finding_report_prints_zero(self):
        """The N = 0 half of the same control."""
        payload = _review("known_good_ta002.py").to_dict()
        assert sum(payload["by_severity"].values()) == 0
        assert payload["findings"] == []

    def test_absent_target_is_not_green(self, tmp_path):
        absent = tmp_path / "no_such_file.py"
        assert not absent.exists()
        report = TAArchetype().review(absent)
        assert report.scanned is False
        assert report.passed is False
        assert any("not found" in e.lower() for e in report.errors)

    def test_ruff_status_is_one_of_the_three_words(self):
        """`unavailable: ...` was a fourth status no consumer matched."""
        report = _review("known_good_ta003.py")
        assert report.tool_availability["ruff"] in ("ok", "missing", "error")


class TestFalsificationNamesThisFile:
    def test_report_falsification_cites_a_real_path(self):
        report = _review("known_good_ta003.py")
        assert "tests/test_ta_archetype.py" in report.falsification
        assert (REPO_ROOT / "tests" / "test_ta_archetype.py").is_file()
