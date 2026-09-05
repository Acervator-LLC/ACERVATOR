"""A file that wears pytest's name must be collected, or be excused.

Every file whose name matches ``PYTEST_DEFAULT_PYTHON_FILES`` is listed off the
tree and must either sit under ``testpaths`` or carry a reason in ``EXCUSED``.
Every collected test file must also yield at least one item, and every
``norecursedirs``, ``--ignore=`` and ``--ignore-glob=`` entry must name a
subject that is in the tree. Each rule reads the tree and the ini rather than
the current session's collected items, so a single-file run cannot pass it
vacuously; ``test_suite_integrity.py`` owns the item-count floors.
"""

from __future__ import annotations

import ast
import os
import re
import tomllib
from fnmatch import fnmatch
from functools import lru_cache
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# pytest's default ``python_files``; the ini sets no override.
PYTEST_DEFAULT_PYTHON_FILES = ("test_*.py", "*_test.py")

# Directories the walk never enters, each with its reason.
WALK_SKIP_EXACT = {
    "__pycache__": "bytecode, not source",
    "quarantine": "holds files taken out of the tree; they are not in it",
}

# Discovery-named files pytest must not collect, each with its reason.
EXCUSED: dict[str, str] = {
    # Every entry is a GUI/coding archetype calibration body under
    # `tests/fixtures/`, kept out of collection by `norecursedirs`.
    "harness_fixtures/gui_archetype/tests/"
    "known_good_colour_test.py": "GUI006 calibration fixture; the archetype must exit 0 on it",
    "harness_fixtures/gui_archetype/tests/"
    "known_bad_colour_test.py": "GUI006 calibration fixture built to FAIL the archetype; "
    "collecting it would turn the suite red on purpose",
    "harness_fixtures/gui_archetype/tests/"
    "known_bad_real_defect_test.py": "coding-archetype calibration fixture carrying deliberate "
    "defects; collecting it would turn the suite red on purpose",
}

# ``python_functions`` and ``python_classes`` defaults. pytest matches a
# PREFIX, so ``testfoo`` counts and ``_test_foo`` does not.
TEST_FUNCTION_PREFIX = "test"
TEST_CLASS_PREFIX = "Test"


@lru_cache(maxsize=1)
def _pyproject() -> dict[str, Any]:
    """Parse pyproject.toml once."""
    parsed: dict[str, Any] = tomllib.loads(
        (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    return parsed


def _ini() -> dict[str, Any]:
    """Read the ``[tool.pytest.ini_options]`` table."""
    table: dict[str, Any] = _pyproject()["tool"]["pytest"]["ini_options"]
    return table


@lru_cache(maxsize=4)
def _walk(root: Path = REPO_ROOT) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """One pass over `root`: entry basenames, and discovery-named files.

    Returns every directory and file basename, then the POSIX paths of
    the matching files relative to `root`.
    """
    entries: list[str] = []
    files: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        kept = []
        for name in dirnames:
            entries.append(name)
            if name in WALK_SKIP_EXACT or name.startswith("."):
                continue
            kept.append(name)
        dirnames[:] = kept
        for name in filenames:
            entries.append(name)
            if any(fnmatch(name, pattern) for pattern in PYTEST_DEFAULT_PYTHON_FILES):
                rel = Path(dirpath, name).relative_to(root)
                files.append(rel.as_posix())
    return tuple(sorted(set(entries))), tuple(sorted(files))


def _discovery_named_files() -> tuple[str, ...]:
    """List every file in the tree whose name pytest recognises."""
    return _walk()[1]


def _tree_entry_names() -> tuple[str, ...]:
    """List every directory and file basename in the tree.

    A ``norecursedirs`` glob is matched against a basename, and a linked
    git worktree carries ``.git`` as a gitdir pointer file rather than a
    directory, so a directory-only list has no subject for it.
    """
    return _walk()[0]


def _dead_ignore_paths(addopts: str | list[str]) -> list[str]:
    """``--ignore``/``--ignore-glob`` entries in addopts naming no path in the tree.

    pytest takes addopts as a string or a list, and accepts both option
    spellings with either a space or an equals sign.
    """
    joined = " ".join(addopts) if isinstance(addopts, list) else addopts
    ignored = re.findall(r"--ignore(?:-glob)?[= ](\S+)", joined)
    return [p for p in ignored if not (REPO_ROOT / p).exists()]


def _testpath_roots() -> tuple[str, ...]:
    """Read the ``testpaths`` roots, without a trailing separator."""
    return tuple(p.strip("/") for p in _ini()["testpaths"])


def _inside_testpaths(rel: str) -> bool:
    """Say whether pytest reaches this path from ``testpaths``."""
    return any(rel == root or rel.startswith(root + "/") for root in _testpath_roots())


def _defines_a_test(path: Path) -> bool:
    """Say whether pytest takes at least one item out of this module."""
    tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            if node.name.startswith(TEST_FUNCTION_PREFIX):
                return True
        elif isinstance(node, ast.ClassDef):
            if not node.name.startswith(TEST_CLASS_PREFIX):
                continue
            for member in node.body:
                if isinstance(
                    member, ast.FunctionDef | ast.AsyncFunctionDef
                ) and member.name.startswith(TEST_FUNCTION_PREFIX):
                    return True
    return False


# -- the rules -------------------------------------------------------


def test_every_discovery_named_file_is_collected_or_excused() -> None:
    """A test-named file outside ``testpaths`` runs nowhere.

    It reads as coverage in the tree and contributes nothing to the gate.
    """
    stragglers = [
        rel
        for rel in _discovery_named_files()
        if not _inside_testpaths(rel) and rel not in EXCUSED
    ]
    assert stragglers == [], (
        "these files match pytest's discovery patterns, sit outside "
        f"testpaths {_testpath_roots()}, and are excused by nothing: "
        f"{stragglers}. Either move the file under a testpath or add it "
        "to EXCUSED with the reason it must stay out"
    )


def test_every_collected_test_file_defines_at_least_one_test() -> None:
    """A test file with no test is a file that does nothing.

    pytest imports it, takes no item out of it, and reports success.
    That is the second half of the same defect: the first half is a
    test file nothing reads, this half is a test file with nothing in
    it.
    """
    empty = [
        rel
        for rel in _discovery_named_files()
        if _inside_testpaths(rel) and not _defines_a_test(REPO_ROOT / rel)
    ]
    assert empty == [], (
        "these files are collected but yield no test item: "
        f"{empty}. A module with no `test`-prefixed function and no "
        "`Test`-prefixed class is a script, and must not carry "
        "pytest's discovery prefix"
    )


def test_every_excusal_names_a_file_that_is_in_the_tree() -> None:
    """An excusal for a file that has gone is dead cover.

    It reads as a live decision long after its subject left.
    """
    gone = [rel for rel in EXCUSED if not (REPO_ROOT / rel).is_file()]
    assert gone == [], f"EXCUSED names files that are not in the tree: {gone}"


def test_every_excusal_carries_a_reason() -> None:
    """An excusal with no reason is a suppression."""
    blank = [rel for rel, reason in EXCUSED.items() if not reason.strip()]
    assert blank == [], f"EXCUSED entries with no reason: {blank}"


def test_pytest_exclusions_name_something_that_is_in_the_tree() -> None:
    """Every collection filter must have a subject.

    ``norecursedirs`` entries are globs matched against a BASENAME, so
    the subject is any tree entry of that name, directory or file.
    ``--ignore=`` and ``--ignore-glob=`` entries are paths.
    pytest accepts all three for a subject that is not there, and says
    nothing, so a dead entry survives until something reads it.

    ``addopts`` is empty, so the second half reads no entry today;
    ``test_the_dead_ignore_scan_answers_both_ways`` shows it can still
    report.
    """
    ini = _ini()
    names = _tree_entry_names()
    dead_exclusions = [
        pattern
        for pattern in ini.get("norecursedirs", [])
        if not any(fnmatch(name, pattern) for name in names)
    ]
    assert (
        dead_exclusions == []
    ), f"norecursedirs entries matching nothing in the tree: {dead_exclusions}"

    dead_paths = _dead_ignore_paths(ini.get("addopts", ""))
    assert (
        dead_paths == []
    ), f"--ignore entries naming a path that is gone: {dead_paths}"


def test_effective_discovery_patterns_are_the_ones_this_guard_reads() -> None:
    """The guard must walk with pytest's real patterns, not a copy.

    The ini does not set ``python_files``, so the defaults above ARE the
    effective configuration. If a later change sets the option, this
    fails, and the constant must be updated before the walk can be
    trusted again.
    """
    assert "python_files" not in _ini(), (
        "pyproject.toml now sets python_files. Update "
        "PYTEST_DEFAULT_PYTHON_FILES to match it before the walk can be "
        "trusted again"
    )


# -- the rules must not be vacuous -----------------------------------


def test_the_walk_finds_the_suite() -> None:
    """A walk that finds nothing passes every rule above.

    Measured 2026-08-23: 272 discovery-named files, 268 of them under
    ``tests/``. The floor sits under both so ordinary consolidation
    does not trip it.
    """
    found = _discovery_named_files()
    assert len(found) >= 200, f"the walk found only {len(found)} files"
    inside = [rel for rel in found if _inside_testpaths(rel)]
    assert len(inside) >= 200, f"only {len(inside)} files are under testpaths"
    assert (
        "tests/test_every_test_file_is_collected.py" in found
    ), "the walk does not find this guard, so it does not read the tree"


def test_the_excusal_list_is_not_empty() -> None:
    """An empty EXCUSED makes its two rules answer nothing.

    Four files are excused today. If the last one ever leaves, that is
    a real change and it must be made deliberately.
    """
    assert EXCUSED, "EXCUSED is empty, so its rules test nothing"


def test_the_exclusion_rule_has_entries_to_read() -> None:
    """A config with no filter makes the exclusion rule vacuous."""
    assert _ini().get(
        "norecursedirs"
    ), "norecursedirs is empty, so the exclusion rule reads nothing"


def test_the_dead_ignore_scan_answers_both_ways() -> None:
    """The ini sets no ``addopts``, so nothing else can show this scan reporting.

    A guard asserting the key is present would fail on sight, so the scan
    is driven over a synthetic option string to prove it can go red.
    """
    live = "tests"
    dead = "tests/a_path_that_is_not_in_the_tree.py"
    assert _dead_ignore_paths("") == []
    assert _dead_ignore_paths(f"--ignore={live}") == []
    assert _dead_ignore_paths(f"--ignore={dead}") == [dead]
    assert _dead_ignore_paths(f"--ignore-glob {dead}") == [dead]
    assert _dead_ignore_paths([f"--ignore={live}", f"--ignore={dead}"]) == [dead]


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("def test_one():\n    assert True\n", True),
        ("async def test_one():\n    assert True\n", True),
        ("class TestThing:\n    def test_one(self):\n        assert True\n", True),
        ("def helper():\n    return 1\n", False),
        ("def _test_one():\n    assert True\n", False),
        ("class Thing:\n    def test_one(self):\n        assert True\n", False),
        ("import math\n", False),
    ],
)
def test_the_empty_file_detector_answers_both_ways(
    source: str, *, expected: bool, tmp_path: Path
) -> None:
    """A detector that always says True would clear an empty file.

    The last four cases are the ones that matter: pytest takes no item
    out of any of them.
    """
    path = tmp_path / "sample_test.py"
    path.write_text(source, encoding="utf-8")
    assert _defines_a_test(path) is expected
