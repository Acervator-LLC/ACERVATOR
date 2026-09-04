"""Run the `LANE_ORDER` commands `.github/workflows/ci.yml` states, on this machine.

`XDIST_WORKERS` is 4 and never `auto`, and `QT_QPA_PLATFORM` is left as this
machine sets it. The `src tests tools *.py` glob is expanded here, since a
`subprocess` argv reaches no shell. `NON_FUNCTIONAL` decides which lanes a diff
calls for, and `MAX_SIGNAL` reads a lane's return code back into a verdict.

    python -m tools.local_ci --lane fast
    python -m tools.local_ci --all
"""

# ruff: noqa: S603
# Every lane argv carries the expanded file list, and `_GIT_EXE` is a variable.
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

#: Never `auto`. See the module docstring.
XDIST_WORKERS = 4

#: A lane that has not answered in this many seconds is hung, not slow.
DEFAULT_TIMEOUT_SECONDS = 3600

#: ci.yml's `IGNORE` pattern; applied with `re.search`, as `grep -vE` is.
NON_FUNCTIONAL = re.compile(
    r"^\.claude/|^docs/|\.md$|^LICENSE$|^\.gitignore$|^\.gitattributes$"
    r"|^\.editorconfig$"
)

#: Tried in order when `--base` names nothing. The first that resolves wins.
BASE_REF_CANDIDATES = ("origin/current", "origin/main", "current", "main")

LANE_ORDER = ("black", "flake8", "fast", "full")

#: The highest POSIX signal number; a code past it is an NTSTATUS, not a signal.
MAX_SIGNAL = 64

#: Shell convention: a process killed by signal N reports 128 + N.
SIGNAL_EXITS = {
    130: "SIGINT",
    134: "SIGABRT",
    137: "SIGKILL",
    139: "SIGSEGV",
    143: "SIGTERM",
}

#: An NTSTATUS crash code reaches a caller signed or unsigned; both forms here.
WINDOWS_CRASH_EXITS = {
    3221225477: "access violation",
    -1073741819: "access violation",
    3221225725: "stack overflow",
    -1073741571: "stack overflow",
}

#: pytest's published exit codes. Named so a red lane says what kind of red.
PYTEST_EXITS = {
    1: "tests failed",
    2: "interrupted",
    3: "internal error",
    4: "usage error",
    5: "no tests collected",
}

_GIT_EXE = shutil.which("git")


def run_git(*args: str) -> tuple[int, str]:
    """Run git in `REPO` and return (returncode, stripped stdout).

    Returns 127 when `_GIT_EXE` is None, which no empty output can look like.
    """
    if _GIT_EXE is None:
        return 127, ""
    try:
        done = subprocess.run(
            [_GIT_EXE, *args],
            cwd=REPO,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return 127, ""
    return done.returncode, done.stdout.strip()


def lint_targets() -> list[str]:
    """The `src tests tools *.py` argument list, with the glob expanded.

    The three directories are passed whether or not they exist, as ci.yml does.
    """
    return ["src", "tests", "tools"] + sorted(p.name for p in REPO.glob("*.py"))


def lane_command(name: str) -> list[str]:
    """The argv for one lane, matching the step of the same name in ci.yml."""
    if name == "black":
        return [sys.executable, "-m", "black", "--check", "--diff", *lint_targets()]
    if name == "flake8":
        return [sys.executable, "-m", "flake8", *lint_targets()]
    if name == "fast":
        return [
            sys.executable,
            "-m",
            "pytest",
            "-n",
            str(XDIST_WORKERS),
            "-m",
            "not slow and not archetype",
            "-q",
        ]
    if name == "full":
        return [
            sys.executable,
            "-m",
            "pytest",
            "-n",
            str(XDIST_WORKERS),
            "-m",
            "slow or archetype",
            "-q",
        ]
    raise ValueError(f"unknown lane {name!r}; known lanes are {', '.join(LANE_ORDER)}")


@dataclass(frozen=True)
class ExitVerdict:
    """A lane's return code, normalized, with whether it counts as a pass."""

    code: int
    passed: bool
    detail: str


def interpret_exit(
    returncode: int, *, is_pytest: bool = False, timed_out: bool = False
) -> ExitVerdict:
    """Return the `ExitVerdict` for a lane's `returncode`.

    A negative code down to `-MAX_SIGNAL` normalizes to 128 + signal;
    `timed_out` reports 143 and never passes.
    """
    if timed_out:
        return ExitVerdict(143, False, "timed out and was killed (143 SIGTERM)")
    code = returncode
    if -MAX_SIGNAL <= returncode < 0:
        code = 128 + (-returncode)
    if code == 0:
        return ExitVerdict(0, True, "ok")
    if code in SIGNAL_EXITS:
        return ExitVerdict(
            code,
            False,
            f"killed by {SIGNAL_EXITS[code]} ({code}); a crash prints no "
            "failure summary",
        )
    if code in WINDOWS_CRASH_EXITS:
        return ExitVerdict(
            code,
            False,
            f"crashed: {WINDOWS_CRASH_EXITS[code]} ({code}); a crash prints no "
            "failure summary",
        )
    if is_pytest and code in PYTEST_EXITS:
        return ExitVerdict(code, False, f"{PYTEST_EXITS[code]} ({code})")
    return ExitVerdict(code, False, f"exit {code}")


def functional_files(changed: Iterable[str]) -> list[str]:
    """The changed paths ci.yml's `changes` job counts as able to affect a build."""
    return [path for path in changed if path and not NON_FUNCTIONAL.search(path)]


def status_paths(porcelain: str) -> list[str]:
    """Paths out of `git status --porcelain` output, both ends of a rename."""
    paths: list[str] = []
    for line in porcelain.splitlines():
        if len(line) < 4:
            continue
        entry = line[3:]
        if " -> " in entry:
            before, after = entry.split(" -> ", 1)
            paths.extend((before.strip('"'), after.strip('"')))
        else:
            paths.append(entry.strip('"'))
    return [path for path in paths if path]


def resolve_base(explicit: str | None) -> str | None:
    """The first base ref that exists, or None when none does."""
    candidates = (explicit,) if explicit else BASE_REF_CANDIDATES
    for ref in candidates:
        code, out = run_git("rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
        if code == 0 and out:
            return ref
    return None


@dataclass(frozen=True)
class ChangeSet:
    """What the branch changes, and whether that means the code lanes run."""

    paths: tuple[str, ...]
    functional: tuple[str, ...]
    run_code_lanes: bool
    reason: str


def classify_changes(paths: Sequence[str] | None, unmeasured: str = "") -> ChangeSet:
    """Return the `ChangeSet` deciding whether the code lanes run.

    An `unmeasured` diff runs every lane, as ci.yml's `changes` job does.
    """
    if unmeasured:
        return ChangeSet((), (), True, f"{unmeasured}; running every lane")
    measured = tuple(paths or ())
    if not measured:
        return ChangeSet((), (), False, "no files changed; nothing to verify")
    code_files = tuple(functional_files(measured))
    if code_files:
        return ChangeSet(
            measured,
            code_files,
            True,
            f"{len(code_files)} of {len(measured)} changed files are functional",
        )
    return ChangeSet(
        measured,
        (),
        False,
        f"all {len(measured)} changed files are non-functional; code lanes skipped",
    )


def read_changes(base: str | None) -> ChangeSet:
    """Measure this branch against `resolve_base`, plus the dirty tree.

    `status_paths` adds the uncommitted and untracked files to the count.
    """
    ref = resolve_base(base)
    if ref is None:
        return classify_changes(None, unmeasured="no base ref resolved")
    code, merge_base = run_git("merge-base", ref, "HEAD")
    if code != 0 or not merge_base:
        return classify_changes(None, unmeasured=f"no merge base with {ref}")
    code, diff = run_git("diff", "--name-only", merge_base, "HEAD")
    if code != 0:
        return classify_changes(None, unmeasured=f"git diff against {ref} failed")
    paths = set(diff.splitlines())
    code, porcelain = run_git("status", "--porcelain", "--untracked-files=all")
    if code != 0:
        return classify_changes(None, unmeasured="git status failed")
    paths.update(status_paths(porcelain))
    return classify_changes(sorted(path for path in paths if path))


@dataclass(frozen=True)
class LaneResult:
    """One lane's outcome, carrying the code so a silent crash still reports."""

    name: str
    verdict: ExitVerdict
    seconds: float


def run_lane(name: str, timeout: int | None) -> LaneResult:
    """Run one lane to completion and read its return code."""
    argv = lane_command(name)
    is_pytest = name in ("fast", "full")
    print(f"[local-ci] lane {name}: {' '.join(argv[1:])}", flush=True)
    started = time.monotonic()
    try:
        done = subprocess.run(argv, cwd=REPO, check=False, timeout=timeout)
    except subprocess.TimeoutExpired:
        return LaneResult(
            name,
            interpret_exit(0, is_pytest=is_pytest, timed_out=True),
            time.monotonic() - started,
        )
    return LaneResult(
        name,
        interpret_exit(done.returncode, is_pytest=is_pytest),
        time.monotonic() - started,
    )


def report(
    changes: ChangeSet, results: Sequence[LaneResult], skipped: Sequence[str]
) -> int:
    """Print one line per lane and one verdict; return the process exit code."""
    print()
    print(f"[local-ci] changes: {changes.reason}")
    for name in skipped:
        print(f"[local-ci] {name:<7} SKIP")
    for result in results:
        state = "PASS" if result.verdict.passed else "FAIL"
        print(
            f"[local-ci] {result.name:<7} {state} "
            f"{result.seconds:7.1f}s  {result.verdict.detail}"
        )
    failed = [result.name for result in results if not result.verdict.passed]
    if failed:
        print(f"[local-ci] VERDICT: FAILED - {', '.join(failed)}")
        return 1
    print(f"[local-ci] VERDICT: PASSED - {len(results)} lane(s) ran, 0 failed")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """The command line: which lanes, which base, and the hang ceiling."""
    parser = argparse.ArgumentParser(
        prog="python -m tools.local_ci",
        description="Run the ci.yml lanes locally. GitHub Actions no longer does.",
    )
    parser.add_argument(
        "--lane",
        action="append",
        choices=LANE_ORDER,
        metavar="NAME",
        help=f"run only this lane; repeatable. One of: {', '.join(LANE_ORDER)}",
    )
    parser.add_argument(
        "--base",
        default=None,
        help="base ref for the diff; default is the first of "
        + ", ".join(BASE_REF_CANDIDATES)
        + " that exists",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="run the lanes even when only non-functional files changed",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=(
            "seconds before a lane is treated as hung "
            f"(default {DEFAULT_TIMEOUT_SECONDS})"
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Select the lanes, run them, print the verdict, return the exit code."""
    args = build_parser().parse_args(argv)
    wanted = tuple(args.lane) if args.lane else LANE_ORDER
    ordered = tuple(name for name in LANE_ORDER if name in wanted)

    changes = read_changes(args.base)
    if not args.all and not changes.run_code_lanes:
        return report(changes, (), ordered)

    results = [run_lane(name, args.timeout) for name in ordered]
    return report(changes, results, ())


if __name__ == "__main__":
    raise SystemExit(main())
