"""A QImage read must name the image it reads from.

`constBits()` and `bits()` return a view into a QImage's pixel buffer.
When the receiver is an expression rather than a local, the image is
freed the moment the call returns and the view points at released
memory: the next allocation writes its own 32-byte object header over
the head of the buffer, and a buffer large enough to be unmapped
segfaults the runner with exit 139 and no failure summary.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

SCANNED_DIRS = ("src", "tests", "tools", "dev_harness")

BUFFER_READERS = frozenset({"bits", "constBits"})


def _python_files() -> list[Path]:
    """Every tracked Python file this rule applies to."""
    found = sorted(REPO_ROOT.glob("*.py"))
    for name in SCANNED_DIRS:
        found.extend(sorted((REPO_ROOT / name).rglob("*.py")))
    return found


def _buffer_reads(source: str) -> list[tuple[int, str]]:
    """Line number and receiver node class of each buffer read in `source`."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in BUFFER_READERS
        ):
            found.append((node.lineno, type(node.func.value).__name__))
    return found


def _offenders(source: str) -> list[int]:
    """Lines in `source` whose buffer read names no local."""
    return [line for line, kind in _buffer_reads(source) if kind != "Name"]


DEFECT_SOURCE = """
def read(image):
    return bytes(image.convertToFormat(FORMAT).constBits())
"""

CORRECT_SOURCE = """
def read(image):
    converted = image.convertToFormat(FORMAT)
    return bytes(converted.constBits())
"""


def test_the_detector_sees_a_temporary_receiver() -> None:
    """A failure means the rule below cannot fail and proves nothing."""
    assert _offenders(DEFECT_SOURCE) == [3]


def test_the_detector_passes_a_named_receiver() -> None:
    """A failure means the rule below rejects the form it asks for."""
    assert _offenders(CORRECT_SOURCE) == []


def test_the_tree_holds_a_buffer_read_to_check() -> None:
    """A failure means the walk found nothing and the rule is vacuous."""
    seen = [
        (path, line)
        for path in _python_files()
        for line, _ in _buffer_reads(path.read_text("utf-8"))
    ]
    assert len(seen) >= 5, seen


def test_every_buffer_read_names_a_local() -> None:
    """A failure means a QImage read points into a freed pixel buffer."""
    offending = [
        f"{path.relative_to(REPO_ROOT).as_posix()}:{line}"
        for path in _python_files()
        for line in _offenders(path.read_text("utf-8"))
    ]
    assert offending == [], offending
