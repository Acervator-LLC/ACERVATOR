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

WHERE THE HOOK IS — 2026-08-25
==============================
The harness moved to user level at the CTO's request. This file used to
build the hook path from the repository root and import the hook AT
MODULE SCOPE, so after the move the whole suite failed during
COLLECTION with FileNotFoundError and nothing could be pushed. The path
now comes from `tools.claude_home`, which searches user level first and
then the repository, exactly as the router hook resolves a skill.

WHAT HAPPENS WHEN THE HARNESS IS ABSENT
=======================================
Absent and INCOMPLETE are different states and are answered
differently.

* ABSENT — no harness directory anywhere. A fresh clone on another
  developer's machine is in this state, and the repository cannot put
  it right: the directory is in `.gitignore` and travels with no clone.
  Failing here would paint the gate red for a state that is not a
  defect, and a gate that is always red carries as little information
  as one that is always green. So these tests SKIP, and the reason
  names every path that was searched. The skip is also raised as a
  warning at import, so it reaches the warnings summary of every run
  rather than hiding behind a dot.
* INCOMPLETE — a harness directory exists but this hook is not in it.
  That is a real defect, in something this repository does pin, so
  `test_the_install_is_not_partial` FAILS.

`TestTheSearchCanFail` carries no skip mark and runs in BOTH states. It
plants a hook under a temporary home and requires the search to find
it, then empties that home and requires None. Without it, the absent
state would leave this file asserting nothing at all, which is the
never-fails shape the skip is otherwise accused of.
"""

from __future__ import annotations

import importlib.util
import io
import json
import warnings
from pathlib import Path
from types import ModuleType

import pytest

from tools import claude_home
from tools.claude_home import (
    absent_reason,
    find,
    hooks_dir,
    missing_hooks,
    settings_file,
)

REPO_ROOT = Path(__file__).resolve().parent.parent

_HOOK_PARTS = ("hooks", "verify_release_gate.py")
HOOK_PATH = find(*_HOOK_PARTS)
_ABSENT = absent_reason(*_HOOK_PARTS)

if HOOK_PATH is None:
    warnings.warn(_ABSENT, stacklevel=1)

_needs_hook = pytest.mark.skipif(HOOK_PATH is None, reason=_ABSENT)


def _load_hook(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "verify_release_gate_under_test", path
    )
    assert spec and spec.loader, f"cannot load hook at {path}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def hook() -> ModuleType:
    """The hook module, imported from wherever it is installed.

    A fixture, not a module-level import. The module-level form is what
    turned a missing file into a COLLECTION error for the whole suite.
    """
    assert HOOK_PATH is not None
    return _load_hook(HOOK_PATH)


class TestTheSearchCanFail:
    """Positive control for the path search. Runs in both states.

    This class deliberately carries no skip mark. It is the reason a
    machine with no harness still runs something here that is able to
    fail.
    """

    def test_search_finds_a_planted_hook_and_reports_an_empty_home(
        self, tmp_path, monkeypatch
    ):
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setattr(claude_home, "REPO", tmp_path / "no-such-repo")
        monkeypatch.setenv("HOME", str(home))
        monkeypatch.setenv("USERPROFILE", str(home))

        assert (
            claude_home.find(*_HOOK_PARTS) is None
        ), "the search reported a hook under a home that holds none"

        planted = home / claude_home.CLAUDE_DIR_NAME / "hooks"
        planted.mkdir(parents=True)
        (planted / "verify_release_gate.py").write_text("", encoding="utf-8")
        assert claude_home.find(*_HOOK_PARTS) == (planted / "verify_release_gate.py")

    def test_the_absent_reason_names_every_path_it_searched(self):
        reason = claude_home.absent_reason(*_HOOK_PARTS)
        for candidate in claude_home.candidates(*_HOOK_PARTS):
            assert str(candidate) in reason, (
                f"the skip reason hides {candidate}; a reader cannot act "
                f"on a message that does not say where it looked"
            )


@_needs_hook
def test_the_install_is_not_partial():
    """A harness directory that is short a hook FAILS, never skips.

    Absence is an uninstalled machine. A directory missing one script is
    a broken install, and a broken install that skips is the silently
    disabled check this repository keeps meeting.
    """
    found = hooks_dir()
    assert found is not None
    absent = missing_hooks(found)
    assert not absent, f"{found} is missing hook script(s): {absent}"


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
        "generator": "dev_harness/harness/check_release_readiness.py",
    }


@pytest.fixture
def run_hook(hook, tmp_path, monkeypatch, capsys):
    """Drive hook.main() with a payload and an isolated sidecar.

    Returns (decision, reason): decision is "allow" when the hook emits
    nothing, else the decision from its stdout JSON.

    The hook always returns 0; the decision travels as JSON on stdout.
    That contract used to be recorded by hanging an unread attribute on
    this closure, which nothing ever read and which pyright reported.
    `test_unparseable_stdin_is_pass_through` asserts the return code
    directly, so the contract is measured rather than annotated.
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
        assert rc == 0, f"the hook must always exit 0; got {rc}"
        out = capsys.readouterr().out.strip()
        if not out:
            return "allow", ""
        body = json.loads(out)
        return body.get("decision", "?"), body.get("reason", "")

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


@_needs_hook
class TestHookIsInstalled:
    def test_hook_file_exists(self):
        """Existence only, and it is not the coverage.

        On its own this assertion is a decoration: it would stay green
        against an empty file. The classes below drive the hook's
        decisions, and they are what make this file evidence.
        """
        assert HOOK_PATH is not None
        assert HOOK_PATH.is_file()

    def test_hook_is_registered_as_a_pretooluse_hook(self):
        settings = settings_file()
        assert settings is not None, absent_reason("settings.json")
        body = json.loads(settings.read_text(encoding="utf-8"))
        cmds = [
            c.get("command", "")
            for entry in body.get("hooks", {}).get("PreToolUse", [])
            for c in entry.get("hooks", [])
        ]
        assert any("verify_release_gate.py" in c for c in cmds), cmds


@_needs_hook
class TestPassThrough:
    def test_non_banner_path_is_allowed(self, run_hook):
        decision, _ = run_hook(_edit(str(REPO_ROOT / "docs" / "notes.md")), _sidecar())
        assert decision == "allow"

    def test_non_write_tool_is_allowed(self, run_hook):
        decision, _ = run_hook(
            {"tool_name": "Read", "tool_input": {"file_path": BANNER}}, None
        )
        assert decision == "allow"


@_needs_hook
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


@_needs_hook
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


@_needs_hook
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

    def test_unparseable_stdin_is_pass_through(self, hook, monkeypatch, capsys):
        """Documented fail-open: a broken payload must not block edits."""
        monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
        assert hook.main() == 0
        assert capsys.readouterr().out.strip() == ""
