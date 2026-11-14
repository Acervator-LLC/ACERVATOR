"""`main` reads each `CASES_FILE` case through every `coding_sigils` module, before and after its fix commit."""

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import ModuleType
from typing import Any

from .coding_input import SEPARATOR, locate
from .coding_partition import FactsFault, coding_sigils, selection
from .core import discipline_fault, repository_root, tool_text

REPO = repository_root(Path(__file__).resolve().parent) or Path.cwd()
CASES_FILE = REPO / "harness_fixtures" / "ocir_cases" / "cases.txt"
GIT_TIMEOUT_S = 600
SOURCE_SUFFIXES = (".py", ".pyi")
SETTINGS_FILES = frozenset(
    {
        ".bandit",
        ".flake8",
        ".gitignore",
        ".mypy.ini",
        ".ruff.toml",
        ".semgrepignore",
        "mypy.ini",
        "pyproject.toml",
        "pyrightconfig.json",
        "ruff.toml",
        "setup.cfg",
        "tox.ini",
    }
)
HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
READ = "read"
UNREAD = "unread"
FAULT = "fault"


class CaseFault(Exception):
    """A case line, a git call, or a restored file's bytes did not hold."""


@dataclass(frozen=True)
class Case:
    """One `CASES_FILE` line: catalogue `row`, fix `commit`, file `path` and `symbol`."""

    row: str
    commit: str
    path: str
    symbol: str

    @property
    def text(self) -> str:
        """The `path, in symbol` input line for this case."""
        return f"{self.path}{SEPARATOR}{self.symbol}"


def load(path: Path = CASES_FILE) -> list[Case]:
    """Return each four-field line of `path` as a `Case`; a short or long line raises `CaseFault`."""
    cases = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        fields = line.split()
        if len(fields) != len(Case.__dataclass_fields__):
            message = f"{path.name} line {number}: {len(fields)} fields, not row commit path symbol"
            raise CaseFault(message)
        cases.append(Case(*fields))
    return cases


def git(*args: str, cwd: Path = REPO, stdin: bytes | None = None) -> bytes:
    """Return the stdout of `git args` run in `cwd`; a non-zero exit raises `CaseFault`."""
    proc = subprocess.run(
        ["git", *args],
        cwd=cwd,
        input=stdin,
        capture_output=True,
        timeout=GIT_TIMEOUT_S,
        check=False,
    )
    if proc.returncode != 0:
        message = f"git {' '.join(args[:3])} exited {proc.returncode}: {tool_text(proc.stderr)}"
        raise CaseFault(message)
    return proc.stdout


def kept(name: str) -> bool:
    """Report whether a tree path `name` is Python source or one of `SETTINGS_FILES`."""
    pure = PurePosixPath(name)
    return pure.suffix in SOURCE_SUFFIXES or pure.name in SETTINGS_FILES


@contextmanager
def restored(commit: str, case_path: str) -> Iterator[Path]:
    """Yield a detached worktree of `commit` holding its `kept` files, `case_path` checked against `git show`."""
    folder = Path(tempfile.mkdtemp(prefix="ocir_case_"))
    try:
        git("worktree", "add", "--no-checkout", "--detach", str(folder), commit)
    except CaseFault:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    try:
        listed = tool_text(git("ls-tree", "-r", "-z", "--name-only", commit)).split(
            "\0"
        )
        names = "\0".join(name for name in listed if name and kept(name)).encode(
            "utf-8"
        )
        git(
            "-c",
            "core.autocrlf=false",
            "checkout",
            commit,
            "--pathspec-from-file=-",
            "--pathspec-file-nul",
            cwd=folder,
            stdin=names,
        )
        git("diff", "--quiet", cwd=folder)
        shown = git("show", f"{commit}:{case_path}")
        if (folder / case_path).read_bytes() != shown:
            message = f"{commit}:{case_path} on disk differs from git show"
            raise CaseFault(message)
        yield folder
    finally:
        git("worktree", "remove", "--force", str(folder))
        shutil.rmtree(folder, ignore_errors=True)


def changed(commit: str, path: str) -> tuple[set[int], set[int]]:
    """Return the lines `commit` changed in `path`: its parent's side, then its own side."""
    before: set[int] = set()
    after: set[int] = set()
    diff = tool_text(git("diff", "-U0", f"{commit}^", commit, "--", path))
    for line in diff.splitlines():
        hunk = HUNK.match(line)
        if hunk:
            old, old_count, new, new_count = (
                int(value) if value is not None else 1 for value in hunk.groups()
            )
            before.update(range(old, old + old_count))
            after.update(range(new, new + new_count))
    return before, after


def span(case: Case, root: Path) -> set[int]:
    """Return the lines of `case.symbol` in `root`, or none when that side defines no such symbol."""
    located = locate(case.text, root)
    if isinstance(located, str):
        return set()
    first, last = located[2]
    return set(range(first, last + 1))


def rule_of(item: Any) -> str:
    """Return the `tool rule` id of one `findings` item: a ruff pair or a sigil's `Finding`."""
    if isinstance(item, tuple):
        return f"ruff {item[0]}"
    if hasattr(item, "kind"):
        return "vulture dead-code"
    tool = getattr(item, "tool", "ruff")
    return f"{tool} {getattr(item, 'code', None) or item.rule}"


def line_of(item: Any) -> int:
    """Return the line of one `findings` item."""
    return int(item[1] if isinstance(item, tuple) else item.line)


def read_side(
    module: ModuleType, root: Path, path: str, site: set[int]
) -> dict[str, Any]:
    """Return `module`'s refusal or fault for `path` under `root`, else its rule ids at `site` and its file count."""
    sigil = module.SIGIL
    refusal = (
        discipline_fault(sigil) or sigil.data_type(path) or sigil.content(path, root)
    )
    if refusal:
        return {"refused": refusal}
    faults = (module.ToolFault, FactsFault, OSError, subprocess.SubprocessError)
    try:
        found = module.findings(path, root, selection(path, root, module.CAN_RUN))[1]
    except faults as exc:
        return {"fault": repr(exc)}
    at_site = sorted(rule_of(item) for item in found if line_of(item) in site)
    return {"site": at_site, "file": len(found)}


def compare(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """Return both sides of one sigil and the rule ids its `site` holds before and not after."""
    if "site" not in before or "site" not in after:
        return {"before": before, "after": after}
    lost = Counter(before["site"]) - Counter(after["site"])
    return {"before": before, "after": after, "read": sorted(lost.elements())}


def verdict_of(readings: dict[str, Any]) -> str:
    """Return `READ` when any sigil reads a rule, `FAULT` when one faulted, else `UNREAD`."""
    if any(reading.get("read") for reading in readings.values()):
        return READ
    sides = [
        side
        for reading in readings.values()
        for side in (reading["before"], reading["after"])
    ]
    return FAULT if any("fault" in side for side in sides) else UNREAD


def read_case(
    case: Case, sigils: list[ModuleType], *, same_commit: bool
) -> dict[str, Any]:
    """Return each sigil's site rules before and after `case.commit`, and the row's verdict."""
    old_lines, new_lines = changed(case.commit, case.path)
    with restored(case.commit, case.path) as after_root:
        after_span = span(case, after_root)
        after_site = new_lines & after_span if after_span else new_lines
        after = {
            m.SIGIL.name: read_side(m, after_root, case.path, after_site)
            for m in sigils
        }
    before, before_site = after, after_site
    if not same_commit:
        with restored(f"{case.commit}^", case.path) as before_root:
            before_site = old_lines & span(case, before_root)
            before = {
                m.SIGIL.name: read_side(m, before_root, case.path, before_site)
                for m in sigils
            }
    readings = {name: compare(before[name], after[name]) for name in before}
    return {
        "row": case.row,
        "commit": case.commit,
        "input": case.text,
        "same_commit": same_commit,
        "site_lines": {"before": len(before_site), "after": len(after_site)},
        "verdict": verdict_of(readings),
        "sigils": readings,
    }


def main(argv: list[str] | None = None) -> int:
    """Print one JSON reading per case; exit 1 on a fault, or on a read row under `--same-commit`."""
    parser = argparse.ArgumentParser(
        description="Read each case of the case list, before and after its fix."
    )
    parser.add_argument("--cases", type=Path, default=CASES_FILE, help="the case list")
    parser.add_argument(
        "--row", action="append", help="read only this catalogue row; repeat for more"
    )
    parser.add_argument(
        "--same-commit",
        action="store_true",
        help="read both sides from the fix commit, so no row can read",
    )
    args = parser.parse_args(argv)
    try:
        cases = [c for c in load(args.cases) if not args.row or c.row in args.row]
    except (OSError, CaseFault) as exc:
        print(f"cannot read the case list: {exc}", file=sys.stderr)
        return 1
    sigils = coding_sigils()
    verdicts: Counter[str] = Counter()
    for case in cases:
        started = time.monotonic()
        try:
            reading = read_case(case, sigils, same_commit=args.same_commit)
        except CaseFault as exc:
            reading = {
                "row": case.row,
                "input": case.text,
                "verdict": FAULT,
                "fault": str(exc),
            }
        reading["seconds"] = round(time.monotonic() - started, 1)
        verdicts[reading["verdict"]] += 1
        print(json.dumps(reading), flush=True)
    print(json.dumps({"cases": len(cases), **verdicts}), flush=True)
    if verdicts[FAULT] or (args.same_commit and verdicts[READ]):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
