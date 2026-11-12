"""`resolve_citation` reads one "path, in symbol" line.

It returns RESOLVED, NOT_GROUNDED or REJECTED, with a reason.
"""

import argparse
import ast
import json
import re
import sys
from collections.abc import Iterator
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

RESOLVED = "RESOLVED"
NOT_GROUNDED = "NOT_GROUNDED"
REJECTED = "REJECTED"

_SEPARATOR = ", in "
_NOT_THE_FORM = "not the form <path>, in <symbol>"
_SEGMENT = re.compile(r"[A-Za-z0-9_.-]+")
_LINE_NUMBER = re.compile(r":\d")
_DRIVE = re.compile(r"[A-Za-z]:")
_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


def _form_fault(citation: str) -> str | None:
    """Return why `citation` is outside the input form, or None when it fits."""
    if "\\" in citation:
        return "backslash"
    if _LINE_NUMBER.search(citation):
        return "line number"
    if _SEPARATOR not in citation:
        return _NOT_THE_FORM
    path, symbol = citation.split(_SEPARATOR, 1)
    if _DRIVE.match(path):
        return "drive letter"
    if path.startswith("/"):
        return "absolute path"
    segments = path.split("/")
    if ".." in segments:
        return "path holds .."
    if not all(_SEGMENT.fullmatch(part) and part != "." for part in segments):
        return _NOT_THE_FORM
    if not path.endswith(".py"):
        return "file type other than .py"
    if not all(part.isidentifier() for part in symbol.split(".")):
        return _NOT_THE_FORM
    return None


def _walk_exact(root: Path, parts: list[str]) -> str | None:
    """Return None when `parts` names a file under `root` in exact letter case.

    Otherwise return why not.
    """
    here = root
    case_differs = False
    for part in parts:
        try:
            names = {entry.name for entry in here.iterdir()}
        except OSError:
            return "file missing"
        matches = sorted(name for name in names if name.casefold() == part.casefold())
        if not matches:
            return "file missing"
        if part not in names:
            case_differs = True
        here = here / (part if part in names else matches[0])
    if not here.is_file():
        return "file missing"
    return "letter case differs" if case_differs else None


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
        elif not rest and isinstance(node, ast.ClassDef):
            if head in _bound_names(stmt):
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


def resolve_citation(citation: str, root: Path) -> tuple[str, str]:
    """Return the verdict for one `citation`, read against the files under `root`.

    The second item is the `reason` that `main` prints.
    """
    fault = _form_fault(citation)
    if fault:
        return REJECTED, fault
    path, symbol = citation.split(_SEPARATOR, 1)
    parts = path.split("/")
    missing = _walk_exact(root, parts)
    if missing:
        return NOT_GROUNDED, missing
    target = root.joinpath(*parts)
    if not target.resolve().is_relative_to(root.resolve()):
        return REJECTED, "path outside the repository"
    try:
        tree = ast.parse(target.read_bytes())
    except OSError:
        return NOT_GROUNDED, "file unreadable"
    except (SyntaxError, ValueError, RecursionError):
        return NOT_GROUNDED, "file does not parse"
    if _defines(tree, symbol.split(".")):
        return RESOLVED, "the file defines it"
    return NOT_GROUNDED, "nothing in the file defines it"


def main(argv: list[str] | None = None) -> int:
    """Print one JSON verdict per citation line in `file`.

    Return 0 only when every citation reads RESOLVED, and 1 otherwise.
    """
    parser = argparse.ArgumentParser(
        prog="python -m dev_harness.sigils.cite_symbol",
        description="Resolve one 'path, in symbol' citation per line.",
    )
    parser.add_argument("file", type=Path, help="one citation per line")
    args = parser.parse_args(argv)
    try:
        lines = args.file.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        print(f"cannot read {args.file}: {exc}", file=sys.stderr)
        return 1
    read = 0
    resolved = 0
    for number, raw in enumerate(lines, start=1):
        citation = raw.strip()
        if not citation or citation.startswith("#"):
            continue
        verdict, reason = resolve_citation(citation, REPO_ROOT)
        read += 1
        if verdict == RESOLVED:
            resolved += 1
        row = {"line": number, "citation": citation, "verdict": verdict}
        row["reason"] = reason
        print(json.dumps(row))
    if read == 0:
        print(f"no citation in {args.file}", file=sys.stderr)
    return 0 if read and resolved == read else 1


if __name__ == "__main__":
    sys.exit(main())
