"""Citation rules: tier 1 in `data_type_fault`, tier 3 in `definition_verdict`."""

import ast
import re
from collections.abc import Callable, Iterator
from pathlib import Path

RESOLVED = "RESOLVED"
NOT_GROUNDED = "NOT_GROUNDED"
REJECTED = "REJECTED"

SETTINGS: dict[str, str] = {"separator": ", in "}

BACKSLASH = "backslash"
LINE_NUMBER = "line number"
NOT_THE_FORM = f"not the form <path>{SETTINGS['separator']}<symbol>"
DRIVE_LETTER = "drive letter"
ABSOLUTE_PATH = "absolute path"
PARENT_SEGMENT = "path holds .."
FILE_MISSING = "file missing"
CASE_DIFFERS = "letter case differs"
UNREADABLE = "file unreadable"
UNPARSED = "file does not parse"
UNDEFINED = "nothing in the file defines it"
DEFINED = "the file defines it"

DATA_TYPE_REJECTS = (
    BACKSLASH,
    LINE_NUMBER,
    NOT_THE_FORM,
    DRIVE_LETTER,
    ABSOLUTE_PATH,
    PARENT_SEGMENT,
)
SEARCH_RUNS = ("the exact-case walk", "the parse", "the search for the definition")
SEARCH_NOT_GROUNDED = (FILE_MISSING, CASE_DIFFERS, UNREADABLE, UNPARSED, UNDEFINED)
SEARCH_RESOLVED = (DEFINED,)

_SEGMENT_RE = re.compile(r"[A-Za-z0-9_.-]+")
_LINE_NUMBER_RE = re.compile(r":\d")
_DRIVE_RE = re.compile(r"[A-Za-z]:")
_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)

Reader = Callable[[bytes, list[str]], bool | None]


def _scope_statements(node: ast.AST) -> Iterator[ast.stmt]:
    """Yield each statement in the scope of `node`.

    It enters `ast.If`, `ast.Try`, `ast.With` and loop blocks, never a `_SCOPES` body.
    """
    for child in ast.iter_child_nodes(node):
        if isinstance(child, ast.stmt):
            yield child
        if not isinstance(child, _SCOPES):
            yield from _scope_statements(child)


def _bound_names(stmt: ast.stmt) -> set[str]:
    """Return the names `stmt` defines.

    A `_SCOPES` node gives its name; `ast.Assign` and `ast.AnnAssign` give stored names.
    """
    if isinstance(stmt, _SCOPES):
        return {stmt.name}
    if isinstance(stmt, ast.Assign):
        targets = list(stmt.targets)
    elif isinstance(stmt, ast.AnnAssign):
        targets = [stmt.target]
    else:
        return set()
    return {
        node.id
        for target in targets
        for node in ast.walk(target)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store)
    }


def _nested(node: ast.AST, parts: list[str]) -> bool:
    """Report whether `parts` names a def or class chain inside `node`.

    The last of `parts` may also be an assignment in an `ast.ClassDef` body.
    """
    head, rest = parts[0], parts[1:]
    for stmt in _scope_statements(node):
        if isinstance(stmt, _SCOPES) and stmt.name == head:
            if not rest or _nested(stmt, rest):
                return True
        elif not rest and isinstance(node, ast.ClassDef) and head in _bound_names(stmt):
            return True
    return False


def _defines(tree: ast.Module, parts: list[str]) -> bool:
    """Report whether `tree` defines the symbol split into `parts`.

    A bare `name` needs a `_SCOPES` node at any depth, or a module-level assignment.
    """
    if len(parts) > 1:
        return _nested(tree, parts)
    name = parts[0]
    for node in ast.walk(tree):
        if isinstance(node, _SCOPES) and node.name == name:
            return True
    return any(name in _bound_names(stmt) for stmt in _scope_statements(tree))


def read_python(source: bytes, parts: list[str]) -> bool | None:
    """Return `_defines` for `parts` in `source`, or None when `ast.parse` fails."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError):
        return None
    return _defines(tree, parts)


READERS: dict[str, Reader] = {".py": read_python}


def file_type(path: str) -> str:
    """Return the last `path` segment's text from its last dot, or an empty string."""
    name = path.rsplit("/", 1)[-1]
    return "." + name.rsplit(".", 1)[1] if "." in name else ""


def data_type_fault(citation: str) -> str | None:
    """Return the tier 1 reason `citation` fails, or None when it fits."""
    if "\\" in citation:
        return BACKSLASH
    if _LINE_NUMBER_RE.search(citation):
        return LINE_NUMBER
    separator = SETTINGS["separator"]
    if separator not in citation:
        return NOT_THE_FORM
    path, symbol = citation.split(separator, 1)
    if _DRIVE_RE.match(path):
        return DRIVE_LETTER
    if path.startswith("/"):
        return ABSOLUTE_PATH
    segments = path.split("/")
    if ".." in segments:
        return PARENT_SEGMENT
    if not all(_SEGMENT_RE.fullmatch(part) and part != "." for part in segments):
        return NOT_THE_FORM
    if not all(part.isidentifier() for part in symbol.split(".")):
        return NOT_THE_FORM
    return None


def _walk_exact(root: Path, parts: list[str]) -> str | None:
    """Return None when `parts` names a file under `root` in exact letter case.

    Otherwise return `FILE_MISSING` or `CASE_DIFFERS`.
    """
    here = root
    case_differs = False
    for part in parts:
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


def definition_verdict(citation: str, root: Path) -> tuple[str, str]:
    """Return the tier 3 output and reason from `_walk_exact` and `READERS`."""
    path, symbol = citation.split(SETTINGS["separator"], 1)
    parts = path.split("/")
    missing = _walk_exact(root, parts)
    if missing:
        return NOT_GROUNDED, missing
    try:
        source = root.joinpath(*parts).read_bytes()
    except OSError:
        return NOT_GROUNDED, UNREADABLE
    defined = READERS[file_type(path)](source, symbol.split("."))
    if defined is None:
        return NOT_GROUNDED, UNPARSED
    if defined:
        return RESOLVED, DEFINED
    return NOT_GROUNDED, UNDEFINED
