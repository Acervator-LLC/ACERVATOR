"""The `OWNER` coding input: `INPUT_FORM`, `READERS`, tiers 1 and 2, and `locate`."""

import ast
import re
from collections.abc import Callable, Iterator
from pathlib import Path, PurePosixPath

from .core import TierCard, named_file

OWNER = "coding"
SEPARATOR = ", in "
INPUT_FORM = f"one line: <path>, or <path>{SEPARATOR}<symbol>"

BACKSLASH = "backslash"
LINE_NUMBER = "line number"
NOT_THE_FORM = f"not the form <path> or <path>{SEPARATOR}<symbol>"
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
    path, separator, symbol = text.partition(SEPARATOR)
    return path, symbol.split(".") if separator else []


def data_type_fault(text: str) -> str | None:
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


def locate(text: str, root: Path) -> tuple[Path, bytes, Span] | str:
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


def content_fault(text: str, root: Path) -> str | None:
    """Return the tier 2 reason `locate` gives for `text` under `root`, or None."""
    located = locate(text, root)
    return located if isinstance(located, str) else None


def fault_file(text: str, root: Path) -> Path | None:
    """Return `named_file` for `text`, by `data_type_fault` and `SEPARATOR`."""
    return named_file(text, root, data_type_fault, SEPARATOR)


DATA_TYPE_TIER: TierCard = {
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
}

CONTENT_TIER: TierCard = {
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
}
