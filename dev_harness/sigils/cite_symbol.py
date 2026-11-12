"""`resolve_citation` filters one citation through the three tiers in `CARD`."""

import argparse
import ast
import json
import re
import sys
from collections.abc import Callable, Iterator
from pathlib import Path

RESOLVED = "RESOLVED"
NOT_GROUNDED = "NOT_GROUNDED"
REJECTED = "REJECTED"

SETTINGS: dict[str, str] = {"separator": ", in "}

DATA_TYPE = "tier 1 data type"
CONTENT = "tier 2 content compatibility"
FUNCTIONS = "tier 3 required processing functions"

BACKSLASH = "backslash"
LINE_NUMBER = "line number"
NOT_THE_FORM = f"not the form <path>{SETTINGS['separator']}<symbol>"
DRIVE_LETTER = "drive letter"
ABSOLUTE_PATH = "absolute path"
PARENT_SEGMENT = "path holds .."
OUTSIDE_ROOT = "path outside the target tree"
FILE_MISSING = "file missing"
CASE_DIFFERS = "letter case differs"
UNREADABLE = "file unreadable"
UNPARSED = "file does not parse"
UNDEFINED = "nothing in the file defines it"
DEFINED = "the file defines it"

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


def read_python(source: bytes, parts: list[str]) -> bool | None:
    """Return `_defines` for `parts` in `source`, or None when `ast.parse` fails."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError):
        return None
    return _defines(tree, parts)


READERS: dict[str, Reader] = {".py": read_python}

NO_READER = f"file type other than {' or '.join(sorted(READERS))}"

CARD: dict[str, object] = {
    "sigil": "CITE.SYMBOL",
    "edition": 2,
    "owner": "truth",
    "input": f"one line: <path>{SETTINGS['separator']}<symbol>",
    "settings": SETTINGS,
    "tiers": [
        {
            "name": DATA_TYPE,
            "accepts": "a relative path in forward slashes and name characters, "
            "and a dotted symbol of identifiers",
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
            "name": CONTENT,
            "accepts": "a path inside the target tree, of a file type in readers",
            "rejects": [OUTSIDE_ROOT, NO_READER],
        },
        {
            "name": FUNCTIONS,
            "runs": [
                "the exact-case walk",
                "the parse",
                "the search for the definition",
            ],
            "not_grounded": [
                FILE_MISSING,
                CASE_DIFFERS,
                UNREADABLE,
                UNPARSED,
                UNDEFINED,
            ],
            "resolved": [DEFINED],
        },
    ],
    "outputs": [RESOLVED, NOT_GROUNDED],
    "refusal": REJECTED,
    "readers": sorted(READERS),
}


def _file_type(path: str) -> str:
    """Return the last `path` segment's text from its last dot, or an empty string."""
    name = path.rsplit("/", 1)[-1]
    return "." + name.rsplit(".", 1)[1] if "." in name else ""


def _data_type_fault(citation: str) -> str | None:
    """Return the `DATA_TYPE` reason `citation` fails, or None when it fits."""
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


def _content_fault(path: str, root: Path) -> str | None:
    """Return the `CONTENT` reason `path` fails under `root`, or None when it fits."""
    target = root.joinpath(*path.split("/")).resolve()
    if not target.is_relative_to(root.resolve()):
        return OUTSIDE_ROOT
    if _file_type(path) not in READERS:
        return NO_READER
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


def _functions_verdict(path: str, symbol: str, root: Path) -> tuple[str, str]:
    """Return the `FUNCTIONS` verdict from `_walk_exact` and the `READERS` entry."""
    parts = path.split("/")
    missing = _walk_exact(root, parts)
    if missing:
        return NOT_GROUNDED, missing
    try:
        source = root.joinpath(*parts).read_bytes()
    except OSError:
        return NOT_GROUNDED, UNREADABLE
    defined = READERS[_file_type(path)](source, symbol.split("."))
    if defined is None:
        return NOT_GROUNDED, UNPARSED
    if defined:
        return RESOLVED, DEFINED
    return NOT_GROUNDED, UNDEFINED


def resolve_citation(citation: str, root: Path) -> tuple[str, str]:
    """Return the verdict for `citation` under `root`, and a reason naming its tier."""
    fault = _data_type_fault(citation)
    if fault:
        return REJECTED, f"{DATA_TYPE}: {fault}"
    path, symbol = citation.split(SETTINGS["separator"], 1)
    fault = _content_fault(path, root)
    if fault:
        return REJECTED, f"{CONTENT}: {fault}"
    verdict, reason = _functions_verdict(path, symbol, root)
    return verdict, f"{FUNCTIONS}: {reason}"


def repository_root(start: Path) -> Path | None:
    """Return the nearest folder at or above `start` that holds `.git`, or None."""
    for folder in (start, *start.parents):
        if (folder / ".git").exists():
            return folder
    return None


def main(argv: list[str] | None = None) -> int:
    """Print `CARD` or one JSON verdict per line of `file`; 0 only if all RESOLVED."""
    parser = argparse.ArgumentParser(
        prog="python -m dev_harness.sigils.cite_symbol",
        description="Resolve one 'path, in symbol' citation per line.",
    )
    parser.add_argument("file", type=Path, nargs="?", help="one citation per line")
    parser.add_argument(
        "--root",
        type=Path,
        help="the tree the citations name; "
        "default: the repository holding the working folder",
    )
    parser.add_argument("--card", action="store_true", help="print the card as JSON")
    args = parser.parse_args(argv)
    if args.card:
        print(json.dumps(CARD, indent=2))
        return 0
    if args.file is None:
        parser.error("a citation file is required unless --card is given")
    root = args.root if args.root is not None else repository_root(Path.cwd())
    if root is None:
        print(
            "no folder holding .git at or above the working folder; pass --root",
            file=sys.stderr,
        )
        return 1
    if not root.is_dir():
        print(f"--root is not a folder: {root}", file=sys.stderr)
        return 1
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
        verdict, reason = resolve_citation(citation, root)
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
