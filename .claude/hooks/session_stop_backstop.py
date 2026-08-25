#!/usr/bin/env python3
"""
Stop hook — session-end backstop for uncommitted work.

v3.20.43 absorption pattern from Anthropic's `cwc-long-running-agents`:
"commit-on-stop.sh is the backstop that catches whatever's still
uncommitted at session end."

SADP-flavored version: instead of forcing an auto-commit to the main
branch (which could pollute history with mid-cascade snapshots), we
write a FORENSIC LOG of what was uncommitted plus a full diff
artifact. Non-destructive. Composes with EDIT_LOG.jsonl (which tracks
intentional edits with authority/purpose) by capturing what is IN the
working tree at session boundaries.

What it does on every Stop:
  1. Capture `git status --porcelain` of the active tree.
  2. If anything is uncommitted, write an entry to
     `.sadp/session_history.jsonl` with timestamp, version, file
     count, and a one-line summary.
  3. If anything is uncommitted, also dump the full `git diff HEAD`
     to `.sadp/session_backstops/YYYY-MM-DD_HHMMSS.diff` for
     forensic recovery.
  4. NEVER runs `git commit`, `git add`, `git stash`, or any
     mutating git command. Read-only on the working tree.

Failure mode contract:
  - If anything fails, log to stderr but exit 0. A Stop hook must
    never block session shutdown.
  - If the repo doesn't have git, exit 0 silently.

Hook contract per Claude Code:
  - stdin: arbitrary JSON (we ignore it)
  - stdout: arbitrary (ignored)
  - exit 0: continue with normal Stop behavior (NEVER block)
"""

from __future__ import annotations
import json
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


def _git_exe() -> str | None:
    """Absolute path to git, or None when git is not on PATH.

    A bare "git" argv[0] resolves against PATH at call time, so a
    shadowing binary earlier on PATH would run instead. Resolving once
    here removes that. Callers already treat a failure as "no data".
    """
    return shutil.which("git")


def _find_repo_root() -> Path | None:
    """Walk up looking for a .git directory OR a sadp/ directory
    (Acervator's canonical project root marker — git is optional)."""
    cur = Path.cwd()
    for _ in range(6):
        if (cur / ".git").exists() or (cur / "sadp").is_dir():
            return cur
        if cur.parent == cur:
            return None
        cur = cur.parent
    return None


def _has_git(repo_root: Path) -> bool:
    return (repo_root / ".git").exists()


def _read_version(repo_root: Path) -> str:
    init_py = repo_root / "src" / "__init__.py"
    if not init_py.is_file():
        return "unknown"
    try:
        txt = init_py.read_text(encoding="utf-8")
    except OSError:
        return "unknown"
    m = re.search(r'__version__\s*=\s*["\'](\d+\.\d+\.\d+)["\']', txt)
    return m.group(1) if m else "unknown"


def _run_git(repo_root: Path, args: list, timeout: int) -> str:
    """Run a read-only git command. Empty string on any failure.

    argv[0] is the absolute path from `_git_exe`, and every other
    element is a literal from the caller plus the repo root. No
    shell=True, no user-supplied token. S603 is a false positive here.
    """
    exe = _git_exe()
    if exe is None:
        return ""
    try:
        r = subprocess.run(  # noqa: S603
            [exe, "-C", str(repo_root), *args],
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if r.returncode != 0:
        return ""
    return r.stdout


def _git_status_porcelain(repo_root: Path) -> str:
    """Return the porcelain output, empty string on failure."""
    return _run_git(repo_root, ["status", "--porcelain"], timeout=10)


def _git_diff_head(repo_root: Path) -> str:
    """Return the unified diff against HEAD, empty string on failure."""
    return _run_git(repo_root, ["diff", "HEAD"], timeout=30)


def _summarize_status(porcelain: str) -> tuple[int, int, int, int]:
    """Return (modified, added, deleted, untracked)."""
    modified = added = deleted = untracked = 0
    for line in porcelain.splitlines():
        if len(line) < 3:
            continue
        code = line[:2]
        if code.startswith("M") or code == " M":
            modified += 1
        elif code.startswith("A") or code == " A":
            added += 1
        elif code.startswith("D") or code == " D":
            deleted += 1
        elif code == "??":
            untracked += 1
        else:
            # Other statuses (R, C, U) — bucket as modified
            modified += 1
    return modified, added, deleted, untracked


def main() -> int:
    try:
        # Consume stdin if present so the hook doesn't block on it
        try:
            sys.stdin.read()
        except (OSError, UnicodeDecodeError):
            pass

        repo_root = _find_repo_root()
        if repo_root is None:
            return 0  # Not a recognizable repo — no-op.

        # If git isn't available, write a minimal session-boundary
        # marker and exit. The forensic-capture path only runs when
        # git is present in the tree.
        if not _has_git(repo_root):
            sadp_dir = repo_root / ".sadp"
            sadp_dir.mkdir(parents=True, exist_ok=True)
            history = sadp_dir / "session_history.jsonl"
            entry = {
                "ts": int(time.time()),
                "iso": datetime.now().isoformat(),
                "version": _read_version(repo_root),
                "clean": True,
                "note": "no git tree — minimal session-boundary marker only",
            }
            with history.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            return 0

        porcelain = _git_status_porcelain(repo_root)
        if not porcelain.strip():
            # Clean tree — log a "clean stop" line and exit
            sadp_dir = repo_root / ".sadp"
            sadp_dir.mkdir(parents=True, exist_ok=True)
            history = sadp_dir / "session_history.jsonl"
            entry = {
                "ts": int(time.time()),
                "iso": datetime.now().isoformat(),
                "version": _read_version(repo_root),
                "clean": True,
            }
            with history.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            return 0

        # Uncommitted work present — capture diff + log
        modified, added, deleted, untracked = _summarize_status(porcelain)
        version = _read_version(repo_root)
        now = datetime.now()
        iso = now.isoformat()
        stamp = now.strftime("%Y-%m-%d_%H%M%S")

        sadp_dir = repo_root / ".sadp"
        backstops_dir = sadp_dir / "session_backstops"
        backstops_dir.mkdir(parents=True, exist_ok=True)

        # Write diff artifact
        diff_path = backstops_dir / f"{stamp}.diff"
        diff_text = _git_diff_head(repo_root)
        # Include the porcelain status at the top so untracked files are visible
        with diff_path.open("w", encoding="utf-8") as f:
            f.write(f"# session_stop_backstop @ {iso}\n")
            f.write(f"# version: v{version}\n")
            f.write("# git status --porcelain:\n")
            for line in porcelain.splitlines():
                f.write(f"#   {line}\n")
            f.write("# ── unified diff against HEAD ────────────────────\n\n")
            f.write(diff_text)

        # Append JSONL entry
        history = sadp_dir / "session_history.jsonl"
        files_total = modified + added + deleted + untracked
        entry = {
            "ts": int(time.time()),
            "iso": iso,
            "version": version,
            "clean": False,
            "files": {
                "total": files_total,
                "modified": modified,
                "added": added,
                "deleted": deleted,
                "untracked": untracked,
            },
            "diff_artifact": str(diff_path.relative_to(repo_root)).replace("\\", "/"),
        }
        with history.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        # Quiet success — stderr only if operator wants to see it
        print(
            f"[session_stop_backstop] captured {files_total} files at v{version} -> "
            f"{diff_path.relative_to(repo_root)}",
            file=sys.stderr,
        )
        return 0

    except Exception as exc:  # noqa: BLE001
        # Never block session shutdown.
        print(f"[session_stop_backstop] non-fatal error: {exc!r}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
