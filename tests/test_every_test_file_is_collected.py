"""A file that wears pytest's name must be collected, or be excused.

WHAT WAS MEASURED
=================
Issue #93, on 2026-08-23, in a clone at commit 2551795. Every file in
the tree whose name matches pytest's discovery patterns was listed from
disk, and the list was compared against what ``pytest tests
--collect-only`` really collects:

    272  files on disk match ``test_*.py`` or ``*_test.py``
    268  of them are collected, and every one yields at least one item
      4  are collected by nothing

Those counts are from BEFORE this file existed. Adding it makes 273
and 269, and takes collection from 7407 items to 7423 -- the 16 this
file contributes, and nothing else moved.

Issue #85 then renamed the first of the four out of pytest's discovery
patterns, so the disk figure is 272 and the uncollected figure is 3.
Nothing about the rule changed; one subject left it.

The four, as issue #93 found them:

  ``test_scrumming_v3.py`` at the repository root. It sat outside
  ``testpaths``, so pytest never read it. It also defined NO test
  function, so bringing it in would have added nothing:
  ``pytest test_scrumming_v3.py --collect-only`` answered "no tests
  collected" and exited 5. It is not a stale copy of anything either.
  Its whole import list -- ``VortexIndicator``, ``MACD``,
  ``BollingerBands``, ``compute_heikin_ashi``, ``detect_bb_proximity``
  -- is exercised by collected tests that DO assert, in
  ``test_ta_engine_confidence_bounds.py``,
  ``test_ta_engine_degenerate_abstention.py``,
  ``test_bollinger_squeeze_scale_invariance.py``,
  ``test_slingshot_canonical.py`` and three others. So it was a script
  wearing a test prefix, and it added no coverage.

  RESOLVED by issue #85 on 2026-08-23. Issue #93 excused it here and
  said the repair "belongs to whichever unit may edit its body". Issue
  #85 is that unit. The file is now ``tools/scrumming_v3_sim.py``: the
  name no longer matches pytest's discovery patterns, so no excusal is
  needed and the entry is gone from ``EXCUSED`` below. Its excusal was
  the ONLY one in this map that named a live script rather than a
  calibration fixture.

  Issue #85 did NOT move it to ``tests/``, which is what issue #85
  originally proposed. ``test_every_collected_test_file_defines_at
  _least_one_test`` below fails on any collected file that yields no
  test item, so ``tests/`` would have turned the suite red. That test
  is the reason the proposal was refused, and it is a two-sided control
  on the refusal: put a test-function-free file under ``testpaths`` and
  it reports the file by name.

  Three archetype fixtures under ``docs/audits/``. They are DELIBERATE,
  they must never be collected, and each one says so in its own
  docstring. They are the known-good and known-bad halves the GUI and
  coding archetypes are calibrated against; a fixture built to fail
  would turn the suite red on purpose. ``docs/audits/`` is a historical
  record and issue #93 did not edit it.

WHY A NEW GUARD
===============
Nothing measured this. ``test_suite_integrity.py`` counts files INSIDE
``tests/`` and fails if the count collapses, so a test file that never
arrives in ``tests/`` is invisible to it.
``test_no_missing_file_references.py`` checks that an ``--ignore=``
entry names a real path, which is the opposite direction: it catches an
exclusion with no file, not a file with no collection.

Every rule here is STATIC. It reads the tree and the ini, not the
current session's collected items. A rule that read collected items
would pass vacuously whenever pytest is pointed at a single file, and
that is how the suite is run during a repair.

WHAT THIS GUARD DOES NOT DO
===========================
It does not assert a collected-item count. ``test_suite_integrity.py``
owns the floors, and a count assertion is only valid on a full-suite
run.
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

# pytest's default ``python_files``. The ini does not set the option, so
# this is what discovery really uses.
# ``test_effective_discovery_patterns_are_the_ones_this_guard_reads``
# fails if the ini ever sets it, so this constant cannot drift away from
# the configuration.
PYTEST_DEFAULT_PYTHON_FILES = ("test_*.py", "*_test.py")

# Directories the walk never enters, and the reason for each. A dot
# directory is a tool cache or an editor setting, and pytest's own
# built-in ``norecursedirs`` default starts with ``.*``.
WALK_SKIP_EXACT = {
    "__pycache__": "bytecode, not source",
}

# A discovery-named file that pytest must NOT collect. Each entry gives
# the reason. This map may not grow without one, and
# ``test_every_excusal_names_a_file_that_is_in_the_tree`` deletes an
# entry's cover the moment its file leaves.
EXCUSED: dict[str, str] = {
    # Issue #85 removed the one entry here that named a live script,
    # `test_scrumming_v3.py`, by renaming it to
    # `tools/scrumming_v3_sim.py`. Every entry left is a calibration
    # fixture under `docs/audits/`, which is a historical record.
    "docs/audits/2026-07-24_gui_docs_archetypes/gui_fixtures/tests/"
    "known_good_colour_test.py": "GUI006 calibration fixture; the archetype must exit 0 on it",
    "docs/audits/2026-07-24_gui_docs_archetypes/gui_fixtures/tests/"
    "known_bad_colour_test.py": "GUI006 calibration fixture built to FAIL the archetype; "
    "collecting it would turn the suite red on purpose",
    "docs/audits/2026-07-24_gui_docs_archetypes/gui_fixtures/tests/"
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


@lru_cache(maxsize=1)
def _walk() -> tuple[tuple[str, ...], tuple[str, ...]]:
    """One pass over the tree: entry basenames, and discovery-named files.

    Returns every directory and file basename, then the POSIX paths of
    the matching files relative to the repository root.
    """
    entries: list[str] = []
    files: list[str] = []
    for dirpath, dirnames, filenames in os.walk(REPO_ROOT):
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
                rel = Path(dirpath, name).relative_to(REPO_ROOT)
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

    It reads as coverage in the tree and contributes nothing to the
    gate. ``test_scrumming_v3.py`` sat at the root in exactly this
    state until issue #85 renamed it ``tools/scrumming_v3_sim.py``.
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

    It reads as a live decision long after its subject left, which is
    the rot issue #69 removed from ``addopts``.
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

    addopts = ini.get("addopts", "")
    if isinstance(addopts, list):
        addopts = " ".join(addopts)
    ignored = re.findall(r"--ignore(?:-glob)?[= ](\S+)", addopts)
    dead_paths = [p for p in ignored if not (REPO_ROOT / p).exists()]
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
