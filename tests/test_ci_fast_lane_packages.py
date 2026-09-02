"""Every fast-lane test imports only what the CI fast lane installs.

A failure means a test that the fast lane collects reaches for a
package pip never put on the build machine. It passes on a developer
host, which has the heavy extras, and fails on CI with
``ModuleNotFoundError``.

The allowed set is read from ``pyproject.toml`` at run time. A copy
typed into this file would go stale and then pass by being wrong.
"""

from __future__ import annotations

import ast
import sys
import tomllib
from importlib.metadata import packages_distributions
from pathlib import Path

import pytest

from tests.fixtures.ci_lanes import (
    PYPROJECT,
    fast_lane_distributions,
    normalise_distribution,
    runs_in_fast_lane,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
TESTS_DIR = REPO_ROOT / "tests"

IMPORT_ERRORS = {"ImportError", "ModuleNotFoundError", "Exception"}


def module_owners() -> dict[str, frozenset[str]]:
    """Top-level module name to the distributions that install it."""
    return {
        module: frozenset(normalise_distribution(d) for d in dists)
        for module, dists in packages_distributions().items()
    }


def is_local_module(module: str, roots: tuple[Path, ...]) -> bool:
    """True when `module` is a file or package under one of `roots`."""
    return any(
        (root / f"{module}.py").is_file() or (root / module).is_dir() for root in roots
    )


def catches_import_error(handler: ast.ExceptHandler) -> bool:
    """True when `handler` runs on a failed import."""
    caught = handler.type
    if caught is None:
        return True
    named = caught.elts if isinstance(caught, ast.Tuple) else [caught]
    return any(
        isinstance(item, ast.Name) and item.id in IMPORT_ERRORS for item in named
    )


def guarded_lines(tree: ast.Module) -> set[int]:
    """Lines of imports inside a try that catches a failed import.

    A guarded import cannot break the run, so it is not an offence
    whatever package it names.
    """
    safe: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        if not any(catches_import_error(h) for h in node.handlers):
            continue
        for statement in node.body:
            for inner in ast.walk(statement):
                if isinstance(inner, (ast.Import, ast.ImportFrom)):
                    safe.add(inner.lineno)
    return safe


def unguarded_imports(path: Path) -> list[tuple[int, str]]:
    """Every top-level module name `path` imports without a guard.

    Covers imports inside a function body as well as module level: the
    matplotlib import that broke CI sat inside a helper.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    safe = guarded_lines(tree)
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and node.lineno not in safe:
            for alias in node.names:
                found.append((node.lineno, alias.name.split(".")[0]))
        elif isinstance(node, ast.ImportFrom) and node.lineno not in safe:
            if node.level == 0 and node.module:
                found.append((node.lineno, node.module.split(".")[0]))
    return found


def offending_imports(directory: Path) -> list[str]:
    """Fast-lane imports of a package the fast lane does not install.

    One string per offence, naming the file, the line and the package.
    """
    allowed = fast_lane_distributions()
    owners = module_owners()
    roots = (REPO_ROOT, TESTS_DIR, directory)
    offences = []
    for path in sorted(directory.rglob("*.py")):
        if not runs_in_fast_lane(path.name):
            continue
        for line, module in unguarded_imports(path):
            if module in sys.stdlib_module_names or is_local_module(module, roots):
                continue
            owning = owners.get(module)
            if owning is None:
                offences.append(
                    f"{path.name}:{line} imports {module!r}, "
                    "which no installed package provides"
                )
            elif not owning & allowed:
                offences.append(
                    f"{path.name}:{line} imports {module!r} from "
                    f"{sorted(owning)}, outside the fast lane's package set"
                )
    return offences


def test_no_fast_lane_test_imports_a_package_ci_does_not_install():
    """A fast-lane test needs a package the CI fast lane never installs."""
    offences = offending_imports(TESTS_DIR)
    assert offences == [], "\n".join(offences)


def write_case(directory: Path, name: str, body: str) -> Path:
    """One test file holding `body`, for driving the scan over a known case."""
    path = directory / name
    path.write_text(body + "\n", newline="\n", encoding="utf-8")
    return path


def test_the_scan_reports_a_fast_lane_file_importing_an_uninstalled_package(tmp_path):
    """The scan stayed silent on the exact import that broke CI."""
    write_case(tmp_path, "test_case.py", "import matplotlib")
    offences = offending_imports(tmp_path)
    assert len(offences) == 1, offences
    assert "matplotlib" in offences[0], offences


def test_the_scan_reports_an_import_inside_a_function_body(tmp_path):
    """The scan reads module level only, so a deferred import hides."""
    write_case(tmp_path, "test_case.py", "def helper():\n    import reportlab")
    offences = offending_imports(tmp_path)
    assert len(offences) == 1, offences
    assert "reportlab" in offences[0], offences


def test_the_scan_reports_a_module_no_installed_package_provides(tmp_path):
    """A name that resolves nowhere reads as allowed."""
    write_case(tmp_path, "test_case.py", "import nowhere_at_all")
    offences = offending_imports(tmp_path)
    assert len(offences) == 1, offences
    assert "nowhere_at_all" in offences[0], offences


def test_the_scan_passes_a_file_importing_only_fast_lane_packages(tmp_path):
    """The scan reports a package the fast lane does install."""
    write_case(tmp_path, "test_case.py", "import pytest\nimport numpy\nimport PySide6")
    assert offending_imports(tmp_path) == []


def test_the_scan_passes_an_import_guarded_by_try_except(tmp_path):
    """A guarded import cannot break the run, so it is not an offence."""
    body = "try:\n    import matplotlib\nexcept ImportError:\n    matplotlib = None"
    write_case(tmp_path, "test_case.py", body)
    assert offending_imports(tmp_path) == []


def test_the_scan_exempts_a_file_the_fast_lane_deselects(tmp_path):
    """A marked file runs in the full lane, which installs the package."""
    write_case(tmp_path, "test_archetype_case.py", "import matplotlib")
    assert offending_imports(tmp_path) == []


@pytest.mark.parametrize("extra", ["charts", "report", "contracts"])
def test_the_fast_lane_package_set_excludes_a_heavy_extra(extra):
    """A heavy extra reads as installed, so the scan can never report it."""
    declared = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]
    named = declared["optional-dependencies"][extra]
    assert named, extra
    leaked = {normalise_distribution(d) for d in named} & fast_lane_distributions()
    assert leaked == set(), leaked
