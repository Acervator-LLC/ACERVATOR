"""Run `dev_harness.harness.check_release_readiness` and record the commit it proved.

`main` writes `STAMP_PATH` with the HEAD sha only on a green run of a clean
tree, and `clear_stamp` removes it otherwise. `SIDECAR_PATH` carries a version
and a test count but names no commit, which is what `head_sha` supplies.
`describe_tags` is the one git call `src/_version.py` reaches for.

    python -m tools.gate
"""

# ruff: noqa: S603
# `_GIT` is a variable, and every argv here carries one.
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
    """Run git in `REPO` and return stripped stdout, or '' on failure.

    Returns '' when `_GIT` is None, which every caller treats as unknown.
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
    """True when tracked content in `REPO` differs from HEAD.

    Untracked files do not count: `_git` is called with `--untracked-files=no`.
    """
    return bool(_git("status", "--porcelain", "--untracked-files=no"))


def describe_tags(root: str | Path, match: str, dirty_suffix: str) -> str:
    """Return `git describe` output for the repository at `root`, or ''.

    `match` limits the eligible tags; a tree with none falls back to a commit id.
    """
    return _git(
        "-C",
        str(root),
        "describe",
        "--tags",
        "--match",
        match,
        "--long",
        f"--dirty={dirty_suffix}",
        "--always",
    )


def clear_stamp(reason: str) -> None:
    """Delete `STAMP_PATH` and print `reason`."""
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
                "gated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
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
