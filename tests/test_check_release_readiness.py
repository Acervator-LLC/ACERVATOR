"""Pins for the release-readiness gate in ``dev_harness.harness.check_release_readiness``.

``main`` cannot print ``[OK] Release-ready`` or write a green sidecar when a
check was skipped, and a pytest run that collected nothing is not a pass. The
sidecar records which checks ran, so a consumer can tell a full run from a
skipped one. Every test here isolates ``SIDECAR_PATH`` onto ``tmp_path``,
because ``main`` calls ``_remove_sidecar`` on failure.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dev_harness.harness import check_release_readiness as crr  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_sidecar(tmp_path, monkeypatch):
    """Point the module's sidecar at tmp_path for every test.

    Without this, any test that drives main() down a failure path
    deletes the real .release_ready.json.
    """
    fake = tmp_path / ".release_ready.json"
    monkeypatch.setattr(crr, "SIDECAR_PATH", fake)
    return fake


@pytest.fixture
def _all_checks_pass(monkeypatch):
    """Make the three checks succeed without running them for real."""
    monkeypatch.setattr(crr, "_run_pytest", lambda: (True, 1105, ""))
    monkeypatch.setattr(crr, "_run_archetype_selfcheck", lambda: (True, [], []))
    monkeypatch.setattr(
        crr, "_run_claim_ledger_check", lambda: (True, "no open claims")
    )


class TestVersionRead:
    def test_reads_version_from_src_init(self):
        assert crr._read_version() != "unknown"

    def test_matches_the_package_dunder(self):
        import src

        assert crr._read_version() == src.__version__


class TestSkippedChecksCannotBeGreen:
    """The defect this cascade exists to close."""

    @pytest.mark.parametrize(
        "flags",
        [
            ["--no-pytest"],
            ["--no-archetypes"],
            ["--no-claims"],
            ["--no-pytest", "--no-archetypes", "--no-claims"],
        ],
    )
    def test_any_skip_flag_refuses_to_declare_ready(
        self, flags, capsys, _isolate_sidecar, _all_checks_pass
    ):
        rc = crr.main(flags)
        out = capsys.readouterr().out
        assert rc != 0, f"{flags} produced a zero exit"
        assert "[OK] Release-ready" not in out
        assert "skipped" in out
        assert (
            not _isolate_sidecar.exists()
        ), f"{flags} wrote a sidecar; a skipped run must write none"

    def test_full_run_is_green_and_writes_sidecar(
        self, capsys, _isolate_sidecar, _all_checks_pass
    ):
        rc = crr.main([])
        out = capsys.readouterr().out
        assert rc == 0, out
        assert "[OK] Release-ready" in out
        assert _isolate_sidecar.exists()


class TestSidecarContents:
    def test_sidecar_records_which_checks_ran(self, _isolate_sidecar, _all_checks_pass):
        crr.main([])
        data = json.loads(_isolate_sidecar.read_text(encoding="utf-8"))
        assert data["checks_run"] == {
            "pytest": "ran",
            "archetypes": "ran",
            "claims": "ran",
        }
        assert data["tests"] == 1105
        assert data["version"] == crr._read_version()

    def test_sidecar_timestamp_is_iso_and_parseable(
        self, _isolate_sidecar, _all_checks_pass
    ):
        from datetime import datetime

        crr.main([])
        data = json.loads(_isolate_sidecar.read_text(encoding="utf-8"))
        # The hook parses this with fromisoformat after stripping Z.
        datetime.fromisoformat(data["timestamp"].replace("Z", "+00:00"))


class TestZeroCollectedTests:
    def test_green_pytest_with_zero_tests_is_a_failure(
        self, capsys, monkeypatch, _isolate_sidecar
    ):
        """A suite that collected nothing cannot support a claim."""
        monkeypatch.setattr(crr, "_run_pytest", lambda: (True, 0, ""))
        monkeypatch.setattr(crr, "_run_archetype_selfcheck", lambda: (True, [], []))
        monkeypatch.setattr(crr, "_run_claim_ledger_check", lambda: (True, ""))
        rc = crr.main([])
        out = capsys.readouterr().out
        assert rc != 0
        assert "0 collected tests" in out
        assert not _isolate_sidecar.exists()


class TestMainPyVersionLiterals:
    """The gate never opens main.py, so nothing else checks its version
    strings. Measured once: the boot log line and the Qt
    application version both said "3.1.26", 23 minor versions stale.
    Every log the operator has collected carries the wrong build.

    The archived pin `test_init_and_main_versions_match` covered ONE of
    these (current_version) and was archived 2026-07-25 without being
    replaced. This widens it to every version literal in the file.

    AST is used rather than a text scan so that commented-out literals
    (main.py has one) are not counted -- comments are absent from the
    tree.
    """

    _VERSION_RE = r"\d+\.\d+\.\d+"

    def _main_py_source(self):
        return (REPO_ROOT / "main.py").read_text(encoding="utf-8")

    def test_bare_version_literals_match_package_version(self):
        import ast
        import re
        import src

        tree = ast.parse(self._main_py_source())
        bare = [
            (n.lineno, n.value)
            for n in ast.walk(tree)
            if isinstance(n, ast.Constant)
            and isinstance(n.value, str)
            and re.fullmatch(self._VERSION_RE, n.value)
        ]
        # Zero bare literals is the end state; one that reappears must match the package.
        mismatched = [(ln, v) for ln, v in bare if v != src.__version__]
        assert not mismatched, (
            f"main.py version literal(s) disagree with "
            f"src.__version__=={src.__version__}: {mismatched}"
        )

    def test_main_sources_its_version_from_the_package(self):
        """Positive control for the test above.

        Without this, deleting the `from src import __version__` bind
        and re-hardcoding every literal to today's value would leave
        both version tests green -- and the drift would restart.
        """
        import ast

        tree = ast.parse(self._main_py_source())
        imports_version = any(
            isinstance(n, ast.ImportFrom)
            and (n.module or "").split(".")[0] == "src"
            and any(a.name == "__version__" for a in n.names)
            for n in ast.walk(tree)
        )
        assert imports_version, (
            "main.py no longer imports __version__ from src; its version "
            "strings are hardcoded again"
        )

    def test_branded_version_strings_match_package_version(self):
        """Catches a version embedded in a longer string that claims to
        be Acervator's own, e.g. the boot log line at main.py:540.

        Deliberately narrow. A blanket scan for any semver in any string
        also flags `psutil>=5.9.0`, historical MEM references, and a
        commented-out literal inside a docstring -- none of which are
        claims about this build's identity. A pin with false positives
        is a pin that gets deleted.
        """
        import ast
        import re
        import src

        branded = re.compile(r"Acervator\s+v?(\d+\.\d+\.\d+)", re.IGNORECASE)
        tree = ast.parse(self._main_py_source())
        bad = []
        for n in ast.walk(tree):
            if not (isinstance(n, ast.Constant) and isinstance(n.value, str)):
                continue
            for found in branded.findall(n.value):
                if found != src.__version__:
                    bad.append((n.lineno, n.value.strip()[:60], found))
        assert not bad, (
            f"main.py brands itself with a stale version while "
            f"src.__version__=={src.__version__}: {bad}"
        )


class TestFailurePathsRemoveSidecar:
    def test_pytest_failure_removes_a_stale_green_sidecar(
        self, monkeypatch, _isolate_sidecar
    ):
        _isolate_sidecar.write_text('{"version": "0.0.0"}', encoding="utf-8")
        monkeypatch.setattr(crr, "_run_pytest", lambda: (False, 3, "boom"))
        monkeypatch.setattr(crr, "_run_archetype_selfcheck", lambda: (True, [], []))
        monkeypatch.setattr(crr, "_run_claim_ledger_check", lambda: (True, ""))
        assert crr.main([]) != 0
        assert not _isolate_sidecar.exists()

    def test_archetype_failure_is_reported(self, capsys, monkeypatch, _isolate_sidecar):
        monkeypatch.setattr(crr, "_run_pytest", lambda: (True, 1105, ""))
        monkeypatch.setattr(
            crr,
            "_run_archetype_selfcheck",
            lambda: (False, ["coding: ruff missing"], []),
        )
        monkeypatch.setattr(crr, "_run_claim_ledger_check", lambda: (True, ""))
        assert crr.main([]) != 0
        assert "ruff missing" in capsys.readouterr().out


class TestRepoWideVersionLiterals:
    """One version, one name.

    `TestMainPyVersionLiterals` above proved the pattern on ONE file.
    Measured once, these sources disagreed with `src.__version__` at the
    same time:

      * pyproject.toml, ver.txt, README.md, and the three scripts named
        in ``_VERSION_CARRYING_SCRIPTS``.

    ``src.core.version_sweep.check_version_consistency`` detects the same
    drift and has no caller, so these tests carry it instead.

    The rule they pin: a file either imports `__version__` or states a
    value equal to it. There is no third option.
    """

    _SEMVER = r"\d+\.\d+\.\d+"

    # Scripts that show or stamp the build version.
    _VERSION_CARRYING_SCRIPTS = (
        "splash_screen.py",
        "investor_screen.py",
        "generate_essay_ja.py",
    )

    @staticmethod
    def _parse(name):
        import ast

        return ast.parse((REPO_ROOT / name).read_text(encoding="utf-8"))

    @staticmethod
    def _frozen_content_constants(tree):
        """Return id() of every literal bound to a `*_FROZEN_AT` name.

        generate_essay_ja.py pins _CONTENT_VERSION_FROZEN_AT = "3.1.98".
        That is not a claim about THIS build. It records which English
        manual the Japanese body was translated from, and the file warns
        at import time when it differs from the running version.
        Rewriting it to the current version would delete a true
        statement and silence the warning.

        This is a stated rule, not a file-and-line allowlist. Exemption
        is earned by the naming convention, and
        test_the_frozen_content_marker_still_warns below stops the
        convention becoming a hiding place.
        """
        import ast

        exempt = set()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if any(n.endswith("_FROZEN_AT") for n in names):
                exempt.add(id(node.value))
        return exempt

    @pytest.mark.parametrize("script", _VERSION_CARRYING_SCRIPTS)
    def test_scripts_state_no_version_that_disagrees(self, script):
        import ast
        import re
        import src

        tree = self._parse(script)
        exempt = self._frozen_content_constants(tree)
        mismatched = [
            (n.lineno, n.value)
            for n in ast.walk(tree)
            if isinstance(n, ast.Constant)
            and isinstance(n.value, str)
            and re.fullmatch(self._SEMVER, n.value)
            and id(n) not in exempt
            and n.value != src.__version__
        ]
        assert not mismatched, (
            f"{script} states version literal(s) that disagree with "
            f"src.__version__=={src.__version__}: {mismatched}"
        )

    @pytest.mark.parametrize("script", _VERSION_CARRYING_SCRIPTS)
    def test_scripts_source_their_version_from_the_package(self, script):
        """Positive control for the test above.

        Without this, deleting every import and hardcoding today's value
        into all three files leaves the drift test green, and the drift
        restarts at the next release. This is the control
        TestMainPyVersionLiterals already uses for main.py.
        """
        import ast

        tree = self._parse(script)
        assert any(
            isinstance(n, ast.ImportFrom)
            and (n.module or "").split(".")[0] == "src"
            and any(a.name == "__version__" for a in n.names)
            for n in ast.walk(tree)
        ), (
            f"{script} no longer imports __version__ from src; its "
            f"version strings are hardcoded again"
        )

    def test_the_frozen_content_marker_still_warns(self):
        """Positive control for the `*_FROZEN_AT` exemption.

        The exemption is safe only while the frozen value announces
        itself at runtime. If the warning goes, the exemption becomes a
        place to park stale versions unseen.
        """
        source = (REPO_ROOT / "generate_essay_ja.py").read_text(encoding="utf-8")
        assert "_CONTENT_VERSION_FROZEN_AT" in source
        assert "warnings.warn" in source, (
            "generate_essay_ja.py freezes a content version but no longer "
            "warns when it differs from the running build"
        )

    def test_pyproject_does_not_restate_the_version(self):
        import tomllib

        data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        project = data["project"]
        assert "version" not in project, (
            f"pyproject.toml hardcodes version={project['version']!r}; it "
            f"must stay dynamic so it cannot disagree with src.__version__"
        )
        assert "version" in project.get(
            "dynamic", []
        ), "pyproject.toml declares neither a static nor a dynamic version"
        attr = data["tool"]["setuptools"]["dynamic"]["version"]["attr"]
        assert attr == "src.__version__", (
            f"pyproject.toml derives its version from {attr!r}, not from "
            f"src.__version__"
        )

    def test_pyproject_version_resolves_to_the_package_version(self):
        """Follow the declaration to the value it actually yields.

        test_pyproject_does_not_restate_the_version checks the wiring.
        This one walks it. A fix that never reaches the value it claims
        to set is not a fix, so the attr is resolved the way setuptools
        resolves it -- import the module named on the left of the last
        dot, then read the attribute named on the right.

        Resolving it here rather than calling
        setuptools.config.pyprojecttoml.read_configuration is
        deliberate: that module ships no type stubs, and adding a
        `type: ignore` to quiet the archetype would hide a real class of
        finding for the life of this file. Measured out of band at
        setuptools 83.0.0, read_configuration returns 3.25.8 for this
        pyproject, which agrees with the walk below.
        """
        import importlib
        import tomllib
        import src

        data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        attr = data["tool"]["setuptools"]["dynamic"]["version"]["attr"]
        module_name, _, attr_name = attr.rpartition(".")
        resolved = getattr(importlib.import_module(module_name), attr_name)
        assert resolved == src.__version__, (
            f"pyproject.toml resolves its version through {attr!r} to "
            f"{resolved!r}, but src.__version__ is {src.__version__!r}"
        )

    def test_pyproject_names_the_product(self):
        import tomllib

        data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        assert data["project"]["name"] == "acervator", (
            f"pyproject.toml calls the project "
            f"{data['project']['name']!r}; the product is Acervator"
        )
        scripts = list(data["project"]["scripts"])
        assert scripts == [
            "acervator"
        ], f"console scripts are {scripts}; the product is Acervator"

    def test_readme_states_no_version_of_its_own(self):
        """The README must point at the source, not copy it.

        A dated historical record of a past measurement is deliberately
        not matched, because rewriting one to today's build would make it
        false.
        """
        import re

        text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        claims = re.findall(
            r"[Cc]urrent version:?\*{0,2}\s*:?\s*v?(" + self._SEMVER + ")", text
        )
        assert not claims, (
            f"README.md hand-writes a current version {claims}; name the "
            f"source file instead, so it cannot go stale"
        )

    def test_no_scratch_version_file_at_repo_root(self):
        """ver.txt held `ASSIGN: __version__ = "3.25.5"`.

        No file in the tree read it, and it is deleted. This stops it
        returning as a fifth disagreeing source.
        """
        assert not (REPO_ROOT / "ver.txt").exists(), (
            "ver.txt is back at the repo root; the version lives in "
            "src/__init__.py and nowhere else"
        )
