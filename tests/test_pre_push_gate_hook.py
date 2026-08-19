"""Pins `.githooks/pre-push` — the mechanism that keeps ungated code on its branch.

The operator's standard, 2026-08-19:

    "Code does not leave the branch or get merged until all gates are passing."

Island `promote` enforced that mechanically. Islands were retired the same day
and within the hour a branch was merged on the REASONING that markdown cannot
affect pytest rather than on a measurement. Prose did not bind. This hook is the
replacement mechanism, and these tests are what stop the mechanism itself from
rotting.

TWO-SIDED BY CONSTRUCTION. A hook that always allows is the failure mode being
guarded against, and it would pass any test that only checks the happy path. So
every allow case here is paired with a refuse case driven through the same
entry point, reading the REAL exit status — never through a pipe, which returns
the pipe's status and not the hook's.

Fully isolated: each test builds a throwaway git repo under `tmp_path`. Nothing
touches the real working tree, and nothing writes to the operator's home.
"""

# ruff: noqa: S603
# S607 IS FIXED BY CONSTRUCTION, NOT SUPPRESSED — see the reasoning at the top
# of tools/harness/coding_archetype.py. Every spawn below resolves its
# executable to an absolute path first (`_GIT`, `_sh()`), so a `git.cmd` or
# `sh.cmd` planted earlier on PATH cannot be executed under the developer's
# token during a test run.
#
# S603 remains and is not avoidable: an all-literal argv draws none and every
# argv carrying a variable draws one. A resolved interpreter path is a variable
# by definition. This directive is the residue, narrowed to the one rule.
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
HOOK_SOURCE = REPO / ".githooks" / "pre-push"
NULL_SHA = "0" * 40

_GIT = shutil.which("git")


def _git_exe() -> str:
    """Absolute git path, or fail loudly. A skipped test is not evidence."""
    if _GIT is None:
        pytest.fail("git not found; the pre-push hook cannot be verified")
    return _GIT


def _sh() -> str:
    """Locate a POSIX shell. Fails loudly rather than skipping.

    A skipped test is not evidence, and this hook is the only thing standing
    between an ungated commit and the default branch.
    """
    found = shutil.which("sh") or shutil.which("bash")
    if not found:
        pytest.fail("no POSIX shell available; the pre-push hook cannot be verified")
    return found


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A throwaway git repo with the real hook copied in."""
    subprocess.run([_git_exe(), "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run([_git_exe(), "config", "user.email", "t@t"], cwd=tmp_path, check=True)
    subprocess.run([_git_exe(), "config", "user.name", "t"], cwd=tmp_path, check=True)
    (tmp_path / "seed.txt").write_text("seed\n", encoding="utf-8", newline="\n")
    subprocess.run([_git_exe(), "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run([_git_exe(), "commit", "-qm", "seed"], cwd=tmp_path, check=True)

    hooks = tmp_path / ".githooks"
    hooks.mkdir()
    shutil.copyfile(HOOK_SOURCE, hooks / "pre-push")
    return tmp_path


def _head(repo: Path) -> str:
    out = subprocess.run(
        [_git_exe(), "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
    )
    return out.stdout.strip()


def _drive(repo: Path, pushed_sha: str, env: dict[str, str] | None = None) -> int:
    """Feed the hook one ref line and return its REAL exit status."""
    line = f"refs/heads/x {pushed_sha} refs/heads/x {NULL_SHA}\n"
    proc = subprocess.run(
        [_sh(), str(repo / ".githooks" / "pre-push")],
        cwd=repo,
        input=line,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    return proc.returncode


def _stamp(repo: Path, commit: str) -> None:
    (repo / ".gate_stamp.json").write_text(
        json.dumps({"commit": commit}, indent=2) + "\n", encoding="utf-8", newline="\n"
    )


def test_refuses_when_no_stamp_exists(repo: Path) -> None:
    """The default state. A commit nobody gated must not leave the branch."""
    assert not (repo / ".gate_stamp.json").exists()
    assert _drive(repo, _head(repo)) == 1


def test_refuses_when_the_stamp_names_a_different_commit(repo: Path) -> None:
    """The case a version/count sidecar cannot catch.

    `.release_ready.json` records a version and a test count, so two different
    commits at the same version produce identical sidecars. Only a commit sha
    distinguishes them, which is the whole reason the stamp exists.
    """
    _stamp(repo, "dead" * 10)
    assert _drive(repo, _head(repo)) == 1


def test_allows_when_the_stamp_names_the_pushed_commit(repo: Path) -> None:
    """The other half. A gate that refuses everything gets bypassed."""
    head = _head(repo)
    _stamp(repo, head)
    assert _drive(repo, head) == 0


def test_a_stamp_goes_stale_the_moment_another_commit_lands(repo: Path) -> None:
    """Gate, then commit again, then push: the stamp must no longer authorise.

    This is the realistic mistake — gate green, then 'just one more fix' — and
    it is exactly what a sidecar without a sha cannot detect.
    """
    gated = _head(repo)
    _stamp(repo, gated)
    assert _drive(repo, gated) == 0

    (repo / "seed.txt").write_text("changed\n", encoding="utf-8", newline="\n")
    subprocess.run([_git_exe(), "commit", "-aqm", "one more fix"], cwd=repo, check=True)
    new_head = _head(repo)
    assert new_head != gated

    assert _drive(repo, new_head) == 1


def test_branch_deletion_is_allowed_with_no_stamp(repo: Path) -> None:
    """A deletion pushes the null sha. There is no content to gate.

    Without this, deleting a merged branch would be impossible until someone
    ran a 25-minute suite for it, and a hook that obstructs legitimate work is
    a hook that gets disabled.
    """
    assert not (repo / ".gate_stamp.json").exists()
    assert _drive(repo, NULL_SHA) == 0


def test_the_documented_bypass_works_and_is_the_only_one(repo: Path) -> None:
    """The escape hatch exists for a broken harness, and must be deliberate.

    Paired with its own negative: the same push without the variable is
    refused, so this proves the variable is what allowed it and not some
    unrelated leniency.
    """
    import os

    base = dict(os.environ)
    base.pop("ACERVATOR_SKIP_GATE_HOOK", None)
    assert _drive(repo, _head(repo), env=base) == 1

    bypass = dict(base)
    bypass["ACERVATOR_SKIP_GATE_HOOK"] = "1"
    assert _drive(repo, _head(repo), env=bypass) == 0
