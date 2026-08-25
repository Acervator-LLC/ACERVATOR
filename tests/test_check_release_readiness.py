"""Pins for the release-readiness gate — v3.24.34 (cascade C43).

Replaces the pre-2026-07-25 archived pin, which could not run: it
imported six helpers from `tools.check_release_readiness`, and the tool
now lives at `tools.harness.check_release_readiness` and defines only
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

from tools.harness import check_release_readiness as crr  # noqa: E402


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
        bare = [
            (n.lineno, n.value)
            for n in ast.walk(tree)
            if isinstance(n, ast.Constant)
            and isinstance(n.value, str)
            and re.fullmatch(self._VERSION_RE, n.value)
        ]
        # Zero bare literals is the correct end state, not a failure:
        # main() now binds `from src import __version__`. Any literal
        # that reappears must at least agree with the package.
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
