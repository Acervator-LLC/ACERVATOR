"""Pin tests for .claude/hooks/*.py.

Each hook is exercised by subprocess with a synthetic stdin payload.
The tests verify:
  - prompt_router: routes correctly on domain keywords; silent on neutral
  - archetype_gate: picks correct archetype by file type + content;
    skips known-noise paths
  - verify_release_gate: gate + pass-through behaviors
  - session_stop_backstop: doesn't crash on no-git or clean-tree

None of the hooks may crash Claude Code — a hook that raises should still
exit 0 (silent fail-open). These tests pin that behavior.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parent.parent
HOOKS = REPO / ".claude" / "hooks"


def _run_hook(hook: str, stdin: str) -> subprocess.CompletedProcess:
    """Run a hook script with the given stdin, return CompletedProcess."""
    return subprocess.run(
        [sys.executable, str(HOOKS / hook)],
        input=stdin,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        cwd=str(REPO),
    )


# ---------------------------------------------------------------------------
# prompt_router.py
# ---------------------------------------------------------------------------


class TestPromptRouter:
    def test_neutral_prompt_still_carries_the_authorship_rule(self):
        """v3.25.6 - this asserted SILENCE on a neutral prompt.

        Silence on a neutral turn was the gap, not the feature.
        "proceed" and "ship it" are the turns where a rule stated
        long ago has stopped binding, and the router injected
        nothing on them. The authorship rule was violated ten times
        in one session while this test passed.

        The rule now goes out every turn. This pins that, and pins
        the constraint that makes it acceptable: it may carry a TURN
        count and must never carry a token count, a percentage, or a
        context-fill figure. That telemetry is permanently banned by
        operator directive.
        """
        r = _run_hook("prompt_router.py",
                      json.dumps({"user_prompt": "What time is it?"}))
        assert r.returncode == 0
        assert "harness-law" in r.stdout, (
            f"the authorship rule must reach every turn; got {r.stdout!r}")
        low = r.stdout.lower()
        for banned in ("token", "context window", "% full", "budget"):
            assert banned not in low, (
                f"router must not emit context telemetry; found {banned!r}")

    def test_silent_on_empty_prompt(self):
        r = _run_hook("prompt_router.py", json.dumps({"user_prompt": ""}))
        assert r.returncode == 0
        assert r.stdout.strip() == ""

    def test_coding_keywords_route_to_coding_archetype(self):
        r = _run_hook("prompt_router.py",
                      json.dumps({"user_prompt": "refactor the pytest suite"}))
        assert r.returncode == 0
        assert "coding" in r.stdout.lower()
        assert "coding_archetype" in r.stdout

    def test_gui_keywords_route_to_gui_archetype(self):
        r = _run_hook("prompt_router.py",
                      json.dumps({"user_prompt": "add a QPushButton to the widget"}))
        assert r.returncode == 0
        assert "gui" in r.stdout.lower()
        assert "gui_archetype" in r.stdout

    def test_docs_keywords_route_to_docs_archetype(self):
        r = _run_hook("prompt_router.py",
                      json.dumps({"user_prompt": "write a how-to guide for the API"}))
        assert r.returncode == 0
        assert "docs" in r.stdout.lower() or "documentation" in r.stdout.lower()
        assert "docs_archetype" in r.stdout

    def test_cascade_keywords_trigger_reminder(self):
        r = _run_hook("prompt_router.py",
                      json.dumps({"user_prompt": "ship the release with a version bump"}))
        assert r.returncode == 0
        assert "cascade" in r.stdout.lower() or "check_release_readiness" in r.stdout

    def test_multi_domain_prompt_surfaces_all(self):
        r = _run_hook("prompt_router.py",
                      json.dumps({"user_prompt": "refactor the QWidget documentation"}))
        assert r.returncode == 0
        # coding (refactor) + gui (QWidget) + docs (documentation)
        low = r.stdout.lower()
        assert "coding" in low and "gui" in low and "docs" in low

    def test_malformed_stdin_does_not_crash(self):
        r = _run_hook("prompt_router.py", "not valid json {")
        assert r.returncode == 0  # fail-open, never crash CC


# ---------------------------------------------------------------------------
# archetype_gate.py
# ---------------------------------------------------------------------------


class TestArchetypeGate:
    def test_skip_docs_audits_path(self, tmp_path):
        # Any file under docs/audits/ is a known-noise path
        stdin = json.dumps({
            "tool_name": "Write",
            "tool_input": {"file_path": "docs/audits/2026-07-24_x/foo.py"},
        })
        r = _run_hook("archetype_gate.py", stdin)
        assert r.returncode == 0
        # skip = no output
        assert r.stdout.strip() == "" or "skip" in r.stdout.lower()

    def test_hook_files_are_graded_like_any_other_file(self):
        """v3.25.6 - this asserted hook files were SKIPPED.

        The enforcement layer exempting itself is why a dead
        command survived in prompt_router for a whole session: it
        injected a path that does not exist into context on every
        release turn, and no archetype ever looked at it. The stated
        reason for the exemption was recursion, but running an
        archetype makes no tool call, so recursion cannot occur.

        Hook files are now graded like any other Python file.
        """
        stdin = json.dumps({
            "tool_name": "Edit",
            "tool_input": {"file_path": ".claude/hooks/prompt_router.py"},
        })
        r = _run_hook("archetype_gate.py", stdin)
        assert r.returncode == 0
        assert "archetype-gate" in r.stdout, (
            f"a hook file must receive a verdict, not silence; "
            f"got {r.stdout!r}")

    def test_non_write_tool_ignored(self):
        stdin = json.dumps({
            "tool_name": "Read",
            "tool_input": {"file_path": "src/__init__.py"},
        })
        r = _run_hook("archetype_gate.py", stdin)
        assert r.returncode == 0
        # gate only fires for Write|Edit; other tools produce no archetype run
        assert r.stdout.strip() == "" or "not applicable" in r.stdout.lower() or \
               "not run" in r.stdout.lower()

    def test_malformed_stdin_does_not_crash(self):
        r = _run_hook("archetype_gate.py", "not json {")
        assert r.returncode == 0

    def test_archetype_pick_logic_module_level(self):
        """Directly exercise the router rather than via subprocess.

        v3.25.0 - this asserted ONE archetype per file, which is the rule
        the operator replaced on 2026-08-09: "Should be all four...GUI,
        Coding, TA (Chart + Quant), Docs."

        Under the old rule a Qt widget got `gui_archetype` and nothing
        else. `gui_archetype` runs 3 tools; `coding_archetype` runs 6.
        mypy, pyright, vulture and semgrep never ran on any file under
        src/gui/. The assertion below is the one that let that stand, so
        it now checks the SET and requires coding on every .py file.
        """
        sys.path.insert(0, str(HOOKS))
        try:
            import archetype_gate
        finally:
            sys.path.pop(0)
        pick = archetype_gate._pick_archetypes
        CODING = "dev_harness.harness.coding_archetype"
        GUI = "dev_harness.harness.gui_archetype"
        DOCS = "dev_harness.harness.docs_archetype"

        # A Qt widget is BOTH a GUI file and a Python file.
        gui_fixture = REPO / "docs" / "audits" / "2026-07-24_gui_docs_archetypes" \
                    / "gui_fixtures" / "known_good_widget.py"
        got = pick(gui_fixture, gui_fixture.read_text(encoding='utf-8'))
        assert CODING in got, f"coding must run on every .py file, got {got}"
        assert GUI in got, f"Qt widget must also get gui, got {got}"

        # A plain Python file gets coding and NOT gui. This is the
        # negative half: without it, a router that returned every
        # archetype for every file would pass the assertion above.
        coding_fixture = REPO / "docs" / "audits" \
                       / "2026-07-24_coding_archetype_multi_agent_test" \
                       / "fixtures" / "known_good.py"
        got = pick(coding_fixture, coding_fixture.read_text(encoding='utf-8'))
        assert CODING in got
        assert GUI not in got, f"plain .py must not get gui, got {got}"

        # Markdown → docs only.
        md = REPO / "docs" / "audits" / "2026-07-24_gui_docs_archetypes" \
           / "docs_fixtures" / "known_good.md"
        assert pick(md, md.read_text(encoding="utf-8")) == [DOCS]

        # v3.25.6 - routing must follow the PENDING source, not the
        # bytes on disk. Routing on disk meant a write that ADDED a
        # Qt widget was graded by the coding archetype alone: the
        # saved file had no widget yet, so the GUI archetype was
        # never called on the change that introduced one. Measured
        # before the fix: on-disk routing [coding], pending routing
        # [coding, gui].
        widget_pending = (
            "from PySide6.QtWidgets import QWidget\n\n"
            "class W(QWidget):\n    pass\n"
        )
        got = pick(coding_fixture, widget_pending)
        assert GUI in got, (
            "a pending write that adds a Qt widget must reach the "
            f"GUI archetype even though the file on disk has none; "
            f"got {got}")
        assert pick(REPO / "README.md", (REPO / "README.md").read_text(encoding="utf-8", errors="replace")) == [DOCS]

        # Unknown extension → nothing.
        assert pick(REPO / "LICENSE", "") == []

        # v3.25.6 - the singular _pick_archetype shim was removed with
        # the rest of the one-archetype-per-file design. Nothing in the
        # live tree calls it; the only remaining references are inside
        # old git worktree snapshots. Asserting consistency with a
        # function that no longer exists tests nothing.


# ---------------------------------------------------------------------------
# verify_release_gate.py
# ---------------------------------------------------------------------------


class TestVerifyReleaseGate:
    def test_non_banner_path_passes_through(self):
        stdin = json.dumps({
            "tool_name": "Edit",
            "tool_input": {"file_path": "dev_harness/harness/foo.py"},
        })
        r = _run_hook("verify_release_gate.py", stdin)
        assert r.returncode == 0
        assert r.stdout.strip() == ""

    def test_non_write_tool_passes_through(self):
        stdin = json.dumps({
            "tool_name": "Read",
            "tool_input": {"file_path": "src/__init__.py"},
        })
        r = _run_hook("verify_release_gate.py", stdin)
        assert r.returncode == 0
        assert r.stdout.strip() == ""

    def test_banner_path_no_sidecar_denies(self, tmp_path, monkeypatch):
        """Move sidecar aside temporarily; a banner-bump edit must deny."""
        sidecar = REPO / ".release_ready.json"
        backup = None
        if sidecar.exists():
            backup = tmp_path / "sidecar.bak"
            sidecar.rename(backup)
        try:
            stdin = json.dumps({
                "tool_name": "Edit",
                "tool_input": {"file_path": "main.py"},
            })
            r = _run_hook("verify_release_gate.py", stdin)
            assert r.returncode == 0
            assert r.stdout.strip(), "expected deny payload"
            payload = json.loads(r.stdout)
            assert payload["decision"] == "deny"
            assert "banner" in payload["reason"].lower() or \
                   "release" in payload["reason"].lower()
        finally:
            if backup is not None:
                backup.rename(sidecar)

    def test_banner_path_fresh_sidecar_allows(self, tmp_path):
        """Write a synthetic fresh sidecar (avoids recursive pytest call
        that would occur from invoking check_release_readiness inside a
        test file that IS in the pytest suite).

        v3.24.34 (C43): the fixture now writes a COMPLETE sidecar. It
        previously wrote `tests: 0` with no `checks_run` -- which is
        exactly the artefact a `--no-pytest` run produces, and which the
        hook now denies. The assertion is unchanged (a good sidecar
        allows); only the fixture moved to the real shape. Pinning the
        old shape as "allow" would have pinned the defect.
        """
        from datetime import datetime, timezone
        sidecar = REPO / ".release_ready.json"
        backup = None
        if sidecar.exists():
            backup = tmp_path / "sidecar.bak"
            sidecar.replace(backup)
        try:
            now = datetime.now(timezone.utc).replace(microsecond=0)
            iso = now.isoformat().replace("+00:00", "Z")
            sidecar.write_text(json.dumps({
                "version": "test", "tests": 1105,
                "checks_run": {"pytest": "ran", "archetypes": "ran",
                               "claims": "ran"},
                "timestamp": iso, "generator": "test_hooks",
            }), encoding="utf-8")
            stdin = json.dumps({
                "tool_name": "Write",
                "tool_input": {"file_path": "src/__init__.py"},
            })
            r = _run_hook("verify_release_gate.py", stdin)
            assert r.returncode == 0
            assert r.stdout.strip() == "", (
                f"fresh sidecar should allow banner write; got {r.stdout!r}"
            )
        finally:
            sidecar.unlink(missing_ok=True)
            if backup is not None:
                backup.replace(sidecar)

    def test_malformed_stdin_does_not_crash(self):
        r = _run_hook("verify_release_gate.py", "not json {")
        assert r.returncode == 0


# ---------------------------------------------------------------------------
# session_stop_backstop.py
# ---------------------------------------------------------------------------


class TestSessionStopBackstop:
    def test_runs_without_crash(self):
        r = _run_hook("session_stop_backstop.py", json.dumps({}))
        assert r.returncode == 0

    def test_malformed_stdin_does_not_crash(self):
        r = _run_hook("session_stop_backstop.py", "not json {")
        assert r.returncode == 0
