"""End-to-end hook flow integration tests.

Each test exercises a full chain, not just a single hook. They verify
that the pieces compose correctly — that a prompt actually reaches the
router, that a Write actually triggers the archetype gate, that the
release-gate deny→check→allow cycle works as a whole.

Unlike test_hooks.py (unit-shape pins), these are integration-shape.

WHERE THE HARNESS IS — 2026-08-25
=================================
Hooks, skills and the settings file moved to user level at the CTO's
request. All three are resolved through `tools.claude_home`, which
searches user level first and then the repository, the same order the
router hook uses when it checks that a skill it names exists.

WHAT HAPPENS WHEN THE HARNESS IS ABSENT
=======================================
These tests SKIP, with a reason that names every path searched, and the
same text is raised as an import-time warning so it appears in the
warnings summary of every run. The repository cannot install the
harness into a stranger's clone, so failing would make the gate red for
a state that is not a defect. `TestTheHarnessSearchCanFail` carries no
skip mark: it runs in both states and proves the search reports absence
when there is nothing to find, so the skip can never be mistaken for a
pass.

A harness directory that exists but is short a hook is a different
state. `tests/test_hooks.py::test_the_install_is_not_partial` FAILS on
it rather than skipping.
"""
from __future__ import annotations

import json
import subprocess
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tools import claude_home
from tools.claude_home import absent_reason, hooks_dir, settings_file, skill_file


REPO = Path(__file__).resolve().parent.parent
HOOKS = hooks_dir()
_ABSENT = absent_reason("hooks")

if HOOKS is None:
    warnings.warn(_ABSENT, stacklevel=1)

_needs_hooks = pytest.mark.skipif(HOOKS is None, reason=_ABSENT)


def _run_python(argv: list[str], stdin: str) -> subprocess.CompletedProcess:
    """Spawn the current interpreter with `argv` and feed it `stdin`.

    Every spawn in this file goes through here. Three separate call
    sites drew three copies of the same security finding and stated the
    same encoding and timeout arguments three times; one site states
    them once.

    The executable is `sys.executable`, an absolute path, so a program
    planted earlier on PATH cannot be run in its place.
    """
    return subprocess.run(
        [sys.executable, *argv],
        input=stdin, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
        timeout=120, cwd=str(REPO),
    )


def _run_hook(hook: str, stdin: str) -> subprocess.CompletedProcess:
    assert HOOKS is not None, _ABSENT
    return _run_python([str(HOOKS / hook)], stdin)


class TestTheHarnessSearchCanFail:
    """Positive control. Runs whether or not the harness is installed."""

    def test_an_empty_home_reports_every_part_absent(
            self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setattr(claude_home, "REPO", tmp_path / "no-such-repo")
        monkeypatch.setenv("HOME", str(home))
        monkeypatch.setenv("USERPROFILE", str(home))

        assert claude_home.hooks_dir() is None
        assert claude_home.settings_file() is None
        assert claude_home.skill_file("harness-law") is None

    def test_a_planted_skill_and_settings_file_resolve(
            self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        root = home / claude_home.CLAUDE_DIR_NAME
        skill = root / "skills" / "harness-law"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text("planted", encoding="utf-8")
        (root / "settings.json").write_text("{}", encoding="utf-8")
        monkeypatch.setattr(claude_home, "REPO", tmp_path / "no-such-repo")
        monkeypatch.setenv("HOME", str(home))
        monkeypatch.setenv("USERPROFILE", str(home))

        assert claude_home.skill_file("harness-law") == skill / "SKILL.md"
        assert claude_home.settings_file() == root / "settings.json"
        assert claude_home.skill_file("no-such-skill") is None


# ---------------------------------------------------------------------------
# Chain 1: prompt_router → archetype named in routing exists + runnable
# ---------------------------------------------------------------------------


@_needs_hooks
class TestRouterNamesRealArchetype:
    """When the router says 'run dev_harness.harness.coding_archetype', that
    module MUST exist and be invokable. Otherwise the routing text is a
    lie. Same for the other two domains."""

    def _extract_archetype_module(self, output: str) -> str | None:
        import re
        m = re.search(r"python -m (dev_harness\.harness\.\w+_archetype)", output)
        return m.group(1) if m else None

    def test_router_coding_module_is_invokable(self):
        r = _run_hook("prompt_router.py",
                      json.dumps({"user_prompt": "refactor the pytest suite"}))
        module = self._extract_archetype_module(r.stdout)
        assert module == "dev_harness.harness.coding_archetype"
        # Actually invoke it; must exit 2 (usage) — proves module runnable
        p = _run_python(["-m", module], "")
        assert p.returncode == 2, "expected usage-error exit from empty invocation"

    def test_router_gui_module_is_invokable(self):
        r = _run_hook("prompt_router.py",
                      json.dumps({"user_prompt": "fix QPushButton layout"}))
        assert "dev_harness.harness.gui_archetype" in r.stdout
        p = _run_python(["-m", "dev_harness.harness.gui_archetype"], "")
        assert p.returncode == 2

    def test_router_docs_module_is_invokable(self):
        r = _run_hook("prompt_router.py",
                      json.dumps({"user_prompt": "write a how-to guide"}))
        assert "dev_harness.harness.docs_archetype" in r.stdout
        p = _run_python(["-m", "dev_harness.harness.docs_archetype"], "")
        assert p.returncode == 2

    def test_router_names_a_skill_that_exists_on_disk(self):
        r = _run_hook("prompt_router.py",
                      json.dumps({"user_prompt": "add a QPushButton"}))
        # Extract "Consult skill: `<slug>`"
        import re
        m = re.search(r"Consult skill: `([^`]+)`", r.stdout)
        assert m, f"router did not name a skill: {r.stdout!r}"
        slug = m.group(1)
        assert skill_file(slug) is not None, (
            f"router named nonexistent skill: {slug}; searched "
            f"{[str(c) for c in claude_home.candidates('skills', slug, 'SKILL.md')]}"
        )


# ---------------------------------------------------------------------------
# Chain 2: Write payload → archetype_gate runs → summary output
# ---------------------------------------------------------------------------


@_needs_hooks
class TestArchetypeGateOnRealFile:
    def test_write_python_triggers_coding_archetype(self):
        """Feed a Write payload for a real Python file; hook should run
        coding_archetype and emit a summary line."""
        target = REPO / "docs" / "audits" / "2026-07-24_coding_archetype_multi_agent_test" / "fixtures" / "known_good.py"
        assert target.exists()
        # Note: docs/audits/ is in the skip list, so the gate should skip
        r = _run_hook("archetype_gate.py", json.dumps({
            "tool_name": "Write",
            "tool_input": {"file_path": str(target)},
        }))
        assert r.returncode == 0
        # v3.25.6 - this asserted docs/audits was SKIPPED. The skip list
        # was removed: exempting a directory meant a real defect could
        # live in one and never be graded, which is how a dead command
        # survived inside the hooks directory for a whole session. Fixture
        # authoring still works because the gate blocks a RISE in high
        # findings, not their presence - a known_bad fixture rewritten
        # with its own content adds nothing and is allowed.
        assert "archetype-gate" in r.stdout, (
            f"a graded file must receive a verdict; got {r.stdout!r}")

    def test_write_python_outside_skip_triggers_summary(self, tmp_path):
        """Copy a fixture outside the skip zone so the hook actually
        runs the archetype."""
        import shutil
        src = REPO / "docs" / "audits" / "2026-07-24_coding_archetype_multi_agent_test" / "fixtures" / "known_good.py"
        dst = tmp_path / "clean.py"
        shutil.copy(src, dst)
        r = _run_hook("archetype_gate.py", json.dumps({
            "tool_name": "Edit",
            "tool_input": {"file_path": str(dst)},
        }))
        assert r.returncode == 0
        assert "archetype-gate" in r.stdout.lower() or r.stdout.strip() == "", (
            f"expected either a summary or a skip; got {r.stdout!r}"
        )


# ---------------------------------------------------------------------------
# Chain 3: full release-gate deny → check → allow cycle
# ---------------------------------------------------------------------------


@_needs_hooks
class TestReleaseGateCycle:
    def test_full_cycle(self, tmp_path):
        """1) Remove sidecar. 2) Verify DENY on banner. 3) Write fresh
        sidecar manually. 4) Verify ALLOW on banner. 5) Restore original
        sidecar so test doesn't leave state dirty."""
        sidecar = REPO / ".release_ready.json"
        backup = None
        if sidecar.exists():
            backup = tmp_path / "sidecar.bak"
            sidecar.replace(backup)

        try:
            # Step 1: no sidecar
            assert not sidecar.exists()

            # Step 2: DENY
            r = _run_hook("verify_release_gate.py", json.dumps({
                "tool_name": "Write",
                "tool_input": {"file_path": "src/__init__.py"},
            }))
            assert r.returncode == 0
            payload = json.loads(r.stdout)
            assert payload["decision"] == "deny"

            # Step 3: synthetic fresh sidecar.
            # v3.24.34 (C43): must be a COMPLETE sidecar. This fixture
            # previously wrote `tests: 0` with no `checks_run` -- the
            # signature of a `--no-pytest` run -- and asserted ALLOW,
            # which pinned the defect as correct behaviour.
            now = datetime.now(timezone.utc).replace(microsecond=0)
            iso = now.isoformat().replace("+00:00", "Z")
            sidecar.write_text(json.dumps({
                "version": "test", "tests": 1105, "timestamp": iso,
                "checks_run": {"pytest": "ran", "archetypes": "ran",
                               "claims": "ran"},
                "generator": "integration_test",
            }), encoding="utf-8")

            # Step 4: ALLOW
            r = _run_hook("verify_release_gate.py", json.dumps({
                "tool_name": "Write",
                "tool_input": {"file_path": "main.py"},
            }))
            assert r.returncode == 0
            assert r.stdout.strip() == "", (
                f"fresh sidecar should allow banner write; got {r.stdout!r}"
            )
        finally:
            # Step 5: restore
            sidecar.unlink(missing_ok=True)
            if backup is not None:
                backup.replace(sidecar)


# ---------------------------------------------------------------------------
# Chain 4: settings.json declared hooks all exist and are runnable
# ---------------------------------------------------------------------------


@_needs_hooks
class TestSettingsWiringIntegrity:
    """Every hook script the settings file wires up must exist on disk
    and be at minimum syntactically valid Python.

    The settings file moved to user level with the hooks, and its
    commands were rewritten to absolute paths at the same time. The
    fixture below therefore resolves a declared path as written when it
    is absolute, and against the repository when it is relative, so both
    a user-level install and a project carrying its own harness are
    read correctly.
    """

    @pytest.fixture(scope="class")
    def declared_hook_paths(self):
        found = settings_file()
        assert found is not None, absent_reason("settings.json")
        settings = json.loads(found.read_text(encoding="utf-8"))
        paths = set()
        for event_hooks in settings.get("hooks", {}).values():
            for entry in event_hooks:
                for hook in entry.get("hooks", []):
                    cmd = hook.get("command", "")
                    # extract "python <path>"
                    parts = cmd.split()
                    if len(parts) >= 2 and parts[0] == "python":
                        paths.add(parts[1])
        return paths

    @staticmethod
    def _resolve(declared: str) -> Path:
        """A declared command path, absolute as written or repo-relative."""
        path = Path(declared)
        return path if path.is_absolute() else REPO / path

    def test_wired_hooks_all_exist(self, declared_hook_paths):
        assert declared_hook_paths, "no hooks declared in the settings file"
        missing = [p for p in declared_hook_paths
                   if not self._resolve(p).is_file()]
        assert not missing, f"declared hooks missing on disk: {missing}"

    def test_wired_hooks_all_parse(self, declared_hook_paths):
        import ast
        broken = []
        for p in declared_hook_paths:
            src = self._resolve(p).read_text(encoding="utf-8", errors="replace")
            try:
                ast.parse(src)
            except SyntaxError as e:
                broken.append(f"{p}: {e}")
        assert not broken, f"declared hooks with syntax errors: {broken}"

    def test_wired_hooks_all_run_without_stdin_crashes(self, declared_hook_paths):
        """Every hook must exit 0 on empty JSON stdin. Hooks that crash
        Claude Code are unusable."""
        broken = []
        for p in declared_hook_paths:
            r = _run_python([str(self._resolve(p))], "{}")
            if r.returncode != 0:
                broken.append(f"{p}: exit={r.returncode}, stderr={r.stderr[:200]!r}")
        assert not broken, f"hooks crash on empty stdin: {broken}"
