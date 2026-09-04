"""Count comments, and prove a cleanup changed no code.

``count`` reads a file with ``tokenize`` and reports own-line comments,
trailing comments, runs of three or more, and comment lines matching
``IDENTIFIER_PATTERNS``. ``prove`` parses two versions, replaces every
docstring with ``DOCSTRING_STANDIN`` and compares the trees, so a line ending
or a docstring edit never reads as a code change. Exit 1 means ``--strict``
found a block or an identifier, or the two versions differ; exit 2 is a refusal.

    python -m tools.comment_audit count src --strict
    python -m tools.comment_audit prove before.py after.py
"""

from __future__ import annotations

import argparse
import ast
import io
import json
import re
import sys
import tokenize
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

BLOCK_MINIMUM = 3

DOCSTRING_STANDIN = "<docstring>"

# Applied to the comment body; on a raw line the leading "#" reads as an issue.
IDENTIFIER_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("version", re.compile(r"\bv\d+\.\d+(?:\.\d+)*\b")),
    ("date", re.compile(r"\b\d{4}-\d{2}-\d{2}\b")),
    # 1 to 4 digits, no hex digit either side. #225522 is a colour and must
    # not read as issue 2255.
    ("issue", re.compile(r"(?<![0-9A-Za-z])#\d{1,4}(?![0-9A-Za-z])")),
    ("issue", re.compile(r"\b(?:issue|pr|pull request)s?\s+\d+\b", re.IGNORECASE)),
    ("memory", re.compile(r"\bMEM-\d+\b", re.IGNORECASE)),
    (
        "item",
        re.compile(r"\b(?:item|bug|task|ticket|story)[-\s]?#?\d+\b", re.IGNORECASE),
    ),
)

DOCSTRING_OWNERS = (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


class Refused(RuntimeError):
    """A path the audit will not read, or a file that will not parse."""


@dataclass(frozen=True)
class Comment:
    """One comment token: its line, its body, and whether it owns its line."""

    line: int
    body: str
    owns_line: bool


@dataclass(frozen=True)
class Block:
    """A run of own-line comments on consecutive lines."""

    start: int
    end: int

    @property
    def lines(self) -> int:
        """Return how many lines the run covers."""
        return self.end - self.start + 1

    def as_dict(self) -> dict[str, int]:
        """Render the run as one row of the report."""
        return {"start": self.start, "end": self.end, "lines": self.lines}


@dataclass(frozen=True)
class Identifier:
    """One outside-code identifier found in one comment."""

    line: int
    kind: str
    text: str

    def as_dict(self) -> dict[str, object]:
        """Render the identifier as one row of the report."""
        return {"line": self.line, "kind": self.kind, "text": self.text}


@dataclass
class FileCount:
    """Every comment number the audit reports for one file."""

    path: str
    own_line_comments: int = 0
    trailing_comments: int = 0
    blocks: list[Block] = field(default_factory=list)
    identifiers: list[Identifier] = field(default_factory=list)

    @property
    def block_lines(self) -> int:
        """Return own-line comment lines inside a run of BLOCK_MINIMUM or more."""
        return sum(b.lines for b in self.blocks)

    @property
    def identifier_comments(self) -> int:
        """Return the count of comment lines carrying an outside-code identifier."""
        return len({i.line for i in self.identifiers})

    def as_dict(self) -> dict[str, object]:
        """Render every number and every citation for this file."""
        return {
            "file": self.path,
            "own_line_comments": self.own_line_comments,
            "trailing_comments": self.trailing_comments,
            "blocks": len(self.blocks),
            "block_lines": self.block_lines,
            "identifier_comments": self.identifier_comments,
            "block_spans": [b.as_dict() for b in self.blocks],
            "identifier_hits": [i.as_dict() for i in self.identifiers],
        }


@dataclass
class CountReport:
    """The whole count job: what was asked for, what was read, and the totals."""

    targets: list[str]
    unresolved: list[str] = field(default_factory=list)
    unreadable: list[dict[str, str]] = field(default_factory=list)
    counts: list[FileCount] = field(default_factory=list)

    @property
    def files(self) -> int:
        """Return how many files were counted."""
        return len(self.counts)

    @property
    def own_line_comments(self) -> int:
        """Return own-line comment lines across every counted file."""
        return sum(c.own_line_comments for c in self.counts)

    @property
    def trailing_comments(self) -> int:
        """Return trailing comments across every counted file."""
        return sum(c.trailing_comments for c in self.counts)

    @property
    def blocks(self) -> int:
        """Return runs of BLOCK_MINIMUM or more across every counted file."""
        return sum(len(c.blocks) for c in self.counts)

    @property
    def block_lines(self) -> int:
        """Return comment lines sitting inside those runs."""
        return sum(c.block_lines for c in self.counts)

    @property
    def identifier_comments(self) -> int:
        """Return comment lines carrying an outside-code identifier."""
        return sum(c.identifier_comments for c in self.counts)

    def as_dict(self) -> dict[str, object]:
        """Render the whole report, totals first."""
        return {
            "targets": self.targets,
            "unresolved": self.unresolved,
            "unreadable": self.unreadable,
            "totals": {
                "files": self.files,
                "own_line_comments": self.own_line_comments,
                "trailing_comments": self.trailing_comments,
                "blocks": self.blocks,
                "block_lines": self.block_lines,
                "identifier_comments": self.identifier_comments,
            },
            "files": [c.as_dict() for c in self.counts],
        }


@dataclass(frozen=True)
class Docstring:
    """One docstring, named by the thing that owns it."""

    owner: str
    text: str


@dataclass(frozen=True)
class Comparison:
    """The verdict of one before/after comparison."""

    identical: bool
    changed_docstrings: list[dict[str, str]]

    def as_dict(self) -> dict[str, object]:
        """Render the verdict as the whole report."""
        return {
            "executable_code_identical": self.identical,
            "changed_docstrings": self.changed_docstrings,
        }


def read_source(path: Path) -> str:
    """Return the text of `path`, or raise Refused when it cannot be read."""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        message = f"{path}: {exc}"
        raise Refused(message) from exc


def comment_body(token_text: str) -> str:
    """Strip the leading run of ``#`` and spaces off one comment token."""
    return token_text.lstrip("#").strip()


def comment_tokens(text: str) -> list[Comment]:
    """Return every comment in `text`, read by Python's tokeniser.

    A ``#`` inside a string literal never reaches this list, and a second
    ``#`` inside a comment stays part of the one comment it belongs to.
    """
    found: list[Comment] = []
    reader = io.StringIO(text).readline
    try:
        for token in tokenize.generate_tokens(reader):
            if token.type != tokenize.COMMENT:
                continue
            row, column = token.start
            owns_line = token.line[:column].strip() == ""
            found.append(Comment(row, comment_body(token.string), owns_line))
    except (tokenize.TokenError, SyntaxError, IndentationError) as exc:
        message = f"will not tokenise: {exc}"
        raise Refused(message) from exc
    return found


def comment_blocks(
    comments: list[Comment], minimum: int = BLOCK_MINIMUM
) -> list[Block]:
    """Return runs of `minimum` or more own-line comments on consecutive lines."""
    rows = sorted(c.line for c in comments if c.owns_line)
    blocks: list[Block] = []
    if not rows:
        return blocks
    start = previous = rows[0]
    for row in rows[1:]:
        if row == previous + 1:
            previous = row
            continue
        if previous - start + 1 >= minimum:
            blocks.append(Block(start, previous))
        start = previous = row
    if previous - start + 1 >= minimum:
        blocks.append(Block(start, previous))
    return blocks


def outside_code_identifiers(body: str) -> list[tuple[str, str]]:
    """Return every version, date, issue, memory or item number in one comment body."""
    return [
        (kind, match.group(0))
        for kind, pattern in IDENTIFIER_PATTERNS
        for match in pattern.finditer(body)
    ]


def count_source(text: str, path: str) -> FileCount:
    """Return every comment number for one file's text."""
    comments = comment_tokens(text)
    count = FileCount(path=path)
    count.own_line_comments = sum(1 for c in comments if c.owns_line)
    count.trailing_comments = sum(1 for c in comments if not c.owns_line)
    count.blocks = comment_blocks(comments)
    count.identifiers = [
        Identifier(comment.line, kind, found)
        for comment in comments
        for kind, found in outside_code_identifiers(comment.body)
    ]
    return count


def count_file(path: Path) -> FileCount:
    """Return every comment number for one file on disk."""
    try:
        return count_source(read_source(path), display_path(path))
    except Refused as exc:
        message = f"{display_path(path)}: {exc}"
        raise Refused(message) from exc


def docstring_owner_name(node: ast.AST, prefix: str) -> str:
    """Return the dotted name that identifies whatever owns a docstring."""
    if isinstance(node, ast.Module):
        return "<module>"
    name = str(getattr(node, "name", "<anonymous>"))
    return f"{prefix}.{name}" if prefix else name


def is_docstring(statement: ast.stmt) -> bool:
    """Return True when `statement` is a bare string expression in first position."""
    return (
        isinstance(statement, ast.Expr)
        and isinstance(statement.value, ast.Constant)
        and isinstance(statement.value.value, str)
    )


def blank_docstrings(tree: ast.AST) -> list[Docstring]:
    """Replace every docstring in `tree` with DOCSTRING_STANDIN, in place.

    Returns the replaced `Docstring` entries in source order, each named by
    `docstring_owner_name`.
    """
    collected: list[Docstring] = []

    def walk(node: ast.AST, prefix: str) -> None:
        if isinstance(node, DOCSTRING_OWNERS):
            owner = docstring_owner_name(node, prefix)
            first = node.body[0] if node.body else None
            if first is not None and is_docstring(first):
                constant = first.value
                if isinstance(constant, ast.Constant):
                    collected.append(Docstring(owner, str(constant.value)))
                    constant.value = DOCSTRING_STANDIN
            prefix = "" if isinstance(node, ast.Module) else owner
        for child in ast.iter_child_nodes(node):
            walk(child, prefix)

    walk(tree, "")
    return collected


def parse_source(text: str, label: str) -> ast.AST:
    """Parse `text`, or raise Refused naming `label`."""
    try:
        return ast.parse(text)
    except SyntaxError as exc:
        message = f"{label}: will not parse: {exc}"
        raise Refused(message) from exc


def docstring_changes(
    before: list[Docstring], after: list[Docstring]
) -> list[dict[str, str]]:
    """Return every docstring whose owner or text differs between the two sides."""
    changes: list[dict[str, str]] = []
    for index in range(max(len(before), len(after))):
        old = before[index] if index < len(before) else None
        new = after[index] if index < len(after) else None
        if old is not None and new is not None:
            if old.owner == new.owner and old.text == new.text:
                continue
        named = new if new is not None else old
        changes.append(
            {
                "owner": named.owner if named is not None else "<unknown>",
                "before": old.text if old is not None else "",
                "after": new.text if new is not None else "",
            }
        )
    return changes


def compare_sources(before: str, after: str, labels: tuple[str, str]) -> Comparison:
    """Compare two versions of one file for a change in executable code."""
    before_tree = parse_source(before, labels[0])
    after_tree = parse_source(after, labels[1])
    before_docs = blank_docstrings(before_tree)
    after_docs = blank_docstrings(after_tree)
    identical = ast.dump(before_tree) == ast.dump(after_tree)
    return Comparison(identical, docstring_changes(before_docs, after_docs))


def display_path(path: Path) -> str:
    """Render a path relative to the repository root when it sits inside it."""
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def python_files(target: Path) -> list[Path]:
    """Return every Python file `target` names, or holds when it is a directory."""
    if target.is_file():
        return [target]
    return sorted(
        p for p in target.rglob("*.py") if "__pycache__" not in p.parts and p.is_file()
    )


def gather(targets: list[Path]) -> tuple[list[Path], list[str]]:
    """Resolve every target to a file list, and name the ones that resolve to none."""
    files: list[Path] = []
    missing: list[str] = []
    for target in targets:
        if not target.exists():
            missing.append(display_path(target))
            continue
        found = python_files(target)
        if not found:
            missing.append(f"{display_path(target)} (holds no Python file)")
            continue
        files.extend(found)
    seen: dict[str, Path] = {}
    for path in files:
        seen.setdefault(display_path(path), path)
    return [seen[key] for key in sorted(seen)], missing


def build_count_report(targets: list[Path]) -> CountReport:
    """Count every file the targets name and total the result."""
    files, missing = gather(targets)
    report = CountReport(targets=[display_path(t) for t in targets], unresolved=missing)
    for path in files:
        try:
            report.counts.append(count_file(path))
        except Refused as exc:
            report.unreadable.append({"file": display_path(path), "error": str(exc)})
    return report


def print_count_report(report: CountReport) -> None:
    """Write the count report to stdout as a table a human reads."""
    rows = (
        ("files counted", report.files),
        ("own-line comments", report.own_line_comments),
        ("trailing comments", report.trailing_comments),
        (f"blocks of {BLOCK_MINIMUM} or more", report.blocks),
        ("lines inside blocks", report.block_lines),
        ("outside-code comments", report.identifier_comments),
    )
    width = max(len(label) for label, _ in rows)
    print(f"comment audit - targets {', '.join(report.targets)}")
    for label, value in rows:
        print(f"  {label:<{width}} : {value}")
    for name in report.unresolved:
        print(f"  UNRESOLVED {name}", file=sys.stderr)
    for bad in report.unreadable:
        print(f"  UNREADABLE {bad['file']}: {bad['error']}", file=sys.stderr)
    flagged = [c for c in report.counts if c.blocks or c.identifiers]
    if not flagged:
        return
    print()
    name_width = max(len(c.path) for c in flagged)
    print(f"  {'file':<{name_width}}  blocks  in-blocks  outside-code")
    for count in sorted(flagged, key=lambda c: -c.block_lines):
        print(
            f"  {count.path:<{name_width}}  {len(count.blocks):>6}  "
            f"{count.block_lines:>9}  {count.identifier_comments:>12}"
        )


def print_comparison(comparison: Comparison, labels: tuple[str, str]) -> None:
    """Write the before/after verdict to stdout."""
    verdict = "IDENTICAL" if comparison.identical else "DIFFERENT"
    print(f"executable code: {verdict}")
    print(f"  before: {labels[0]}")
    print(f"  after : {labels[1]}")
    if not comparison.changed_docstrings:
        print("  docstrings: unchanged")
        return
    print(f"  docstrings changed: {len(comparison.changed_docstrings)}")
    for change in comparison.changed_docstrings:
        print(f"    {change['owner']}")


def run_count(args: argparse.Namespace) -> int:
    """Run the count job and return the process exit code."""
    targets = [t if t.is_absolute() else REPO_ROOT / t for t in args.paths]
    report = build_count_report(targets)
    if args.json:
        print(json.dumps(report.as_dict(), indent=2))
    else:
        print_count_report(report)
    # A run that counted no file reports every total as 0, which reads
    # exactly like a clean file. Refuse it instead of passing --strict.
    if not report.files:
        print("no Python file was counted", file=sys.stderr)
        return 2
    if report.unresolved or report.unreadable:
        return 2
    if args.strict and (report.blocks or report.identifier_comments):
        return 1
    return 0


def run_prove(args: argparse.Namespace) -> int:
    """Run the prove job and return the process exit code."""
    paths = [p if p.is_absolute() else REPO_ROOT / p for p in (args.before, args.after)]
    labels = (display_path(paths[0]), display_path(paths[1]))
    try:
        texts = [read_source(p) for p in paths]
        comparison = compare_sources(texts[0], texts[1], labels)
    except Refused as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(comparison.as_dict(), indent=2))
    else:
        print_comparison(comparison, labels)
    return 0 if comparison.identical else 1


def build_parser() -> argparse.ArgumentParser:
    """Return the command line: one subcommand per job."""
    parser = argparse.ArgumentParser(
        prog="comment_audit",
        description="Count comments, and prove a cleanup changed no code.",
    )
    sub = parser.add_subparsers(dest="job", required=True)

    counter = sub.add_parser("count", help="Count comments in files or directories.")
    counter.add_argument("paths", nargs="+", type=Path, help="Files or directories.")
    counter.add_argument("--json", action="store_true", help="Print JSON.")
    counter.add_argument(
        "--strict",
        action="store_true",
        help="Exit 1 when any block or outside-code identifier is found.",
    )
    counter.set_defaults(handler=run_count)

    prover = sub.add_parser("prove", help="Compare two versions of one file.")
    prover.add_argument("before", type=Path, help="The version before the edit.")
    prover.add_argument("after", type=Path, help="The version after the edit.")
    prover.add_argument("--json", action="store_true", help="Print JSON.")
    prover.set_defaults(handler=run_prove)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Parse the command line, run the chosen job, return the exit code."""
    args = build_parser().parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    sys.exit(main())
