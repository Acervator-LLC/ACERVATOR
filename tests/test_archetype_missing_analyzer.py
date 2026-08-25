"""An absent analyzer must report `missing`, never `ok` — C43 step 5.

The defect: four of the six analyzers are invoked as `python -m <tool>`
(ruff, mypy, bandit, vulture). When the module is absent that does NOT
raise FileNotFoundError — the interpreter writes "No module named X" to
stderr, exits non-zero, and leaves stdout EMPTY. Every one of those
runners then hits

    if not proc.stdout.strip():
        return findings, "ok"

and reports `ok` with zero findings, which is byte-identical to "the
analyzer ran and the file is clean". The `except FileNotFoundError`
guard only catches the two bare-executable runners (pyright, semgrep).

Why it matters: `check_release_readiness._run_archetype_selfcheck`
treats a `passed=True` report as evidence. Uninstall ruff and the gate
still goes green, having checked nothing. This is not hypothetical —
every archetype invocation in this session reported `tools missing:
vale` and passed regardless.

These tests follow M5: verify by FORCING the failure. All four
analyzers are installed on this machine, so the missing branch is
unreachable without simulating absence.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dev_harness.harness.coding_archetype import CodingArchetype

MODULE_INVOKED = ["ruff", "mypy", "bandit", "vulture"]


@pytest.fixture
def sample_py(tmp_path):
    p = tmp_path / "sample.py"
    p.write_text("x = 1\n", encoding="utf-8")
    return p


def _absent(tool: str, real_run):
    """subprocess.run replacement that makes one tool look uninstalled."""

    def fake(cmd, *a, **kw):
        if isinstance(cmd, (list, tuple)) and tool in [str(c) for c in cmd]:
            return subprocess.CompletedProcess(
                cmd,
                returncode=1,
                stdout="",
                stderr=f"{sys.executable}: No module named {tool}\n",
            )
        return real_run(cmd, *a, **kw)

    return fake


@pytest.mark.parametrize("tool", MODULE_INVOKED)
def test_absent_module_analyzer_reports_missing(tool, sample_py, monkeypatch):
    real_run = subprocess.run
    monkeypatch.setattr(subprocess, "run", _absent(tool, real_run))
    report = CodingArchetype().review(sample_py)
    assert report.tool_availability.get(tool) == "missing", (
        f"{tool} absent but reported "
        f"{report.tool_availability.get(tool)!r}; an uninstalled analyzer "
        f"that reports 'ok' lets the release gate pass having checked "
        f"nothing"
    )


@pytest.mark.parametrize("tool", MODULE_INVOKED)
def test_absent_analyzer_is_named_in_falsification(tool, sample_py, monkeypatch):
    """The report must say which analyzer did not run."""
    real_run = subprocess.run
    monkeypatch.setattr(subprocess, "run", _absent(tool, real_run))
    report = CodingArchetype().review(sample_py)
    assert tool in report.falsification


class TestGUIArchetype:
    """gui_archetype carried the identical defect in two runners."""

    @pytest.mark.parametrize("tool", ["ruff", "bandit"])
    def test_absent_module_reports_missing(self, tool, sample_py, monkeypatch):
        from dev_harness.harness.gui_archetype import GUIArchetype

        real_run = subprocess.run
        monkeypatch.setattr(subprocess, "run", _absent(tool, real_run))
        report = GUIArchetype().review(sample_py)
        assert report.tool_availability.get(tool) == "missing"


class TestDocsArchetype:
    @pytest.fixture
    def sample_md(self, tmp_path):
        p = tmp_path / "sample.md"
        p.write_text("# Title\n\nSome prose here.\n", encoding="utf-8")
        return p

    def test_absent_proselint_reports_missing(self, sample_md, monkeypatch):
        from dev_harness.harness.docs_archetype import DocsArchetype

        real_run = subprocess.run
        monkeypatch.setattr(subprocess, "run", _absent("proselint", real_run))
        report = DocsArchetype().review(sample_md)
        assert report.tool_availability.get("proselint") == "missing"

    def test_vale_runtime_error_is_not_reported_as_ok(self, sample_md, monkeypatch):
        """vale writes runtime errors to STDERR with an EMPTY stdout.

        Measured with vale 3.17.1 and no .vale.ini: rc=2, stdout empty,
        stderr carrying {"Code":"E100", ...}. The archetype reported
        vale:'ok' with 0 findings, so an installed-but-unconfigured vale
        was worse than an absent one.
        """
        from dev_harness.harness.docs_archetype import DocsArchetype

        e100 = (
            '{"Line":0,"Path":"","Text":"E100 [.vale.ini not found] '
            'Runtime error\\n\\nno config file found","Code":"E100"}'
        )
        real_run = subprocess.run

        def fake(cmd, *a, **kw):
            # SUBSTRING, not equality. `_run_vale` used to spawn the
            # bare name "vale" while holding the absolute path that
            # `shutil.which` had just resolved; it now spawns that
            # path, so argv[0] reads like C:/.../vale.EXE. An
            # equality match would stop matching and this test would
            # pass by never simulating the failure at all.
            if isinstance(cmd, (list, tuple)) and any(
                "vale" in str(c).lower() for c in cmd
            ):
                return subprocess.CompletedProcess(
                    cmd, returncode=2, stdout="", stderr=e100
                )
            return real_run(cmd, *a, **kw)

        monkeypatch.setattr(subprocess, "run", fake)
        report = DocsArchetype().review(sample_md)
        assert (
            report.tool_availability.get("vale") == "error"
        ), "a vale runtime failure must not be reported as a clean run"
        assert any("vale" in e for e in report.errors)
        assert report.passed is False, (
            "an analyzer that errored did not clear anything, so the "
            "report it appears in must not be green"
        )

    def test_vale_spawns_the_path_it_resolved(self, sample_md, monkeypatch):
        """`shutil.which` and `subprocess.run` must agree.

        The resolved absolute path was computed into `vale_bin` and
        thrown away; the spawn passed the bare name and made the
        operating system search PATH a second time. `which` proved
        one binary existed and the spawn could run a different one.
        """
        import shutil

        from dev_harness.harness.docs_archetype import DocsArchetype

        resolved = shutil.which("vale")
        if resolved is None:
            pytest.skip("vale not installed on this machine")
        seen = []
        real_run = subprocess.run

        def record(cmd, *a, **kw):
            if isinstance(cmd, (list, tuple)) and cmd:
                seen.append(str(cmd[0]))
            return real_run(cmd, *a, **kw)

        monkeypatch.setattr(subprocess, "run", record)
        DocsArchetype().review(sample_md)
        vale_calls = [c for c in seen if "vale" in c.lower()]
        assert vale_calls, "vale was never spawned"
        for argv0 in vale_calls:
            assert argv0 == resolved, (
                f"vale spawned as {argv0!r}, not the path shutil.which "
                f"resolved ({resolved!r}); PATH is searched twice and "
                f"the two lookups can disagree"
            )


def test_all_analyzers_present_is_still_ok(sample_py):
    """Positive control: without simulated absence nothing is 'missing'.

    Guards against a fix that marks everything missing unconditionally.
    """
    report = CodingArchetype().review(sample_py)
    missing = [t for t, s in report.tool_availability.items() if s == "missing"]
    assert not missing, (
        f"expected all analyzers installed on this machine, got " f"missing={missing}"
    )
