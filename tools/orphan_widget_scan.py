"""Find interactive Qt widgets that nothing wires.

``scan_file`` reads a module with ``ast`` and reports every
``INTERACTIVE_WIDGETS`` name that never precedes a ``.connect(`` call in the
same file. A widget wired through a loop variable or handed to a helper reads
as an orphan, so ``build_report`` is a warning and not a verdict. An assignment
carrying ``OPT_OUT_MARKER`` is counted as declared and skipped.

    python -m tools.orphan_widget_scan --root src/gui --strict
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

OPT_OUT_MARKER = "# display_only"

# Qt classes the user can operate. A QLabel or a QFrame is not here:
# it carries no signal a handler needs, so an unwired one is correct.
INTERACTIVE_WIDGETS = frozenset(
    {
        "QAction",
        "QCheckBox",
        "QComboBox",
        "QDateEdit",
        "QDateTimeEdit",
        "QDial",
        "QDoubleSpinBox",
        "QFontComboBox",
        "QKeySequenceEdit",
        "QLineEdit",
        "QListView",
        "QListWidget",
        "QPlainTextEdit",
        "QPushButton",
        "QRadioButton",
        "QScrollBar",
        "QSlider",
        "QSpinBox",
        "QTabWidget",
        "QTableView",
        "QTableWidget",
        "QTextEdit",
        "QTimeEdit",
        "QToolButton",
        "QTreeView",
        "QTreeWidget",
    }
)


class Widget:
    """One interactive widget found at one assignment site."""

    def __init__(self, name: str, cls: str, lineno: int) -> None:
        self.name = name
        self.cls = cls
        self.lineno = lineno

    def as_dict(self, path: str) -> dict[str, object]:
        """Render this widget as one row of the report."""
        return {"file": path, "line": self.lineno, "name": self.name, "class": self.cls}


def target_name(node: ast.expr) -> str | None:
    """Render an assignment target as the text the source uses.

    ``ast.Name`` and ``ast.Attribute`` answer their spelling; every other
    ``node`` answers None.
    """
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = target_name(node.value)
        return f"{base}.{node.attr}" if base else None
    return None


def _called_class(value: ast.expr) -> str | None:
    """Return the class name of a constructor call, or None."""
    if not isinstance(value, ast.Call):
        return None
    func = value.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


class FileScan(ast.NodeVisitor):
    """Collect widget assignments and connected names from one module."""

    def __init__(self, lines: list[str]) -> None:
        self.lines = lines
        self.widgets: list[Widget] = []
        self.connected: set[str] = set()
        self.opted_out: list[Widget] = []

    def _record_assign(self, target: ast.expr, value: ast.expr) -> None:
        cls = _called_class(value)
        if cls is None or cls not in INTERACTIVE_WIDGETS:
            return
        name = target_name(target)
        if name is None:
            return
        lineno = getattr(target, "lineno", 0)
        widget = Widget(name, cls, lineno)
        in_range = 0 < lineno <= len(self.lines)
        source = self.lines[lineno - 1] if in_range else ""
        if OPT_OUT_MARKER in source:
            self.opted_out.append(widget)
        else:
            self.widgets.append(widget)

    def visit_Assign(self, node: ast.Assign) -> None:  # noqa: N802
        """Record ``btn = QPushButton(...)`` and its aliases."""
        for target in node.targets:
            self._record_assign(target, node.value)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:  # noqa: N802
        """Record ``btn: QPushButton = QPushButton(...)``."""
        if node.value is not None:
            self._record_assign(node.target, node.value)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        """Record the owner of every ``.connect(...)`` call."""
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "connect":
            # func.value is the signal (``btn.clicked``) or the widget itself.
            owner = target_name(func.value)
            if owner is not None:
                self.connected.add(owner)
                head, _, _ = owner.rpartition(".")
                if head:
                    self.connected.add(head)
        self.generic_visit(node)


def scan_file(path: Path) -> tuple[list[Widget], list[Widget], int]:
    """Return (orphans, opted_out, total_interactive) for one file."""
    text = path.read_text(encoding="utf-8", errors="replace")
    tree = ast.parse(text, filename=str(path))
    scan = FileScan(text.splitlines())
    scan.visit(tree)
    orphans = [w for w in scan.widgets if w.name not in scan.connected]
    total = len(scan.widgets) + len(scan.opted_out)
    return orphans, scan.opted_out, total


def _display_path(path: Path) -> str:
    """Render a path relative to the repo root when it is inside it."""
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def build_report(root: Path) -> dict[str, object]:
    """Scan every module under root and return the whole report."""
    files = sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)
    rows: list[dict[str, object]] = []
    declared: list[dict[str, object]] = []
    unreadable: list[dict[str, object]] = []
    total = 0
    for path in files:
        rel = _display_path(path)
        try:
            orphans, opted_out, count = scan_file(path)
        except (OSError, SyntaxError, ValueError) as exc:
            unreadable.append({"file": rel, "error": str(exc)})
            continue
        total += count
        rows.extend(w.as_dict(rel) for w in orphans)
        declared.extend(w.as_dict(rel) for w in opted_out)
    return {
        "root": _display_path(root),
        "files_scanned": len(files),
        "files_unreadable": unreadable,
        "interactive_widgets": total,
        "wired": total - len(rows) - len(declared),
        "display_only": declared,
        "orphan_candidates": rows,
    }


def _rows_of(report: dict[str, object], key: str) -> list[dict[str, object]]:
    """Read one list field out of the report, or raise."""
    value = report[key]
    if not isinstance(value, list):
        message = f"report[{key!r}] is not a list"
        raise TypeError(message)
    return value


def print_report(report: dict[str, object]) -> None:
    """Write the report to stdout as a table a human reads."""
    rows = _rows_of(report, "orphan_candidates")
    declared = _rows_of(report, "display_only")
    unreadable = _rows_of(report, "files_unreadable")
    print(f"orphan widget scan - root {report['root']}")
    print(f"  files scanned      : {report['files_scanned']}")
    print(f"  interactive widgets: {report['interactive_widgets']}")
    print(f"  wired to a handler : {report['wired']}")
    print(f"  marked display_only: {len(declared)}")
    print(f"  orphan candidates  : {len(rows)}")
    for bad in unreadable:
        print(f"  UNREADABLE {bad['file']}: {bad['error']}")
    if not rows:
        return
    print()
    print("  Every line below is a control the user can operate whose")
    print("  signals reach no handler in the same file. Wire it, delete")
    print(f"  it, or mark the assignment {OPT_OUT_MARKER}.")
    print()
    width = max(len(str(r["file"])) for r in rows)
    ordered = sorted(rows, key=lambda r: (str(r["file"]), int(str(r["line"]))))
    for row in ordered:
        print(
            f"  {str(row['file']):<{width}}  {str(row['line']):>5}  "
            f"{str(row['class']):<18} {row['name']}"
        )


def main(argv: list[str] | None = None) -> int:
    """Run the scan and return the process exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=REPO_ROOT / "src" / "gui",
        help="Directory to scan (default: src/gui).",
    )
    parser.add_argument("--json", action="store_true", help="Print the report as JSON.")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit 1 when any orphan candidate is found.",
    )
    args = parser.parse_args(argv)

    root = args.root if args.root.is_absolute() else REPO_ROOT / args.root
    if not root.is_dir():
        print(f"root is not a directory: {root}", file=sys.stderr)
        return 2

    report = build_report(root)
    # An existing but empty directory passes the check above and scans nothing.
    if not report["files_scanned"]:
        print(f"no Python file under {root}; nothing was scanned", file=sys.stderr)
        print(
            "A scan of zero files reports zero orphans and would pass " "--strict.",
            file=sys.stderr,
        )
        return 2
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print_report(report)

    if args.strict and _rows_of(report, "orphan_candidates"):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
