"""Run the release gate and STAMP the commit it proved.

Why this exists
---------------
The operator's standard, stated 2026-08-19:

    "Code does not leave the branch or get merged until all gates are
     passing."

Island `promote` used to enforce that mechanically. Islands were retired the
same day, and within the hour a documentation branch was merged on the
REASONING that markdown cannot affect pytest rather than on a measurement.
That is the failure this file exists to make impossible.

Why a wrapper and not a change to the gate itself
-------------------------------------------------
`harness-law` forbids editing anything under `dev_harness/harness/`, and that rule
is not negotiable for convenience. So the gate is called, not modified. This
file adds exactly one thing the gate does not record: WHICH COMMIT was proved.

`.release_ready.json` carries a version, a test count and a timestamp. None of
those identifies a tree. Two different commits at v3.25.8 produce identical
sidecars, so a sidecar alone can never answer "was THIS commit gated?" The
stamp answers it by recording the HEAD sha.

The dirty-tree refusal is the load-bearing part
-----------------------------------------------
A gate run against a dirty working tree measured content that is in no commit.
Stamping it would assert that HEAD was proved when HEAD is not what ran. So a
green gate on a dirty tree is recorded as NOT STAMPED, deliberately, and the
pre-push hook then refuses. Commit first, then gate.

Usage
-----
    python -m tools.gate            # runs the gate, stamps on success

Exit code is the gate's own, unmodified. Never read it through a pipe.
"""

# ruff: noqa: S603
# S607 IS FIXED BY CONSTRUCTION HERE, NOT SUPPRESSED, following the reasoning
# recorded at the top of dev_harness/harness/coding_archetype.py: a partial
# executable path is not a false positive, because on Windows PATH plus
# PATHEXT would execute a `git.cmd` planted anywhere earlier on PATH under the
# developer's own token. Both spawns below use an absolute path — the gate via
# `sys.executable`, git via `_GIT`, resolved once through shutil.which — so
# S607 reports zero here by construction.
#
# S603 remains and is not avoidable, exactly as measured for the archetype: an
# all-literal argv draws no S603 and every argv carrying a variable draws one.
# `_GIT` is a variable by definition, so there is no compliant form of "spawn
# the resolved git". This directive is the residue, narrowed to the one rule.
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
STAMP_PATH = REPO / ".gate_stamp.json"
SIDECAR_PATH = REPO / ".release_ready.json"

_GIT = shutil.which("git")


def _git(*args: str) -> str:
    """Run git in the repo and return stripped stdout, or '' on failure.

    Returns '' when git cannot be resolved at all. Every caller treats '' as
    "unknown", and unknown is refused rather than stamped — a stamp that
    guesses is worse than no stamp.
    """
    if _GIT is None:
        return ""
    try:
        out = subprocess.run(
            [_GIT, *args],
            cwd=REPO,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return ""
    return out.stdout.strip() if out.returncode == 0 else ""


def head_sha() -> str:
    return _git("rev-parse", "HEAD")


def tree_is_dirty() -> bool:
    """True when tracked content differs from HEAD.

    Untracked files are IGNORED on purpose: the gate does not run them and a
    scratch file beside the repo must not block a legitimate push. Tracked
    modifications are what make a stamp a lie.
    """
    return bool(_git("status", "--porcelain", "--untracked-files=no"))


def clear_stamp(reason: str) -> None:
    """Remove a stamp so a later push cannot inherit an older proof."""
    if STAMP_PATH.exists():
        STAMP_PATH.unlink()
        print(f"[gate] stamp cleared: {reason}")


def main() -> int:
    print("[gate] running dev_harness.harness.check_release_readiness ...")
    result = subprocess.run(
        [sys.executable, "-m", "dev_harness.harness.check_release_readiness"],
        cwd=REPO,
        check=False,
    )
    rc = result.returncode

    if rc != 0:
        clear_stamp(f"gate exited {rc}")
        print(f"[gate] NOT STAMPED — gate exited {rc}. Nothing may be pushed.")
        return rc

    sha = head_sha()
    if not sha:
        clear_stamp("HEAD unreadable")
        print("[gate] NOT STAMPED — could not read HEAD.")
        return 1

    if tree_is_dirty():
        clear_stamp("working tree dirty at gate time")
        print(
            "[gate] NOT STAMPED — the gate was green but tracked files differ "
            "from HEAD, so it did not measure any commit. Commit, then re-run."
        )
        return 1

    version, tests = "", 0
    if SIDECAR_PATH.exists():
        try:
            side = json.loads(SIDECAR_PATH.read_text(encoding="utf-8"))
            version, tests = side.get("version", ""), side.get("tests", 0)
        except (OSError, ValueError):
            pass

    STAMP_PATH.write_text(
        json.dumps(
            {
                "commit": sha,
                "version": version,
                "tests": tests,
                "gated_at": datetime.now(timezone.utc).isoformat(
                    timespec="seconds"
                ),
                "generator": "tools/gate.py",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"[gate] STAMPED {sha[:12]} (v{version}, {tests} tests). Push allowed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
