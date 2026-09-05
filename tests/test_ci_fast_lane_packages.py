"""Every test imports only what the CI lane collecting it installs.

``offending_imports`` reads the files the fast lane collects.
``full_lane_offences`` reads the files it deselects and follows the repo
modules they import. Both measure against the set ``lane_distributions``
reads out of ``pyproject.toml`` at run time.
"""

from __future__ import annotations

import ast
import sys
import tomllib
from importlib.metadata import packages_distributions
from pathlib import Path

import pytest

from tests.fixtures.ci_lanes import (
    FULL_LANE_EXTRA,
    PYPROJECT,
    fast_lane_distributions,
    lane_distributions,
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
    """Every dotted module name `path` imports without a guard.

    Covers imports inside a function body as well as module level: the
    matplotlib import that broke CI sat inside a helper.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    safe = guarded_lines(tree)
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and node.lineno not in safe:
            for alias in node.names:
                found.append((node.lineno, alias.name))
        elif isinstance(node, ast.ImportFrom) and node.lineno not in safe:
            if node.level == 0 and node.module:
                found.append((node.lineno, node.module))
    return found


def local_module_path(module: str, roots: tuple[Path, ...]) -> Path | None:
    """The file a dotted `module` names under one of `roots`, else None."""
    parts = module.split(".")
    for root in roots:
        base = root.joinpath(*parts)
        if base.with_suffix(".py").is_file():
            return base.with_suffix(".py")
        if (base / "__init__.py").is_file():
            return base / "__init__.py"
    return None


def reachable_imports(path: Path, roots: tuple[Path, ...]) -> dict[str, str]:
    """Third-party modules `path` reaches, each with the chain that led there.

    An import that `local_module_path` resolves is followed, so a package
    a test reaches only through a repo module is reported.
    """
    pending = [(path, path.name)]
    read: set[Path] = set()
    found: dict[str, str] = {}
    while pending:
        current, chain = pending.pop()
        if current in read:
            continue
        read.add(current)
        for _line, module in unguarded_imports(current):
            top = module.split(".")[0]
            if top in sys.stdlib_module_names:
                continue
            resolved = local_module_path(module, roots)
            if resolved is not None:
                pending.append((resolved, f"{chain} -> {module}"))
            elif is_local_module(top, roots):
                continue
            elif top not in found:
                found[top] = f"{chain} -> {module}"
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
        for line, dotted in unguarded_imports(path):
            module = dotted.split(".")[0]
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


def full_lane_files(directory: Path) -> list[Path]:
    """Every file under `directory` the fast lane deselects."""
    return [
        path
        for path in sorted(directory.rglob("*.py"))
        if not runs_in_fast_lane(path.name)
    ]


def full_lane_offences(directory: Path) -> list[str]:
    """Full-lane imports of a package the full lane does not install.

    One string per offence, naming the import chain and the package.
    """
    allowed = lane_distributions(FULL_LANE_EXTRA)
    owners = module_owners()
    roots = (REPO_ROOT, TESTS_DIR, directory)
    offences = []
    for path in full_lane_files(directory):
        for module, chain in sorted(reachable_imports(path, roots).items()):
            owning = owners.get(module)
            if owning is None:
                offences.append(
                    f"{chain} reaches {module!r}, "
                    "which no installed package provides"
                )
            elif not owning & allowed:
                offences.append(
                    f"{chain} reaches {module!r} from {sorted(owning)}, "
                    "outside the full lane's package set"
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


def test_no_full_lane_test_imports_a_package_ci_does_not_install():
    """A full-lane test needs a package the CI full lane never installs."""
    offences = full_lane_offences(TESTS_DIR)
    assert offences == [], "\n".join(offences)


def test_the_full_lane_scan_reads_the_files_the_fast_lane_deselects():
    """The full-lane check above passes over an empty file list."""
    names = {path.name for path in full_lane_files(TESTS_DIR)}
    assert "test_build_product_manual.py" in names, sorted(names)
    assert "test_build_product_manual_rendering.py" in names, sorted(names)


def test_the_full_lane_scan_reports_a_package_reached_through_a_repo_module(tmp_path):
    """A package reached only through a repo module hides from a direct read."""
    write_case(tmp_path, "helper.py", "import nowhere_at_all")
    case = write_case(tmp_path, "test_archetype_case.py", "import helper")
    assert unguarded_imports(case) == [(1, "helper")]

    reached = reachable_imports(case, (tmp_path,))
    assert "nowhere_at_all" in reached, reached
    assert reached["nowhere_at_all"].endswith("helper -> nowhere_at_all"), reached


def test_the_full_lane_scan_passes_a_file_importing_only_full_lane_packages(tmp_path):
    """The scan reports a package the full lane does install."""
    write_case(tmp_path, "test_archetype_case.py", "import pytest\nimport reportlab")
    assert full_lane_offences(tmp_path) == []


def test_the_full_lane_package_set_follows_a_self_reference_into_another_extra():
    """`acervator[lint]` reaches black, which the `dev` extra never names."""
    assert "black" in lane_distributions(FULL_LANE_EXTRA)
    assert "black" not in fast_lane_distributions()


@pytest.mark.parametrize("extra", ["charts", "report", "contracts"])
def test_the_fast_lane_package_set_excludes_a_heavy_extra(extra):
    """A heavy extra reads as installed, so the scan can never report it."""
    declared = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]
    named = declared["optional-dependencies"][extra]
    assert named, extra
    leaked = {normalise_distribution(d) for d in named} & fast_lane_distributions()
    assert leaked == set(), leaked
