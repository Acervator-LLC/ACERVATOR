"""Pins for the release-gate PreToolUse hook — v3.24.34 (cascade C43).

Replaces the pre-2026-07-25 archived pin, which provided ZERO coverage.
It drifted from the hook on four axes at once:

    axis          archived pin                    real hook
    payload key   {"tool": "Edit"}                reads `tool_name` (:99)
    sidecar path  .sadp/.last_release_check.json  .release_ready.json (:35)
    deny signal   asserts rc == 2                 always exits 0; the
                                                  decision is JSON on
                                                  stdout (:17, :118-128)
    timestamp     int(time.time())                ISO-8601 (:71)

Because the hook reads `tool_name` and the pin sent `tool`, main()
returned at :100 before reading anything. Measured with the real
sidecar deleted -- the exact case the pin existed to catch:

    archived shape : rc=0  NO OUTPUT = ALLOW
    current shape  : rc=0  decision=deny

So its 7 green assertions were all `assert rc == 0` against a function
returning 0 unconditionally for their input; they would have stayed
green with the hook body deleted. Full classification:
docs/audits/2026-08-05_C43_archived_pin_classification.md.

These tests import the hook as a module and redirect SIDECAR_PATH onto
tmp_path. The archived pin mutated the real sidecar and restored it
best-effort in a fixture; an interrupted run left the operator's tree
holding whatever the last test wrote.
"""

from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOK_PATH = REPO_ROOT / ".claude" / "hooks" / "verify_release_gate.py"


def _load_hook():
    spec = importlib.util.spec_from_file_location(
        "verify_release_gate_under_test", HOOK_PATH
    )
    assert spec and spec.loader, f"cannot load hook at {HOOK_PATH}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


hook = _load_hook()


def _sidecar(tests=1105, version="3.24.32", checks=None, age_minutes=0):
    """Build a sidecar payload in the shape the real gate writes."""
    from datetime import datetime, timedelta, timezone

    when = datetime.now(timezone.utc) - timedelta(minutes=age_minutes)
    return {
        "version": version,
        "tests": tests,
        "checks_run": (
            {"pytest": "ran", "archetypes": "ran", "claims": "ran"}
            if checks is None
            else checks
        ),
        "timestamp": when.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "generator": "tools/harness/check_release_readiness.py",
    }


@pytest.fixture
def run_hook(tmp_path, monkeypatch, capsys):
    """Drive hook.main() with a payload and an isolated sidecar.

    Returns (decision, reason): decision is "allow" when the hook emits
    nothing, else the decision from its stdout JSON.
    """
    fake = tmp_path / ".release_ready.json"
    monkeypatch.setattr(hook, "SIDECAR_PATH", fake)

    def _run(payload: dict, sidecar: dict | None):
        if sidecar is None:
            if fake.exists():
                fake.unlink()
        else:
            fake.write_text(json.dumps(sidecar), encoding="utf-8")
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
        rc = hook.main()
        out = capsys.readouterr().out.strip()
        if not out:
            return "allow", ""
        body = json.loads(out)
        return body.get("decision", "?"), body.get("reason", "")

    _run.rc_is_always_zero = True
    return _run


def _edit(path: str):
    return {
        "tool_name": "Edit",
        "tool_input": {
            "file_path": path,
            "old_string": '__version__ = "3.24.32"',
            "new_string": '__version__ = "3.24.33"',
        },
    }


BANNER = str(REPO_ROOT / "src" / "__init__.py")
MAIN_PY = str(REPO_ROOT / "main.py")


class TestHookIsInstalled:
    def test_hook_file_exists(self):
        assert HOOK_PATH.is_file()

    def test_hook_is_registered_as_a_pretooluse_hook(self):
        settings = REPO_ROOT / ".claude" / "settings.json"
        assert settings.is_file()
        body = json.loads(settings.read_text(encoding="utf-8"))
        cmds = [
            c.get("command", "")
            for entry in body.get("hooks", {}).get("PreToolUse", [])
            for c in entry.get("hooks", [])
        ]
        assert any("verify_release_gate.py" in c for c in cmds), cmds


class TestPassThrough:
    def test_non_banner_path_is_allowed(self, run_hook):
        decision, _ = run_hook(_edit(str(REPO_ROOT / "docs" / "notes.md")), _sidecar())
        assert decision == "allow"

    def test_non_write_tool_is_allowed(self, run_hook):
        decision, _ = run_hook(
            {"tool_name": "Read", "tool_input": {"file_path": BANNER}}, None
        )
        assert decision == "allow"


class TestBannerPathsAreGated:
    @pytest.mark.parametrize("target", [BANNER, MAIN_PY])
    def test_fresh_complete_sidecar_allows(self, run_hook, target):
        decision, reason = run_hook(_edit(target), _sidecar())
        assert decision == "allow", reason

    @pytest.mark.parametrize("target", [BANNER, MAIN_PY])
    def test_missing_sidecar_denies(self, run_hook, target):
        decision, reason = run_hook(_edit(target), None)
        assert decision == "deny"
        assert "sidecar" in reason.lower()

    def test_stale_sidecar_denies(self, run_hook):
        decision, reason = run_hook(_edit(BANNER), _sidecar(age_minutes=90))
        assert decision == "deny"
        assert "old" in reason.lower()


class TestSidecarMustProveWhatItRan:
    """Step 4 of C43. Freshness alone is not evidence.

    A sidecar written by `--no-pytest` is exactly as fresh as one from a
    full run; before v3.24.34 the hook could not tell them apart.
    """

    def test_sidecar_without_checks_run_is_not_trusted(self, run_hook):
        legacy = _sidecar()
        del legacy["checks_run"]
        decision, reason = run_hook(_edit(BANNER), legacy)
        assert decision == "deny"
        assert "checks_run" in reason

    def test_sidecar_recording_a_skipped_check_denies(self, run_hook):
        decision, reason = run_hook(
            _edit(BANNER),
            _sidecar(
                checks={"pytest": "skipped", "archetypes": "ran", "claims": "ran"}
            ),
        )
        assert decision == "deny"
        assert "pytest" in reason

    def test_sidecar_reporting_zero_tests_denies(self, run_hook):
        """The exact artefact observed in the tree on 2026-08-05."""
        decision, reason = run_hook(_edit(BANNER), _sidecar(tests=0))
        assert decision == "deny"
        assert "0 tests" in reason


class TestPayloadContract:
    """Regression guard against the vacuity that made the archived pin
    worthless. If the key the hook reads ever drifts again, this fails
    instead of every other test silently passing."""

    def test_hook_reads_tool_name_not_tool(self, run_hook):
        legacy_shape = {"tool": "Edit", "tool_input": {"file_path": BANNER}}
        decision, _ = run_hook(legacy_shape, None)
        current_shape = _edit(BANNER)
        decision_current, _ = run_hook(current_shape, None)
        assert (
            decision_current == "deny"
        ), "hook no longer denies a correctly-shaped payload"
        assert decision == "allow", (
            "hook now reacts to the legacy 'tool' key; if the payload "
            "contract changed, update _edit() and this pin together"
        )

    def test_unparseable_stdin_is_pass_through(self, monkeypatch, capsys):
        """Documented fail-open: a broken payload must not block edits."""
        monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
        assert hook.main() == 0
        assert capsys.readouterr().out.strip() == ""
