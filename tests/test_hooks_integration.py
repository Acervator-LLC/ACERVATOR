"""End-to-end hook flow integration tests.

Each test exercises a full chain, not just a single hook. They verify
that the pieces compose correctly — that a prompt actually reaches the
router, that a Write actually triggers the archetype gate, that the
release-gate deny→check→allow cycle works as a whole.

Unlike test_hooks.py (unit-shape pins), these are integration-shape.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
HOOKS = REPO / ".claude" / "hooks"


def _run_hook(hook: str, stdin: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(HOOKS / hook)],
        input=stdin,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        cwd=str(REPO),
    )


# ---------------------------------------------------------------------------
# Chain 1: prompt_router → archetype named in routing exists + runnable
# ---------------------------------------------------------------------------


class TestRouterNamesRealArchetype:
    """When the router says 'run tools.harness.coding_archetype', that
    module MUST exist and be invokable. Otherwise the routing text is a
    lie. Same for the other two domains."""

    def _extract_archetype_module(self, output: str) -> str | None:
        import re

        m = re.search(r"python -m (tools\.harness\.\w+_archetype)", output)
        return m.group(1) if m else None

    def test_router_coding_module_is_invokable(self):
        r = _run_hook(
            "prompt_router.py", json.dumps({"user_prompt": "refactor the pytest suite"})
        )
        module = self._extract_archetype_module(r.stdout)
        assert module == "tools.harness.coding_archetype"
        # Actually invoke -h; must exit 2 (usage) — proves module runnable
        p = subprocess.run(
            [sys.executable, "-m", module],
            capture_output=True,
            timeout=30,
            cwd=str(REPO),
        )
        assert p.returncode == 2, "expected usage-error exit from empty invocation"

    def test_router_gui_module_is_invokable(self):
        r = _run_hook(
            "prompt_router.py", json.dumps({"user_prompt": "fix QPushButton layout"})
        )
        assert "tools.harness.gui_archetype" in r.stdout
        p = subprocess.run(
            [sys.executable, "-m", "tools.harness.gui_archetype"],
            capture_output=True,
            timeout=30,
            cwd=str(REPO),
        )
        assert p.returncode == 2

    def test_router_docs_module_is_invokable(self):
        r = _run_hook(
            "prompt_router.py", json.dumps({"user_prompt": "write a how-to guide"})
        )
        assert "tools.harness.docs_archetype" in r.stdout
        p = subprocess.run(
            [sys.executable, "-m", "tools.harness.docs_archetype"],
            capture_output=True,
            timeout=30,
            cwd=str(REPO),
        )
        assert p.returncode == 2

    def test_router_names_a_skill_that_exists_on_disk(self):
        r = _run_hook(
            "prompt_router.py", json.dumps({"user_prompt": "add a QPushButton"})
        )
        # Extract "Consult skill: `<slug>`"
        import re

        m = re.search(r"Consult skill: `([^`]+)`", r.stdout)
        assert m, f"router did not name a skill: {r.stdout!r}"
        slug = m.group(1)
        assert (
            REPO / ".claude" / "skills" / slug / "SKILL.md"
        ).is_file(), f"router named nonexistent skill: {slug}"


# ---------------------------------------------------------------------------
# Chain 2: Write payload → archetype_gate runs → summary output
# ---------------------------------------------------------------------------


class TestArchetypeGateOnRealFile:
    def test_write_python_triggers_coding_archetype(self):
        """Feed a Write payload for a real Python file; hook should run
        coding_archetype and emit a summary line."""
        target = (
            REPO
            / "docs"
            / "audits"
            / "2026-07-24_coding_archetype_multi_agent_test"
            / "fixtures"
            / "known_good.py"
        )
        assert target.exists()
        # Note: docs/audits/ is in the skip list, so the gate should skip
        r = _run_hook(
            "archetype_gate.py",
            json.dumps(
                {
                    "tool_name": "Write",
                    "tool_input": {"file_path": str(target)},
                }
            ),
        )
        assert r.returncode == 0
        # v3.25.6 - this asserted docs/audits was SKIPPED. The skip list
        # was removed: exempting a directory meant a real defect could
        # live in one and never be graded, which is how a dead command
        # survived inside .claude/hooks for a whole session. Fixture
        # authoring still works because the gate blocks a RISE in high
        # findings, not their presence - a known_bad fixture rewritten
        # with its own content adds nothing and is allowed.
        assert (
            "archetype-gate" in r.stdout
        ), f"a graded file must receive a verdict; got {r.stdout!r}"

    def test_write_python_outside_skip_triggers_summary(self, tmp_path):
        """Copy a fixture outside the skip zone so the hook actually
        runs the archetype."""
        import shutil

        src = (
            REPO
            / "docs"
            / "audits"
            / "2026-07-24_coding_archetype_multi_agent_test"
            / "fixtures"
            / "known_good.py"
        )
        dst = tmp_path / "clean.py"
        shutil.copy(src, dst)
        r = _run_hook(
            "archetype_gate.py",
            json.dumps(
                {
                    "tool_name": "Edit",
                    "tool_input": {"file_path": str(dst)},
                }
            ),
        )
        assert r.returncode == 0
        assert (
            "archetype-gate" in r.stdout.lower() or r.stdout.strip() == ""
        ), f"expected either a summary or a skip; got {r.stdout!r}"


# ---------------------------------------------------------------------------
# Chain 3: full release-gate deny → check → allow cycle
# ---------------------------------------------------------------------------


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
            r = _run_hook(
                "verify_release_gate.py",
                json.dumps(
                    {
                        "tool_name": "Write",
                        "tool_input": {"file_path": "src/__init__.py"},
                    }
                ),
            )
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
            sidecar.write_text(
                json.dumps(
                    {
                        "version": "test",
                        "tests": 1105,
                        "timestamp": iso,
                        "checks_run": {
                            "pytest": "ran",
                            "archetypes": "ran",
                            "claims": "ran",
                        },
                        "generator": "integration_test",
                    }
                ),
                encoding="utf-8",
            )

            # Step 4: ALLOW
            r = _run_hook(
                "verify_release_gate.py",
                json.dumps(
                    {
                        "tool_name": "Write",
                        "tool_input": {"file_path": "main.py"},
                    }
                ),
            )
            assert r.returncode == 0
            assert (
                r.stdout.strip() == ""
            ), f"fresh sidecar should allow banner write; got {r.stdout!r}"
        finally:
            # Step 5: restore
            sidecar.unlink(missing_ok=True)
            if backup is not None:
                backup.replace(sidecar)


# ---------------------------------------------------------------------------
# Chain 4: settings.json declared hooks all exist and are runnable
# ---------------------------------------------------------------------------


class TestSettingsWiringIntegrity:
    """Every hook script referenced in .claude/settings.json must exist
    on disk and be at minimum syntactically valid Python."""

    @pytest.fixture(scope="class")
    def declared_hook_paths(self):
        settings = json.loads(
            (REPO / ".claude" / "settings.json").read_text(encoding="utf-8")
        )
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

    def test_wired_hooks_all_exist(self, declared_hook_paths):
        assert declared_hook_paths, "no hooks declared in settings.json"
        missing = [p for p in declared_hook_paths if not (REPO / p).is_file()]
        assert not missing, f"declared hooks missing on disk: {missing}"

    def test_wired_hooks_all_parse(self, declared_hook_paths):
        import ast

        broken = []
        for p in declared_hook_paths:
            src = (REPO / p).read_text(encoding="utf-8", errors="replace")
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
            r = subprocess.run(
                [sys.executable, str(REPO / p)],
                input="{}",
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
                cwd=str(REPO),
            )
            if r.returncode != 0:
                broken.append(f"{p}: exit={r.returncode}, stderr={r.stderr[:200]!r}")
        assert not broken, f"hooks crash on empty stdin: {broken}"
