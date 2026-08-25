"""PreToolUse hook: gates Write/Edit on banner-bump paths.

Fires only for Write/Edit tools targeting:
  - src/__init__.py       (canonical __version__)
  - main.py               (current_version banner)

For those targets, checks the sidecar `.release_ready.json` at repo root:
  - MISSING       → DENY with instructions to run check_release_readiness
  - STALE (>1 hr) → DENY with instructions to re-run
  - FRESH + [OK]  → ALLOW

For any other target path, ALLOW (pass-through). The gate is deliberately
narrow — it only blocks version-banner bumps, not general edits.

Stdin: JSON payload from Claude Code with tool_name + tool_input.
Stdout: {"decision": "allow"|"deny", "reason": "..."} on non-allow.
Exit code: 0 always; the decision is in the JSON payload.

FALSIFICATION: this hook is wrong if (a) BANNER_PATHS doesn't reflect the
actual source-of-truth version files (check src/__init__.py + main.py by
grepping for `__version__` / `current_version`), (b) the sidecar can be
forged by a process bypassing `check_release_readiness.py`, (c) the
MAX_AGE_SECONDS threshold is wrong for the operator's workflow.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
SIDECAR_PATH = REPO / ".release_ready.json"

# Paths whose Write/Edit MUST have a fresh green sidecar.
BANNER_PATHS = frozenset(
    {
        "src/__init__.py",
        "main.py",
    }
)

# Sidecar is considered stale after 1 hour. That's long enough for a
# cascade session, short enough that a stale gate can't hide a broken
# state for long.
MAX_AGE_SECONDS = 60 * 60


def _normalize(path: str) -> str:
    """Return the repo-relative path with forward slashes."""
    p = Path(path)
    try:
        rel = p.resolve().relative_to(REPO)
    except (ValueError, OSError):
        rel = p
    return str(rel).replace(os.sep, "/")


def _sidecar_state() -> tuple[str, str]:
    """Return (state, reason). state is 'fresh', 'stale', or 'missing'."""
    if not SIDECAR_PATH.exists():
        return "missing", "no .release_ready.json sidecar"
    try:
        data = json.loads(SIDECAR_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        return "missing", f"cannot read sidecar: {e}"
    ts = data.get("timestamp")
    if not ts:
        return "missing", "sidecar has no timestamp"
    try:
        when = datetime.fromisoformat(ts)
    except (TypeError, ValueError):
        return "missing", f"cannot parse sidecar timestamp {ts!r}"
    if when.tzinfo is None:
        # A naive stamp would raise on the subtraction below and take
        # the whole gate down. Read it as UTC, which is what the
        # generator writes.
        when = when.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - when).total_seconds()
    if age > MAX_AGE_SECONDS:
        mins = int(age / 60)
        return "stale", f"sidecar is {mins} min old (max {MAX_AGE_SECONDS//60})"

    # Freshness alone is not evidence. A sidecar written by
    # `--no-pytest` is just as fresh as one written by a full run, and
    # before v3.24.34 the two were indistinguishable here. Observed
    # 2026-08-05: a `tests: 0` green sidecar advertised readiness for
    # 46 minutes. Require the run to say what it actually did.
    checks = data.get("checks_run")
    if not isinstance(checks, dict):
        return "incomplete", (
            "sidecar has no checks_run record (written by a pre-v3.24.34 "
            "gate); re-run the gate to produce a trustworthy sidecar"
        )
    skipped = sorted(k for k, v in checks.items() if v != "ran")
    if skipped:
        return "incomplete", ("sidecar records skipped check(s): " + ", ".join(skipped))

    try:
        n_tests = int(data.get("tests", 0))
    except (TypeError, ValueError):
        n_tests = 0
    if n_tests <= 0:
        return "incomplete", f"sidecar reports {n_tests} tests"

    return "fresh", (f"sidecar fresh; v{data.get('version','?')}, " f"{n_tests} tests")


def _payload_target(payload: dict) -> str | None:
    """Extract the target file_path from a Write/Edit tool_input."""
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return None
    target = tool_input.get("file_path") or tool_input.get("path")
    return target if isinstance(target, str) else None


def main() -> int:
    # Read the hook payload from stdin. If parse fails, PASS-THROUGH
    # rather than block — safer to allow the tool call than to make
    # every Write/Edit undebuggable.
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    # Measured 2026-08-10: stdin of `null`, `[1,2,3]` or a non-object
    # tool_input raised AttributeError and exited 1. A non-zero hook
    # exit is a non-blocking error, so the gate failed OPEN on exactly
    # the malformed input a caller bug would produce.
    if not isinstance(payload, dict):
        return 0

    tool_name = payload.get("tool_name", "")
    if tool_name not in ("Write", "Edit"):
        return 0

    target = _payload_target(payload)
    if not target:
        return 0

    rel = _normalize(target)
    if rel not in BANNER_PATHS:
        # not a banner-bump path — pass through silently
        return 0

    state, reason = _sidecar_state()
    if state == "fresh":
        # sidecar green; allow the banner-bump write
        return 0

    # Deny with instructions
    output = {
        "decision": "deny",
        "reason": (
            f"Release-gate DENY: attempting to write banner-bump path "
            f"{rel!r} but {reason}. Run:\n"
            f"  python -m tools.harness.check_release_readiness\n"
            f"and get `[OK] Release-ready (vX.Y.Z, N tests)` first."
        ),
    }
    print(json.dumps(output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
