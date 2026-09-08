"""``__file__``-relative path maths and function-local imports across ``src``.

A module that walks up from ``__file__`` by a count of parents answers with a
path one level off when it moves directory, and raises nothing.
``test_every_import_under_src_resolves`` resolves every
import ``_imports_of`` finds, function-local ones included, which collection
never reaches. ``test_the_walker_reads_a_deferred_import`` is its control.
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _imports_of(path: Path) -> list[tuple[str, int]]:
    """Every import in a file, function-local ones included, resolved.

    A file outside ``REPO_ROOT`` carries no package, so ``pkg`` is empty and only
    its absolute imports resolve.
    """
    try:
        rel = path.resolve().relative_to(REPO_ROOT).with_suffix("")
        pkg: tuple[str, ...] = rel.parts[:-1]
    except ValueError:
        pkg = ()
    found: list[tuple[str, int]] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8", errors="replace"))):
        if isinstance(node, ast.Import):
            found += [(alias.name, node.lineno) for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = list(pkg[: len(pkg) - (node.level - 1)])
                module = ".".join(base + ([node.module] if node.module else []))
            else:
                module = node.module or ""
            if module:
                found.append((module, node.lineno))
    return found


def _src_files() -> list[Path]:
    return [
        p
        for p in sorted((REPO_ROOT / "src").rglob("*.py"))
        if "__pycache__" not in p.parts
    ]


KNOWN_UNRESOLVABLE: set[str] = set()


def test_every_import_under_src_resolves() -> None:
    """Grep cannot see a deferred import. This walks the AST instead."""
    broken = set()
    for path in _src_files():
        for module, line in _imports_of(path):
            if not module.startswith("src."):
                continue
            try:
                spec = importlib.util.find_spec(module)
            except (ImportError, ModuleNotFoundError, ValueError):
                spec = None
            if spec is None:
                broken.add(f"{path.relative_to(REPO_ROOT).as_posix()} -> {module}")
    assert broken - KNOWN_UNRESOLVABLE == set(), "unresolvable:\n  " + "\n  ".join(
        sorted(broken - KNOWN_UNRESOLVABLE)
    )
    assert broken == KNOWN_UNRESOLVABLE, f"the known finding changed: {sorted(broken)}"


def test_the_walker_reads_a_deferred_import(tmp_path) -> None:
    """CONTROL. ``_imports_of`` finds an import written inside a function body,
    which is where a deferred import lives and where collection cannot see it."""
    module = tmp_path / "deferred_importer.py"
    module.write_text(
        "import json\n"
        "\n"
        "\n"
        "def go():\n"
        "    from src.trading.stone_tablets import get_registry\n"
        "\n"
        "    return json, get_registry\n",
        encoding="utf-8",
    )
    walked = {name for name, _line in _imports_of(module)}
    assert "src.trading.stone_tablets" in walked, sorted(walked)
    assert "json" in walked, sorted(walked)


def test_the_walker_reports_nothing_for_a_module_with_no_imports(tmp_path) -> None:
    """NEGATIVE CONTROL. ``_imports_of`` reads the file it was handed and answers
    with an empty list when that file imports nothing."""
    module = tmp_path / "importless.py"
    module.write_text("VALUE = 1\n", encoding="utf-8")
    assert _imports_of(module) == []
