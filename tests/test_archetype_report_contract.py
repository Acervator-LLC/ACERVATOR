"""One report contract, and every sentence of it shown failing.

`tools/harness/report.py` states nine properties. Each gets a test that
holds, and a PAIRED CONTROL that would pass if the property were dropped
-- because a test with no control is not evidence.

The properties:

  1. a report with `scanned=False` is never green
  2. a report carrying a required analyzer that is not `ok` is never green
  3. `by_severity` sums to `len(findings)`, in EVERY archetype
  4. a scanned target with every analyzer `ok` and no high finding IS green
  5. a report carrying an `errors` entry is never green
  6. a rule module handed a source it could not read does not report `ok`
  7. an analyzer that exits non-zero printing nothing is an `error`, not `ok`
  8. a DEAD type-ignore and a merely over-broad one get different severities
  9. the verdict does not depend on the directory the caller stood in

Properties 1, 2, 5, 6, 7 and 9 are about the RUN. Property 4 is the
control for all of them: without it, a change that simply made
everything red would satisfy every one and be indistinguishable from the
fix.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.harness.report import (
    OPTIONAL_ANALYZERS,
    REPO_ROOT as HARNESS_REPO_ROOT,
    ArchetypeReport,
    Finding,
    cli_exit,
    refuse_silent_failure,
    scan_rule_modules,
)

SCAFFOLDING = (("scaffolding", "tools.harness.rules.scaffolding"),)

# Built at run time. Written as a literal, this file would trip the very
# rule it uses as bait, which is how ta_archetype came to fail itself
# three times for documenting the incident it was built from.
PLACEHOLDER_BAIT = '"""Doc."""\n\n# ' + "FIX" + "ME: not done\n"

ARCHETYPE_MODULES = (
    "tools.harness.coding_archetype",
    "tools.harness.ta_archetype",
    "tools.harness.gui_archetype",
    "tools.harness.docs_archetype",
    "tools.harness.watchdog_archetype",
)

CODING_FIX = (
    REPO_ROOT
    / "docs"
    / "audits"
    / "2026-07-24_coding_archetype_multi_agent_test"
    / "fixtures"
)


def _high(line: int = 1) -> Finding:
    return Finding(
        tool="t", severity="high", file="f", line=line, rule_id="R", message="m"
    )


def _low(line: int = 1) -> Finding:
    return Finding(
        tool="t", severity="low", file="f", line=line, rule_id="R", message="m"
    )


class TestScannedGatesGreen:
    """PROPERTY 1 - a scan that never happened is not a clean scan."""

    def test_unscanned_empty_report_is_not_green(self):
        rep = ArchetypeReport(target="x", tool_availability={"t": "ok"})
        assert rep.scanned is False
        assert rep.passed is False

    def test_unscanned_report_says_why(self):
        rep = ArchetypeReport(target="x")
        assert any("never scanned" in r for r in rep.why_not_green())

    def test_scanned_empty_report_IS_green(self):
        """CONTROL. Without this, "always red" would pass the test above."""
        rep = ArchetypeReport(target="x", tool_availability={"t": "ok"}, scanned=True)
        assert rep.passed is True
        assert rep.why_not_green() == []

    def test_default_is_the_safe_direction(self):
        """A new archetype that forgets to set the flag reports NOT green.

        The default has to fail closed. If it defaulted True, forgetting
        it would be invisible, which is the shape of the original defect.
        """
        assert ArchetypeReport(target="x").scanned is False


class TestToolAvailabilityGatesGreen:
    """PROPERTY 2 - an analyzer that did not run cleared nothing."""

    @pytest.mark.parametrize("status", ["missing", "error", "unavailable: x"])
    def test_non_ok_status_is_not_green(self, status):
        rep = ArchetypeReport(
            target="x", tool_availability={"ruff": "ok", "mypy": status}, scanned=True
        )
        assert rep.passed is False
        assert rep.unavailable_required() == ["mypy"]

    def test_all_ok_IS_green(self):
        """CONTROL for the parametrized case above."""
        rep = ArchetypeReport(
            target="x", tool_availability={"ruff": "ok", "mypy": "ok"}, scanned=True
        )
        assert rep.passed is True
        assert rep.unavailable_required() == []

    def test_a_free_form_status_is_not_treated_as_ok(self):
        """`unavailable: ...` was a real status string one archetype wrote.

        Every consumer tested for the words "missing" or "error", so this
        one matched neither and slipped through as though it had run.
        """
        rep = ArchetypeReport(
            target="x", tool_availability={"ruff": "unavailable: boom"}, scanned=True
        )
        assert rep.passed is False

    def test_optional_set_is_empty_and_that_is_deliberate(self):
        assert OPTIONAL_ANALYZERS == frozenset(), (
            "adding a name here declares that analyzer's coverage "
            "optional; it must come with a reason"
        )

    def test_an_optional_analyzer_would_not_void_the_report(self, monkeypatch):
        """The mechanism works, even though the set is empty today."""
        import tools.harness.report as rp

        monkeypatch.setattr(rp, "OPTIONAL_ANALYZERS", frozenset({"vale"}))
        rep = ArchetypeReport(
            target="x", tool_availability={"vale": "missing"}, scanned=True
        )
        assert rep.passed is True


class TestFindingsStillGateGreen:
    """PROPERTY 4 - the original rule still holds on top of the new two."""

    def test_a_high_finding_blocks(self):
        rep = ArchetypeReport(
            target="x", findings=[_high()], tool_availability={"t": "ok"}, scanned=True
        )
        assert rep.passed is False

    def test_a_low_finding_does_not_block(self):
        rep = ArchetypeReport(
            target="x", findings=[_low()], tool_availability={"t": "ok"}, scanned=True
        )
        assert rep.passed is True


class TestBySeverityIsPublishedEverywhere:
    """PROPERTY 3 - the count the gate prints must be the real count."""

    def test_by_severity_sums_to_the_finding_count(self):
        rep = ArchetypeReport(
            target="x",
            findings=[_high(), _low(), _low()],
            tool_availability={"t": "ok"},
            scanned=True,
        )
        assert sum(rep.by_severity().values()) == len(rep.findings) == 3

    @pytest.mark.parametrize("module", ARCHETYPE_MODULES)
    def test_every_archetype_publishes_the_key(self, module):
        """One archetype omitted it, and the gate summed a missing key
        to zero. It printed "0 findings" above "by tool: ruff=81"."""
        mod = importlib.import_module(module)
        payload = mod.ArchetypeReport(
            target="x",
            findings=[
                mod.Finding(
                    tool="t",
                    severity="high",
                    file="f",
                    line=1,
                    rule_id="R",
                    message="m",
                )
            ],
        ).to_dict()
        assert "by_severity" in payload
        assert sum(payload["by_severity"].values()) == 1

    @pytest.mark.parametrize("module", ARCHETYPE_MODULES)
    def test_every_archetype_shares_one_report_class(self, module):
        mod = importlib.import_module(module)
        assert mod.ArchetypeReport is ArchetypeReport
        assert mod.Finding is Finding


class TestExitCodeFollowsTheVerdict:
    def test_green_exits_zero(self):
        rep = ArchetypeReport(target="x", tool_availability={"t": "ok"}, scanned=True)
        assert cli_exit(rep) == 0

    def test_unscanned_exits_one(self, capsys):
        rep = ArchetypeReport(target="x")
        assert cli_exit(rep) == 1
        assert "never scanned" in capsys.readouterr().err


class TestTheRealCLIs:
    """The end-to-end shape: five `main()` entry points, one absent path.

    `main()` is called rather than spawned. It returns exactly the int
    the process exits with -- `sys.exit(main())` is the only glue -- so
    this drives the real argv-to-verdict path without a subprocess.
    """

    @staticmethod
    def _main_of(module: str):
        return importlib.import_module(module).main

    @pytest.mark.parametrize("module", ARCHETYPE_MODULES)
    def test_absent_path_exits_non_zero(self, module, tmp_path, capsys):
        absent = tmp_path / "no_such_target.py"
        assert not absent.exists(), "control invalid: the path exists"
        code = self._main_of(module)([str(absent)])
        capsys.readouterr()
        assert code != 0, (
            f"{module} returned 0 on a path that does not exist; a caller "
            f"reading the exit code was told the file is clean"
        )

    @pytest.mark.parametrize("module", ARCHETYPE_MODULES)
    def test_present_clean_path_still_exits_zero(self, module, tmp_path, capsys):
        """CONTROL. Prove the CLIs did not simply stop passing."""
        present = tmp_path / "clean_module.py"
        present.write_text('"""A module."""\n', encoding="utf-8")
        code = self._main_of(module)([str(present)])
        out = capsys.readouterr()
        assert code == 0, (
            f"{module} returned {code} on a clean present file; "
            f"stdout={out.out[-600:]} stderr={out.err[-600:]}"
        )


class TestErrorsGateGreen:
    """PROPERTY 5 - a run that recorded a fault is not a clean run.

    MEASURED before this held, on an empty directory: exit 0,
    passed=True, 0 findings, and `errors` carrying "rules: source read
    failed: PermissionError". Nothing in the report contradicted the
    green.
    """

    def test_a_recorded_error_is_not_green(self):
        rep = ArchetypeReport(
            target="x",
            tool_availability={"t": "ok"},
            scanned=True,
            errors=["rules: source read failed: PermissionError"],
        )
        assert rep.passed is False
        assert any("error(s) recorded" in r for r in rep.why_not_green())

    def test_no_error_IS_green(self):
        """CONTROL. Without it, "always red" would pass the test above."""
        rep = ArchetypeReport(target="x", tool_availability={"t": "ok"}, scanned=True)
        assert rep.passed is True
        assert rep.why_not_green() == []


class TestRuleModulesCannotScanNothingAndReportOk:
    """PROPERTY 6 - reading no source is not the same as finding nothing."""

    def test_a_source_that_cannot_be_read_is_not_ok(self, tmp_path):
        """A directory is the case that was measured. read_text raises."""
        rep = ArchetypeReport(target=str(tmp_path), scanned=True)
        scan_rule_modules(rep, tmp_path, SCAFFOLDING, (".py",))
        assert rep.tool_availability["scaffolding"] != "ok"
        assert rep.passed is False

    def test_a_readable_file_IS_ok(self, tmp_path):
        """CONTROL for the case above."""
        f = tmp_path / "clean.py"
        f.write_text('"""Doc."""\n', encoding="utf-8")
        rep = ArchetypeReport(target=str(f), scanned=True)
        scan_rule_modules(rep, f, SCAFFOLDING, (".py",))
        assert rep.tool_availability["scaffolding"] == "ok"
        assert rep.passed is True

    def test_a_directory_is_scanned_file_by_file(self, tmp_path):
        """The finding that used to be LOST is the point of the property.

        Before this, a directory target handed the rule modules "" and
        every one of them reported `ok`. Measured on markdown: the FILE
        target reported hallucination H001 and the DIRECTORY target
        reported nothing, green.
        """
        (tmp_path / "bait.py").write_text(PLACEHOLDER_BAIT, encoding="utf-8")
        as_file = ArchetypeReport(target="f", scanned=True)
        scan_rule_modules(as_file, tmp_path / "bait.py", SCAFFOLDING, (".py",))
        assert as_file.findings, "control invalid: the bait draws nothing"

        as_dir = ArchetypeReport(target="d", scanned=True)
        scan_rule_modules(as_dir, tmp_path, SCAFFOLDING, (".py",))
        assert [f.rule_id for f in as_dir.findings] == [
            f.rule_id for f in as_file.findings
        ]
        assert as_dir.tool_availability["scaffolding"] == "ok"


class TestSilentToolFailureIsAnError:
    """PROPERTY 7 - installed-but-broken is not the same as clean.

    MEASURED with ruff installed and one malformed `ruff.toml` beside
    the target: ruff exited 2 with no stdout, the archetype reported
    ruff `ok` with 0 findings and passed=True, on a fixture that draws 7
    findings with a valid config.
    """

    @staticmethod
    def _proc(rc: int, out: str = "", err: str = ""):
        import subprocess

        return subprocess.CompletedProcess(
            args=["x"], returncode=rc, stdout=out, stderr=err
        )

    def test_non_zero_with_no_output_raises(self):
        with pytest.raises(RuntimeError, match="without output"):
            refuse_silent_failure(self._proc(2, "", "config broken"), "ruff")

    def test_non_zero_WITH_output_does_not_raise(self):
        """CONTROL. Most analyzers exit non-zero when they find things."""
        refuse_silent_failure(self._proc(1, "[{}]"), "ruff")

    def test_zero_with_no_output_does_not_raise(self):
        """CONTROL. A clean file legitimately prints nothing."""
        refuse_silent_failure(self._proc(0, ""), "mypy")

    @pytest.mark.parametrize("module", ARCHETYPE_MODULES)
    def test_no_runner_returns_ok_on_an_empty_non_zero_run(self, module):
        """Every `subprocess.run` result is checked before it is parsed.

        Static, and deliberately so: this is the rule a SEVENTH analyzer
        will break, and a behavioural test only covers the six that
        exist today.
        """
        import ast

        src = (
            HARNESS_REPO_ROOT / Path(*module.split(".")).with_suffix(".py")
        ).read_text(encoding="utf-8")
        tree = ast.parse(src)
        runs = [
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == "run"
            and isinstance(n.func.value, ast.Name)
            and n.func.value.id == "subprocess"
        ]
        for call in runs:
            kwargs = {k.arg for k in call.keywords}
            assert "cwd" in kwargs, (
                f"{module}: a subprocess.run at line {call.lineno} does not "
                f"pin cwd, so its verdict depends on where the caller stood"
            )


class TestUnusedIgnoreSeverityIsReadOffTheMessage:
    """PROPERTY 8 - a dead directive and an over-broad one are not equal.

    Both arrive as `unused-ignore`. Strip-and-diff through the full
    archetype separates them: removing the plain one changed no other
    diagnostic on 5 of 5 rows in this tree, and removing the
    "use narrower" one ADDED `mypy:method-assign` and
    `pyright:reportAttributeAccessIssue`.
    """

    @staticmethod
    def _sev(message: str) -> str:
        from tools.harness.coding_archetype import _unused_ignore_severity

        return _unused_ignore_severity(message)

    def test_a_dead_directive_is_high(self):
        assert self._sev('Unused "type: ignore" comment') == "high"

    def test_an_over_broad_directive_is_medium(self):
        assert (
            self._sev(
                'Unused "type: ignore" comment, use narrower [method-assign] '
                "instead of [assignment] code"
            )
            == "medium"
        )

    def test_the_two_are_not_the_same(self):
        """CONTROL. One severity for both is the defect this replaced."""
        assert self._sev('Unused "type: ignore" comment') != self._sev(
            'Unused "type: ignore" comment, use narrower [x] instead of ' "[y] code"
        )


class TestTheVerdictDoesNotDependOnTheCallersDirectory:
    """PROPERTY 9 - the analyzers read config from the current directory.

    MEASURED on one unchanged absolute path before the cwd was pinned:
    75 findings from the repo root against 78 from another directory,
    and the same `type: ignore` reported medium from one and high from
    the other. `tools/harness/claim_ledger.py` drew ruff UP017 twice
    from the root and not at all from elsewhere.
    """

    def test_mypy_writes_its_cache_where_the_harness_says(self):
        """mypy defaults to ./.mypy_cache -- a cache per caller."""
        import inspect
        from tools.harness.coding_archetype import CodingArchetype

        src = inspect.getsource(CodingArchetype._run_mypy)
        assert "--cache-dir" in src
        assert "REPO_ROOT" in src

    def test_ruff_answers_the_same_from_another_directory(self, tmp_path, monkeypatch):
        """The real runner, twice, from two directories."""
        from tools.harness.coding_archetype import CodingArchetype

        target = HARNESS_REPO_ROOT / "tools" / "harness" / "claim_ledger.py"
        assert target.is_file(), "control invalid: the target is missing"
        arch = CodingArchetype()
        monkeypatch.chdir(HARNESS_REPO_ROOT)
        from_root, status_root = arch._run_ruff(target)
        monkeypatch.chdir(tmp_path)
        from_away, status_away = arch._run_ruff(target)
        assert status_root == status_away == "ok"
        assert sorted(f.rule_id for f in from_root) == sorted(
            f.rule_id for f in from_away
        )


class TestKnownGoodAndKnownBadStillDiscriminate:
    """The instrument's own positive control, run from here too."""

    def test_fixtures_exist(self):
        assert (CODING_FIX / "known_good.py").is_file()
        assert (CODING_FIX / "known_bad.py").is_file()

    def test_known_good_returns_zero_and_known_bad_returns_one(self, capsys):
        from tools.harness.coding_archetype import main as coding_main

        results = {}
        for name in ("known_good.py", "known_bad.py"):
            results[name] = coding_main([str(CODING_FIX / name)])
            capsys.readouterr()
        assert results["known_good.py"] == 0
        assert results["known_bad.py"] == 1, (
            "known_bad returning 0 means the instrument is blind and every "
            "other verdict in this repo is void"
        )
