"""Pins for the release-readiness gate — v3.24.34 (cascade C43).

Replaces the pre-2026-07-25 archived pin, which could not run: it
imported six helpers from `tools.check_release_readiness`, and the tool
now lives at `dev_harness.harness.check_release_readiness` and defines only
one of them. Full classification of every archived failure is at
docs/audits/2026-08-05_C43_archived_pin_classification.md.

What these pin, and why each exists:

  * The gate cannot print `[OK] Release-ready` or write a green sidecar
    when a check was skipped. Before v3.24.34 `--no-pytest
    --no-archetypes --no-claims` left `failures` empty and printed
    "[OK] Release-ready (vX.Y.Z, 0 tests)". Observed in the wild
    2026-08-05: a `tests: 0` green sidecar sat in the tree for 46
    minutes, left by a skipped run.
  * A green pytest run that collected nothing is not evidence.
  * The sidecar records WHICH checks ran, so a consumer can tell a full
    run from a skipped one. They were previously indistinguishable.

EVERY test here isolates SIDECAR_PATH onto tmp_path. `main()` calls
`_remove_sidecar()` on failure, so an unisolated test would delete the
operator's real sidecar as a side effect.
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
    monkeypatch.setattr(crr, "_run_claim_ledger_check",
                        lambda: (True, "no open claims"))


class TestVersionRead:
    def test_reads_version_from_src_init(self):
        assert crr._read_version() != "unknown"

    def test_matches_the_package_dunder(self):
        import src
        assert crr._read_version() == src.__version__


class TestSkippedChecksCannotBeGreen:
    """The defect this cascade exists to close."""

    @pytest.mark.parametrize("flags", [
        ["--no-pytest"],
        ["--no-archetypes"],
        ["--no-claims"],
        ["--no-pytest", "--no-archetypes", "--no-claims"],
    ])
    def test_any_skip_flag_refuses_to_declare_ready(
            self, flags, capsys, _isolate_sidecar, _all_checks_pass):
        rc = crr.main(flags)
        out = capsys.readouterr().out
        assert rc != 0, f"{flags} produced a zero exit"
        assert "[OK] Release-ready" not in out
        assert "skipped" in out
        assert not _isolate_sidecar.exists(), (
            f"{flags} wrote a sidecar; a skipped run must write none")

    def test_full_run_is_green_and_writes_sidecar(
            self, capsys, _isolate_sidecar, _all_checks_pass):
        rc = crr.main([])
        out = capsys.readouterr().out
        assert rc == 0, out
        assert "[OK] Release-ready" in out
        assert _isolate_sidecar.exists()


class TestSidecarContents:
    def test_sidecar_records_which_checks_ran(
            self, _isolate_sidecar, _all_checks_pass):
        crr.main([])
        data = json.loads(_isolate_sidecar.read_text(encoding="utf-8"))
        assert data["checks_run"] == {
            "pytest": "ran", "archetypes": "ran", "claims": "ran"}
        assert data["tests"] == 1105
        assert data["version"] == crr._read_version()

    def test_sidecar_timestamp_is_iso_and_parseable(
            self, _isolate_sidecar, _all_checks_pass):
        from datetime import datetime
        crr.main([])
        data = json.loads(_isolate_sidecar.read_text(encoding="utf-8"))
        # The hook parses this with fromisoformat after stripping Z.
        datetime.fromisoformat(data["timestamp"].replace("Z", "+00:00"))


class TestZeroCollectedTests:
    def test_green_pytest_with_zero_tests_is_a_failure(
            self, capsys, monkeypatch, _isolate_sidecar):
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
    """NF-133 / finding G1.

    The gate never opens main.py -- `grep -n 'main\\.py' ` against the
    tool returns nothing -- so nothing has ever checked its version
    strings. Measured at build v3.24.32: the boot log line and the Qt
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
        bare = [(n.lineno, n.value) for n in ast.walk(tree)
                if isinstance(n, ast.Constant) and isinstance(n.value, str)
                and re.fullmatch(self._VERSION_RE, n.value)]
        # Zero bare literals is the correct end state, not a failure:
        # main() now binds `from src import __version__`. Any literal
        # that reappears must at least agree with the package.
        mismatched = [(ln, v) for ln, v in bare if v != src.__version__]
        assert not mismatched, (
            f"main.py version literal(s) disagree with "
            f"src.__version__=={src.__version__}: {mismatched}")

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
            for n in ast.walk(tree))
        assert imports_version, (
            "main.py no longer imports __version__ from src; its version "
            "strings are hardcoded again")

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
            if not (isinstance(n, ast.Constant)
                    and isinstance(n.value, str)):
                continue
            for found in branded.findall(n.value):
                if found != src.__version__:
                    bad.append((n.lineno, n.value.strip()[:60], found))
        assert not bad, (
            f"main.py brands itself with a stale version while "
            f"src.__version__=={src.__version__}: {bad}")


class TestFailurePathsRemoveSidecar:
    def test_pytest_failure_removes_a_stale_green_sidecar(
            self, monkeypatch, _isolate_sidecar):
        _isolate_sidecar.write_text('{"version": "0.0.0"}', encoding="utf-8")
        monkeypatch.setattr(crr, "_run_pytest", lambda: (False, 3, "boom"))
        monkeypatch.setattr(crr, "_run_archetype_selfcheck", lambda: (True, [], []))
        monkeypatch.setattr(crr, "_run_claim_ledger_check", lambda: (True, ""))
        assert crr.main([]) != 0
        assert not _isolate_sidecar.exists()

    def test_archetype_failure_is_reported(
            self, capsys, monkeypatch, _isolate_sidecar):
        monkeypatch.setattr(crr, "_run_pytest", lambda: (True, 1105, ""))
        monkeypatch.setattr(crr, "_run_archetype_selfcheck",
                            lambda: (False, ["coding: ruff missing"], []))
        monkeypatch.setattr(crr, "_run_claim_ledger_check", lambda: (True, ""))
        assert crr.main([]) != 0
        assert "ruff missing" in capsys.readouterr().out


class TestRepoWideVersionLiterals:
    """Issue #70. One version, one name.

    `TestMainPyVersionLiterals` above proved the pattern on ONE file.
    Measured at build v3.25.8, these sources disagreed with
    `src.__version__ == "3.25.8"` at the same time:

      * pyproject.toml            version = "1.0.0", name
                                  "quantum-auto-trader"
      * ver.txt                   3.25.5 -- zero consumers, now deleted
      * README.md                 "Current version: 3.15.94"
      * splash_screen.py:170      "3.9.0"
      * investor_screen.py:289    "3.7.0"
      * generate_essay_ja.py:43   "3.1.98"
      * generate_essay_ja.py:78   output filename stamped v3.7.0

    Nothing compared any of them to the package, so every one rotted
    quietly. The repo already SHIPS a drift detector --
    src/core/version_sweep.py check_version_consistency -- and a search
    of the tree finds no caller for it. An instrument nobody runs
    measures nothing. These tests live in the suite, which does run.

    The rule they pin: a file either imports `__version__` or states a
    value equal to it. There is no third option.
    """

    _SEMVER = r"\d+\.\d+\.\d+"

    # Scripts that show or stamp the build version. Each carried a stale
    # literal before issue #70.
    _VERSION_CARRYING_SCRIPTS = (
        "splash_screen.py",
        "investor_screen.py",
        "generate_essay_ja.py",
    )

    @staticmethod
    def _parse(name):
        import ast
        return ast.parse((REPO_ROOT / name).read_text(encoding="utf-8"))

    @classmethod
    def _frozen_content_constants(cls, tree):
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
            f"src.__version__=={src.__version__}: {mismatched}")

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
            for n in ast.walk(tree)), (
            f"{script} no longer imports __version__ from src; its "
            f"version strings are hardcoded again")

    def test_the_frozen_content_marker_still_warns(self):
        """Positive control for the `*_FROZEN_AT` exemption.

        The exemption is safe only while the frozen value announces
        itself at runtime. If the warning goes, the exemption becomes a
        place to park stale versions unseen.
        """
        source = (REPO_ROOT / "generate_essay_ja.py").read_text(
            encoding="utf-8")
        assert "_CONTENT_VERSION_FROZEN_AT" in source
        assert "warnings.warn" in source, (
            "generate_essay_ja.py freezes a content version but no longer "
            "warns when it differs from the running build")

    def test_pyproject_does_not_restate_the_version(self):
        import tomllib
        data = tomllib.loads(
            (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        project = data["project"]
        assert "version" not in project, (
            f"pyproject.toml hardcodes version={project['version']!r}; it "
            f"must stay dynamic so it cannot disagree with src.__version__")
        assert "version" in project.get("dynamic", []), (
            "pyproject.toml declares neither a static nor a dynamic version")
        attr = data["tool"]["setuptools"]["dynamic"]["version"]["attr"]
        assert attr == "src.__version__", (
            f"pyproject.toml derives its version from {attr!r}, not from "
            f"src.__version__")

    def test_pyproject_version_resolves_to_the_package_version(self):
        """Read pyproject through setuptools, not by eye.

        test_pyproject_does_not_restate_the_version checks the wiring.
        This checks the wiring produces the right number. A fix that
        never reaches the value it claims to set is not a fix.
        """
        import src
        from setuptools.config.pyprojecttoml import read_configuration
        resolved = read_configuration(
            str(REPO_ROOT / "pyproject.toml"))["project"]["version"]
        assert resolved == src.__version__, (
            f"setuptools resolves the project version to {resolved!r} but "
            f"src.__version__ is {src.__version__!r}")

    def test_pyproject_names_the_product(self):
        import tomllib
        data = tomllib.loads(
            (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        assert data["project"]["name"] == "acervator", (
            f"pyproject.toml calls the project "
            f"{data['project']['name']!r}; the product is Acervator")
        scripts = list(data["project"]["scripts"])
        assert scripts == ["acervator"], (
            f"console scripts are {scripts}; the product is Acervator")

    def test_readme_states_no_version_of_its_own(self):
        """The README must point at the source, not copy it.

        Its hand-written number was 10 minor versions stale. Dated
        historical records such as "measured at v3.13.7" are
        deliberately not matched. They are true statements about a past
        run, and rewriting them to today's build would make them false.
        """
        import re
        text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        claims = re.findall(
            r"[Cc]urrent version:?\*{0,2}\s*:?\s*v?(" + self._SEMVER + ")",
            text)
        assert not claims, (
            f"README.md hand-writes a current version {claims}; name the "
            f"source file instead, so it cannot go stale")

    def test_no_scratch_version_file_at_repo_root(self):
        """ver.txt held `ASSIGN: __version__ = "3.25.5"`.

        A search of every file type found no reader for it anywhere in
        the tree. It was committed once, by accident, in `be6aa04
        initial upload`. Issue #70 deleted it. This stops it returning
        as a fifth disagreeing source.
        """
        assert not (REPO_ROOT / "ver.txt").exists(), (
            "ver.txt is back at the repo root; the version lives in "
            "src/__init__.py and nowhere else")
