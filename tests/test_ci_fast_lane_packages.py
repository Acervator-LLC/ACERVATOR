"""Every test imports only what the CI lane collecting it installs.

``offending_imports`` reads the files the fast lane collects and
``full_lane_offences`` the files it deselects. Both walk ``reachable_imports``
through the repo modules a test imports, and measure against the set
``lane_distributions`` reads out of ``pyproject.toml`` at run time.
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
    SLOW_FILES,
    fast_lane_distributions,
    is_collected,
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


def names_type_checking(test: ast.expr) -> bool:
    """True when `test` is the ``TYPE_CHECKING`` flag, plain or dotted."""
    if isinstance(test, ast.Name):
        return test.id == "TYPE_CHECKING"
    return isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"


def deferred_lines(tree: ast.Module) -> set[int]:
    """Lines of imports a plain ``import`` of the module never executes.

    Covers a function or method body and the body of an ``if TYPE_CHECKING``.
    """
    deferred: set[int] = set()
    bodies: list[list[ast.stmt]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            bodies.append(node.body)
        elif isinstance(node, ast.If) and names_type_checking(node.test):
            bodies.append(node.body)
    for body in bodies:
        for statement in body:
            for inner in ast.walk(statement):
                if isinstance(inner, (ast.Import, ast.ImportFrom)):
                    deferred.add(inner.lineno)
    return deferred


def imports_outside(tree: ast.Module, skip: set[int]) -> list[tuple[int, str]]:
    """Every dotted module name `tree` imports on a line outside `skip`."""
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and node.lineno not in skip:
            for alias in node.names:
                found.append((node.lineno, alias.name))
        elif isinstance(node, ast.ImportFrom) and node.lineno not in skip:
            if node.level == 0 and node.module:
                found.append((node.lineno, node.module))
    return found


def _parse(path: Path) -> ast.Module | None:
    """Parse `path`, or None when it vanished after the scan listed it."""
    try:
        source = path.read_text(encoding="utf-8")
    except OSError:
        return None
    return ast.parse(source)


def unguarded_imports(path: Path) -> list[tuple[int, str]]:
    """Every dotted module name `path` imports without a guard.

    Covers a function body as well as module level, unlike
    ``import_time_imports``.
    """
    tree = _parse(path)
    if tree is None:
        return []
    return imports_outside(tree, guarded_lines(tree))


def import_time_imports(path: Path) -> list[tuple[int, str]]:
    """Every dotted module name importing `path` runs, guards excluded.

    Drops the lines ``deferred_lines`` reports, which a caller reaches only
    by calling the function holding them.
    """
    tree = _parse(path)
    if tree is None:
        return []
    return imports_outside(tree, guarded_lines(tree) | deferred_lines(tree))


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


def reachable_imports(
    path: Path, roots: tuple[Path, ...], entry: bool = True
) -> dict[str, str]:
    """Third-party modules `path` reaches, each with the chain that led there.

    An import `local_module_path` resolves is followed through
    ``import_time_imports``, which drops the lines that module defers.
    """
    pending = [(path, path.name, entry)]
    read: set[Path] = set()
    found: dict[str, str] = {}
    while pending:
        current, chain, entry = pending.pop()
        if current in read:
            continue
        read.add(current)
        reader = unguarded_imports if entry else import_time_imports
        for _line, module in reader(current):
            top = module.split(".")[0]
            if top in sys.stdlib_module_names:
                continue
            resolved = local_module_path(module, roots)
            if resolved is not None:
                pending.append((resolved, f"{chain} -> {module}", False))
            elif is_local_module(top, roots):
                continue
            elif top not in found:
                found[top] = f"{chain} -> {module}"
    return found


def lane_offences(
    directory: Path, files: list[Path], allowed: frozenset[str], lane: str
) -> list[str]:
    """Imports in `files` of a package the `lane` package set `allowed` omits.

    One string per offence, naming the import chain and the package.
    """
    owners = module_owners()
    roots = (REPO_ROOT, TESTS_DIR, directory)
    offences = []
    for path in files:
        reached = reachable_imports(path, roots, is_collected(path.name))
        for module, chain in sorted(reached.items()):
            owning = owners.get(module)
            if owning is None:
                offences.append(
                    f"{chain} reaches {module!r}, "
                    "which no installed package provides"
                )
            elif not owning & allowed:
                offences.append(
                    f"{chain} reaches {module!r} from {sorted(owning)}, "
                    f"outside the {lane} lane's package set"
                )
    return offences


def fast_lane_files(directory: Path) -> list[Path]:
    """Every file under `directory` the fast lane collects."""
    return [
        path for path in sorted(directory.rglob("*.py")) if runs_in_fast_lane(path.name)
    ]


def offending_imports(directory: Path) -> list[str]:
    """Fast-lane imports of a package the fast lane does not install."""
    return lane_offences(
        directory, fast_lane_files(directory), fast_lane_distributions(), "fast"
    )


def full_lane_files(directory: Path) -> list[Path]:
    """Every file under `directory` the fast lane deselects."""
    return [
        path
        for path in sorted(directory.rglob("*.py"))
        if not runs_in_fast_lane(path.name)
    ]


def full_lane_offences(directory: Path) -> list[str]:
    """Full-lane imports of a package the full lane does not install."""
    return lane_offences(
        directory,
        full_lane_files(directory),
        lane_distributions(FULL_LANE_EXTRA),
        "full",
    )


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
    """``offending_imports`` names matplotlib, the import that broke CI."""
    write_case(tmp_path, "test_case.py", "import matplotlib")
    offences = offending_imports(tmp_path)
    assert len(offences) == 1, offences
    assert "matplotlib" in offences[0], offences


def test_the_scan_reports_an_import_inside_a_function_body(tmp_path):
    """``is_collected`` holds for a test file, so a deferred import counts."""
    write_case(tmp_path, "test_case.py", "def helper():\n    import reportlab")
    offences = offending_imports(tmp_path)
    assert len(offences) == 1, offences
    assert "reportlab" in offences[0], offences


def test_the_scan_reports_a_module_no_installed_package_provides(tmp_path):
    """``module_owners`` holds no entry, and the scan reports the name."""
    write_case(tmp_path, "test_case.py", "import nowhere_at_all")
    offences = offending_imports(tmp_path)
    assert len(offences) == 1, offences
    assert "nowhere_at_all" in offences[0], offences


def test_the_scan_passes_a_file_importing_only_fast_lane_packages(tmp_path):
    """``fast_lane_distributions`` covers all three, so nothing is reported."""
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


def chains_of(offences: list[str]) -> list[str]:
    """The import chain of each offence, with the package clause dropped."""
    return [offence.split(" reaches ")[0] for offence in offences]


def test_the_scan_names_the_chain_from_the_test_through_the_repo_module(tmp_path):
    """A direct read of the test file names only the repo module."""
    write_case(tmp_path, "helper.py", "import matplotlib")
    case = write_case(tmp_path, "test_case.py", "import helper")

    assert unguarded_imports(case) == [(1, "helper")]

    assert chains_of(offending_imports(tmp_path)) == [
        "helper.py -> matplotlib",
        "test_case.py -> helper -> matplotlib",
    ]


def test_the_scan_passes_a_repo_module_guarding_its_heavy_import(tmp_path):
    """A guard keeps the repo module importable without the package."""
    guarded = "try:\n    import matplotlib\nexcept ImportError:\n    matplotlib = None"
    helper = write_case(tmp_path, "helper.py", guarded)
    write_case(tmp_path, "test_case.py", "import helper")

    assert offending_imports(tmp_path) == []

    helper.write_text("import matplotlib\n", newline="\n", encoding="utf-8")
    assert chains_of(offending_imports(tmp_path)) == [
        "helper.py -> matplotlib",
        "test_case.py -> helper -> matplotlib",
    ], "the same case unguarded must be reported, or the pass above is empty"


def test_the_scan_passes_a_repo_module_importing_inside_a_function_body(tmp_path):
    """Importing the repo module never runs a name bound inside a function."""
    helper = write_case(tmp_path, "helper.py", "def call():\n    import matplotlib")
    write_case(tmp_path, "test_case.py", "import helper")

    assert offending_imports(tmp_path) == []

    helper.write_text("import matplotlib\n", newline="\n", encoding="utf-8")
    assert chains_of(offending_imports(tmp_path)) == [
        "helper.py -> matplotlib",
        "test_case.py -> helper -> matplotlib",
    ], "the same import at module level must be reported"


def test_the_scan_passes_a_repo_module_importing_under_type_checking(tmp_path):
    """A ``TYPE_CHECKING`` body binds names for the checker, not at run time."""
    body = (
        "from typing import TYPE_CHECKING\n\nif TYPE_CHECKING:\n    import matplotlib"
    )
    helper = write_case(tmp_path, "helper.py", body)
    write_case(tmp_path, "test_case.py", "import helper")

    assert offending_imports(tmp_path) == []

    helper.write_text("import matplotlib\n", newline="\n", encoding="utf-8")
    assert chains_of(offending_imports(tmp_path)) == [
        "helper.py -> matplotlib",
        "test_case.py -> helper -> matplotlib",
    ], "the same import outside the TYPE_CHECKING body must be reported"


def test_the_fast_lane_scan_reads_the_files_the_fast_lane_collects():
    """The fast-lane check above passes over an empty file list."""
    names = {path.name for path in fast_lane_files(TESTS_DIR)}
    assert "test_ci_fast_lane_packages.py" in names, sorted(names)
    assert "test_design_system_chart_tokens.py" not in names, sorted(names)
    assert "test_extract_product_manual_keeps_additions.py" not in names, sorted(names)


def test_a_file_that_vanished_after_the_listing_is_skipped(tmp_path):
    """``rglob`` names a file another process can delete before the read."""
    gone = tmp_path / "gone.py"
    assert unguarded_imports(gone) == []
    assert import_time_imports(gone) == []


def test_a_file_that_is_present_is_still_read(tmp_path):
    """Positive control for the skip above."""
    present = tmp_path / "present.py"
    present.write_text("import numpy\n", encoding="utf-8")
    assert unguarded_imports(present) == [(1, "numpy")]
    assert import_time_imports(present) == [(1, "numpy")]


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


@pytest.mark.parametrize("package", ["matplotlib", "pypdf"])
def test_the_full_lane_installs_what_the_deselected_files_reach(package):
    """The files moved out of the fast lane get their package in the full one."""
    assert package in lane_distributions(FULL_LANE_EXTRA)
    assert package not in fast_lane_distributions()


@pytest.mark.parametrize(
    "name",
    [
        "test_design_system_chart_tokens.py",
        "test_extract_product_manual_keeps_additions.py",
    ],
)
def test_a_file_reaching_a_heavy_package_is_named_slow(name):
    """A fast lane collecting these would skip one and error on the other."""
    assert name in SLOW_FILES
    assert not runs_in_fast_lane(name)


@pytest.mark.parametrize("extra", ["charts", "report", "contracts"])
def test_the_fast_lane_package_set_excludes_a_heavy_extra(extra):
    """A heavy extra reads as installed, so the scan can never report it."""
    declared = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]
    named = declared["optional-dependencies"][extra]
    assert named, extra
    leaked = {normalise_distribution(d) for d in named} & fast_lane_distributions()
    assert leaked == set(), leaked
