"""`SIGIL` is CODE.OPTIMIZE on the `core` card; `optimize` judges one input line."""

import ast
import json
import re
import subprocess
import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from functools import cache
from pathlib import Path, PurePosixPath

from .core import FLAGS, Flag, FlagRow, Sigil, Verdict, judge, main

CLEAN = "CLEAN"
OPTIMIZABLE = "OPTIMIZABLE"
REJECTED = "REJECTED"

RUFF_BUILT = "0.16.0"
RUFF_TIMEOUT_S = 120
FAMILIES = ("PERF", "SIM", "C4", "UP", "FURB", "PLR17", "C901")
FIX_CLASSES = {"Always": "always", "Sometimes": "sometimes", "None": "none"}
FOLLOW_ON = {
    "always": "apply ruff's fix for that rule and read the file again",
    "sometimes": "the same, where ruff offers it for that line",
    "none": "a unit of work",
}

SETTINGS: dict[str, str] = {
    "separator": ", in ",
    "ruff_version": RUFF_BUILT,
    "rule_families": ", ".join(FAMILIES),
    "ruff_config": "the one ruff finds from the folder of the file: "
    "its target version, preview and complexity limit",
}

BACKSLASH = "backslash"
LINE_NUMBER = "line number"
NOT_THE_FORM = f"not the form <path> or <path>{SETTINGS['separator']}<symbol>"
DRIVE_LETTER = "drive letter"
ABSOLUTE_PATH = "absolute path"
PARENT_SEGMENT = "path holds .."
OUTSIDE_ROOT = "path outside the target tree"
FILE_MISSING = "file missing"
CASE_DIFFERS = "letter case differs"
UNREADABLE = "file unreadable"
UNPARSED = "file does not parse"
NO_SCOPE = "nothing in the file defines it as a def or class"

_SEGMENT_RE = re.compile(r"[A-Za-z0-9_.-]+")
_LINE_NUMBER_RE = re.compile(r":\d")
_DRIVE_RE = re.compile(r"[A-Za-z]:")
_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)

Span = tuple[int, int]
Reader = Callable[[bytes, list[str]], Span | str]


class ToolFault(Exception):
    """`python -m ruff` did not run, or printed output `_ruff_findings` cannot read."""


@dataclass(frozen=True)
class Finding:
    """One ruff finding: rule `code`, rule `name`, `line` and `fix` class."""

    code: str
    name: str
    line: int
    fix: str


def _statements(node: ast.AST) -> Iterator[ast.stmt]:
    """Yield each statement in the scope of `node`, never entering a `_SCOPES` body."""
    for child in ast.iter_child_nodes(node):
        if isinstance(child, ast.stmt):
            yield child
        if not isinstance(child, _SCOPES):
            yield from _statements(child)


def _scope(tree: ast.Module, parts: list[str]) -> ast.AST | None:
    """Return the last `_SCOPES` node each of `parts` names inside the one before."""
    node: ast.AST = tree
    for part in parts:
        named = [
            stmt
            for stmt in _statements(node)
            if isinstance(stmt, _SCOPES) and stmt.name == part
        ]
        if not named:
            return None
        node = named[-1]
    return node


def read_python(source: bytes, parts: list[str]) -> Span | str:
    """Return the `parts` span in `source`, all lines when empty, or `NO_SCOPE`."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError):
        return UNPARSED
    if not parts:
        return 1, max(len(source.splitlines()), 1)
    scope = _scope(tree, parts)
    if not isinstance(scope, _SCOPES):
        return NO_SCOPE
    first = min([scope.lineno, *(item.lineno for item in scope.decorator_list)])
    return first, scope.end_lineno or scope.lineno


READERS: dict[str, Reader] = {".py": read_python}

NO_READER = f"file type other than {' or '.join(sorted(READERS))}"


def _split(text: str) -> tuple[str, list[str]]:
    """Return the path in `text` and its dotted symbol as parts, empty without one."""
    path, separator, symbol = text.partition(SETTINGS["separator"])
    return path, symbol.split(".") if separator else []


def _data_type_fault(text: str) -> str | None:
    """Return the tier 1 reason `text` fails, or None when it fits."""
    if "\\" in text:
        return BACKSLASH
    if _LINE_NUMBER_RE.search(text):
        return LINE_NUMBER
    path, parts = _split(text)
    if _DRIVE_RE.match(path):
        return DRIVE_LETTER
    if path.startswith("/"):
        return ABSOLUTE_PATH
    segments = path.split("/")
    if ".." in segments:
        return PARENT_SEGMENT
    if not all(_SEGMENT_RE.fullmatch(part) and part != "." for part in segments):
        return NOT_THE_FORM
    if not all(part.isidentifier() for part in parts):
        return NOT_THE_FORM
    return None


def _walk_exact(root: Path, segments: list[str]) -> str | None:
    """Return None if `segments` is a file in `root` in exact case, or the fault."""
    here = root
    case_differs = False
    for part in segments:
        try:
            names = {entry.name for entry in here.iterdir()}
        except OSError:
            return FILE_MISSING
        matches = sorted(name for name in names if name.casefold() == part.casefold())
        if not matches:
            return FILE_MISSING
        if part not in names:
            case_differs = True
        here = here / (part if part in names else matches[0])
    if not here.is_file():
        return FILE_MISSING
    return CASE_DIFFERS if case_differs else None


def _locate(text: str, root: Path) -> tuple[Path, bytes, Span] | str:
    """Return the file `text` names in `root`, its bytes and span, or a tier 2 fault."""
    path, parts = _split(text)
    segments = path.split("/")
    if not root.joinpath(*segments).resolve().is_relative_to(root.resolve()):
        return OUTSIDE_ROOT
    reader = READERS.get(PurePosixPath(path).suffix)
    if reader is None:
        return NO_READER
    fault = _walk_exact(root, segments)
    if fault:
        return fault
    file = root.joinpath(*segments)
    try:
        source = file.read_bytes()
    except OSError:
        return UNREADABLE
    span = reader(source, parts)
    if isinstance(span, str):
        return span
    return file, source, span


def _content_fault(text: str, root: Path) -> str | None:
    """Return the tier 2 reason `_locate` gives for `text` under `root`, or None."""
    located = _locate(text, root)
    return located if isinstance(located, str) else None


def _said(proc: subprocess.CompletedProcess[bytes]) -> str:
    """Return the stderr of `proc`, else its stdout, decoded and stripped."""
    return (proc.stderr or proc.stdout).decode("utf-8", "replace").strip()


@cache
def ruff_version() -> str:
    """Return the version `python -m ruff --version` prints, or raise `ToolFault`."""
    try:
        proc = subprocess.run(
            [sys.executable, "-P", "-m", "ruff", "--version"],
            capture_output=True,
            timeout=RUFF_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ToolFault(f"ruff --version: {exc}") from exc
    words = proc.stdout.decode("utf-8", "replace").split()
    if proc.returncode != 0 or len(words) != 2 or words[0] != "ruff":
        raise ToolFault(f"ruff --version exited {proc.returncode}: {_said(proc)}")
    return words[1]


@cache
def fix_classes() -> dict[str, str]:
    """Return each rule code's `FIX_CLASSES` value from `python -m ruff rule --all`."""
    try:
        proc = subprocess.run(
            [
                sys.executable,
                "-P",
                "-m",
                "ruff",
                "rule",
                "--all",
                "--output-format",
                "json",
            ],
            capture_output=True,
            timeout=RUFF_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ToolFault(f"ruff rule --all: {exc}") from exc
    if proc.returncode != 0:
        raise ToolFault(f"ruff rule --all exited {proc.returncode}: {_said(proc)}")
    try:
        return {
            rule["code"]: FIX_CLASSES[rule["fix_availability"]]
            for rule in json.loads(proc.stdout)
        }
    except (ValueError, KeyError, TypeError) as exc:
        raise ToolFault(f"ruff rule --all printed an unreadable rule: {exc}") from exc


def _ruff_findings(source: bytes, folder: Path) -> list[Finding]:
    """Return each `FAMILIES` `Finding` for `source` on stdin, run from `folder`."""
    try:
        proc = subprocess.run(
            [
                sys.executable,
                "-P",
                "-m",
                "ruff",
                "check",
                "--no-cache",
                "--output-format",
                "json",
                "--select",
                "PERF,SIM,C4,UP,FURB,PLR17,C901",
                "-",
            ],
            input=source,
            cwd=folder,
            capture_output=True,
            timeout=RUFF_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ToolFault(f"ruff check: {exc}") from exc
    if proc.returncode not in {0, 1}:
        raise ToolFault(f"ruff check exited {proc.returncode}: {_said(proc)}")
    classes = fix_classes()
    try:
        return [
            Finding(
                row["code"], row["name"], row["location"]["row"], classes[row["code"]]
            )
            for row in json.loads(proc.stdout)
            if isinstance(row["code"], str) and row["code"].startswith(FAMILIES)
        ]
    except (ValueError, KeyError, TypeError) as exc:
        raise ToolFault(f"ruff check printed an unreadable finding: {exc}") from exc


def _functions_verdict(text: str, root: Path) -> tuple[str, str]:
    """Return `CLEAN`, or `OPTIMIZABLE` with each `Finding` in the `_locate` span."""
    located = _locate(text, root)
    if isinstance(located, str):
        raise ToolFault(f"{text}: {located}, after tier 2 accepted it")
    file, source, (first, last) = located
    findings = [
        finding
        for finding in _ruff_findings(source, file.parent)
        if first <= finding.line <= last
    ]
    version = f"ruff {ruff_version()}"
    if not findings:
        return CLEAN, f"{version}: no rule in {SETTINGS['rule_families']} fires"
    rows = "; ".join(
        f"{item.code} {item.name} line {item.line} fix {item.fix}" for item in findings
    )
    return OPTIMIZABLE, f"{version}: {rows}"


SIGIL = Sigil(
    name="CODE.OPTIMIZE",
    edition=1,
    owner="coding",
    input_form=f"one line: <path>, or <path>{SETTINGS['separator']}<symbol>",
    settings=SETTINGS,
    tiers=(
        {
            "accepts": "a relative path in forward slashes and name characters, "
            "and an optional dotted symbol of identifiers",
            "rejects": [
                BACKSLASH,
                LINE_NUMBER,
                NOT_THE_FORM,
                DRIVE_LETTER,
                ABSOLUTE_PATH,
                PARENT_SEGMENT,
            ],
        },
        {
            "accepts": "a file of a type in readers, inside the target tree, "
            "in exact letter case, that parses; a symbol names a def or class in it",
            "rejects": [
                OUTSIDE_ROOT,
                NO_READER,
                FILE_MISSING,
                CASE_DIFFERS,
                UNREADABLE,
                UNPARSED,
                NO_SCOPE,
            ],
        },
        {
            "runs": [
                "python -m ruff check --select with the rule families, "
                "the file on standard input, from the folder of the file",
                "for a symbol, only the findings inside its lines",
                "python -m ruff rule --all, for the fix class of each rule",
            ],
            "clean": "no rule in the rule families fires",
            "optimizable": ["rule id", "rule name", "line", "fix class"],
            "fix_classes": list(FOLLOW_ON),
            "not_read": "a ruff setting matched on the file name, such as "
            "per-file-ignores, because the file reaches ruff on standard input",
        },
    ),
    outputs={
        CLEAN: FlagRow(Flag.PASS),
        OPTIMIZABLE: FlagRow(Flag.OPTIMIZE),
    },
    refusal=REJECTED,
    follows={
        Flag.OPTIMIZE: FLAGS[Flag.OPTIMIZE]["follows"]
        + "; by fix class: "
        + "; ".join(f"{fix} -> {rule}" for fix, rule in FOLLOW_ON.items()),
    },
    readers=READERS,
    data_type=_data_type_fault,
    content=_content_fault,
    functions=_functions_verdict,
)


def optimize(text: str, root: Path) -> Verdict:
    """Return the `judge` verdict of `SIGIL` for one input line under `root`."""
    return judge(SIGIL, text, root, in_source=False)


def run(argv: list[str] | None = None) -> int:
    """Return `main` for `SIGIL`, or 1 with the `ToolFault` on stderr."""
    try:
        return main(SIGIL, argv)
    except ToolFault as exc:
        print(f"ruff did not run: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(run())
