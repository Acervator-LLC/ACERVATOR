"""The island tool is retired. It may not come back.

WHAT WAS RETIRED
================
`tools/island.py` was a branch-and-merge simulator. It hard-copied the
repository to an "island" directory, hashed every file at fork time, and
refused to promote a file that live had moved under. `tools/.island_ledger.jsonl`
recorded each promotion. `tests/test_island_promotion_refuses_stale.py`
held 31 test functions, 102 collected tests, pinning that behaviour.

The operator retired islands on 2026-08-19, on moving to GitHub, and
ruled on 2026-08-22: *"Islands are obsolete. You are using Git and
Branches and Issues now."* Issue #67 deleted the three files.

MEASURED BEFORE THE DELETION, at commit 905c9b0
===============================================
    831 lines   tools/island.py
                sha256 65bef95565bce05a8432ba21342f71c55f46f48175728137a5db72f75abbfd3e
     56 lines   tools/.island_ledger.jsonl, 55115 bytes
                sha256 39bc1ce73a18c1bdba12fcd30900a976e7b800a7f38966990d5ef2431e0f0bd6
    616 lines   tests/test_island_promotion_refuses_stale.py
                sha256 e5ad51f0310e79d953f249d3b4bf457e293202e16ecd873d39130c993f78d1b8

Exactly ONE file imported the module: the test file above, at its line
24, `from tools import island`. Nothing under `src/` ever did.

WHY DELETION LOSES NOTHING
==========================
All three were committed, so git holds them for ever. The ledger is
recoverable with `git show 905c9b0:tools/.island_ledger.jsonl`. The lists
it uniquely carried are already transcribed into CHANGELOG.md, which
names it as their source at four places and keeps the entries inline.

The ledger is the tool's STATE FILE, not a narrative record. `island.py`
line 84 named it `LEDGER_RELPATH` and appended to it on every promotion.
With the tool gone, nothing reads it and nothing writes it. A state file
whose only writer is deleted is machinery, so it went with the machinery.

WHAT THE ISLAND GUARANTEED, AND WHAT REPLACES IT
================================================
    fork an isolated copy  ->  a clone, a branch, or `git worktree`
    refuse a stale promote ->  a merge or rebase conflict, plus the gate
                               stamp in `.githooks/pre-push`, which binds
                               the gate verdict to ONE commit sha
    the promotion ledger   ->  commit history, `git log --follow`
    an untouched live tree ->  operatives work in their own clone and the
                               referee fetches and merges
    refuse `dev_harness/`, ->  no mechanism. Recorded as prose in
    `.claude/`, config and    `harness-law` on 2026-08-19, BEFORE this
    version files             issue, and not a loss this change caused
    preserve per-file      ->  `.gitattributes`, added 2026-08-20, plus
    line endings              touchset's LINE ENDING check

Two of those replacements are weaker than what they replace, and both
were already weaker on 2026-08-19. This issue deletes a tool that was
already not running. It removes no live mechanism.

WHY A SEPARATE FILE
===================
`tests/test_tools_are_reachable.py` is the inventory guard from issue
#83. Its subject is the CONTENTS of `tools/`, and its
`test_every_tool_on_disk_is_declared` already fails if `island.py`
returns undeclared. That is one clause of this contract, not all of it.
The island had a ledger, a test file, an entry in `migrate_harness.py`
and a section of `.gitignore` around it, and a directory inventory
cannot speak about those. Folding them in would give that file two
subjects and make a failure there ambiguous.

THE .gitignore CLAUSE
=====================
`.gitignore` opened with a "cascade C00 baseline snapshot protocol"
section. It declared that `_archive/` and `.session26_backups/` were
tracked ON PURPOSE, as a rollback mechanism. Measured 2026-08-22:
`git ls-files` returned ZERO paths under either name, and neither
directory was on disk. The section documented a protocol that protected
nothing, and a reader who trusted it would have believed a rollback
existed. It was removed with the tool, because it is the same fault:
a homegrown substitute for what git already does.

TWO-SIDED CONTROL
=================
Every probe here reports absence, and a probe that always reports
absence proves nothing. `TestTheInstrumentCanFail` points each one at a
subject that IS present and requires the opposite verdict:

    the file probe         ->  `tools/gate.py`, which is present
    the import probe       ->  `tools.gate`, which imports
    the import scanner     ->  three planted import lines
    the scanner, other way ->  prose that names the module and must NOT
                               be a subject
    the existence check    ->  a path that was never in the tree
    the tracked-path probe ->  `tools/`, which has tracked files

THE REVERT CONTROL, RUN 2026-08-22
==================================
Run twice, because the contract has two halves and one revert cannot
exercise both.

    ON THE BRANCH   24 tests collected, 24 passed.

    REVERT 1        The three deleted files were restored from
                    `git show 905c9b0:<path>`, and `.gitignore` was
                    restored with them. 6 FAILED, 18 passed:
                        test_the_tool_is_gone
                        test_the_ledger_is_gone
                        test_its_test_file_is_gone
                        test_the_module_does_not_import
                        test_no_live_python_file_imports_it
                        test_the_gitignore_does_not_declare_the_
                            snapshot_protocol

    REVERT 2        The deletions were kept, and the two REPAIRED
                    callers were restored instead:
                    `tools/migrate_harness.py` and
                    `tests/test_tools_are_reachable.py`. 3 FAILED,
                    22 passed:
                        test_migrate_harness_does_not_name_the_tool
                        test_every_loose_tool_exists[tools/island.py]
                        test_the_tools_inventory_does_not_declare_island
                    In that same state `tests/test_tools_are_reachable.py`
                    itself reported 5 failed, 32 passed, which is the
                    deliberate issue #83 failure this change repairs.

    RESTORED        Both reverts were removed. All 716 files in the
                    working tree kept their sha256, verified byte for
                    byte, caches excluded.
"""

# ruff: noqa: S603
# S607 IS FIXED BY CONSTRUCTION, NOT SUPPRESSED, following the pattern
# measured clean in tests/test_no_committed_backup_copies.py. Every spawn
# below runs git through `_git_exe()`, which resolves an absolute path with
# shutil.which, so a `git.cmd` planted earlier on PATH cannot run under the
# developer's token during a test.
#
# S603 remains and is not avoidable: an all-literal argv draws none, and
# every argv carrying a variable draws one. A resolved executable path is a
# variable by definition. This directive is the residue, narrowed to the one
# rule.
from __future__ import annotations

import importlib
import importlib.util
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# The three files issue #67 deleted, written out. A discovered list would
# shrink in silence; a written one fails when a name returns.
RETIRED_PATHS: tuple[str, ...] = (
    "tools/island.py",
    "tools/.island_ledger.jsonl",
    "tests/test_island_promotion_refuses_stale.py",
)

# The module name that must no longer import.
RETIRED_MODULE = "tools.island"

# The directories the cascade section claimed were tracked on purpose.
CASCADE_DIRECTORIES: tuple[str, ...] = ("_archive", ".session26_backups")

# Every import form that reaches the retired module. Matched at the start
# of a line, with leading space allowed, so that prose naming the module
# inside a sentence is not a subject. Prose cannot route a call.
_IMPORTS_ISLAND = re.compile(
    r"^[ \t]*(?:from[ \t]+tools[ \t]+import[ \t]+island\b"
    r"|import[ \t]+tools\.island\b"
    r"|from[ \t]+tools\.island[ \t]+import\b)",
    re.MULTILINE,
)

# Trees whose Python is live code. `dev_harness/` is excluded: operator law
# forbids editing it, its references are prose in comments, and it never
# imported the module. Historical records are excluded for the same reason
# they are excluded in tests/test_harness_is_reachable.py -- they record
# what was true, and rewriting them would destroy the record.
_LIVE_TREES: tuple[str, ...] = ("src", "tests", "tools")

_GIT = shutil.which("git")


def _git_exe() -> str:
    """Return an absolute git path, or fail. A skip is not evidence."""
    if _GIT is None:
        pytest.fail("git not found; tracked files cannot be enumerated")
    return _GIT


def path_is_absent(relative_path: str) -> bool:
    """Report whether `relative_path` is missing from the working tree.

    This is the instrument for the deletion clause, so a control below
    feeds it a path that IS present and requires False.
    """
    return not (REPO_ROOT / relative_path).exists()


def module_imports(module_name: str) -> bool:
    """Report whether `module_name` imports.

    A control below feeds this a module that does import and requires
    True, so an always-False verdict cannot satisfy the clause above.
    """
    try:
        importlib.import_module(module_name)
    except ImportError:
        return False
    return True


def files_importing_island(text: str) -> bool:
    """Report whether `text` carries an import of the retired module."""
    return _IMPORTS_ISLAND.search(text) is not None


def tracked_paths_under(directory: str) -> list[str]:
    """Every tracked path under `directory`, by `git ls-files`.

    A control below asks for a directory that HAS tracked files and
    requires a non-empty answer, because an empty answer from a broken
    query looks exactly like a clean result.
    """
    result = subprocess.run(
        [_git_exe(), "ls-files", "--", directory],
        cwd=str(REPO_ROOT), capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        pytest.fail(f"git ls-files failed: {result.stderr[:400]}")
    return [line for line in result.stdout.splitlines() if line.strip()]


def loose_tools() -> tuple[str, ...]:
    """The LOOSE_TOOLS list that `tools/migrate_harness.py` copies."""
    module = importlib.import_module("tools.migrate_harness")
    return tuple(module.LOOSE_TOOLS)


def tools_inventory() -> tuple[tuple[str, bool], ...]:
    """The INVENTORY written in the issue #83 guard, loaded by PATH.

    `tests/` carries no `__init__.py`, so the file is not reachable as
    `tests.test_tools_are_reachable`. Loading it by location reads the
    real declaration rather than a copy of it kept here, which would
    drift.
    """
    path = REPO_ROOT / "tests" / "test_tools_are_reachable.py"
    spec = importlib.util.spec_from_file_location(
        "_issue_83_inventory", path)
    if spec is None or spec.loader is None:
        pytest.fail(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return tuple(module.INVENTORY)


class TestTheFilesAreGone:
    """Each of the three, named, so a return fails by name."""

    def test_the_tool_is_gone(self):
        assert path_is_absent("tools/island.py"), (
            "tools/island.py is back. Islands are retired; git branches "
            "do this job. See issue #67.")

    def test_the_ledger_is_gone(self):
        assert path_is_absent("tools/.island_ledger.jsonl"), (
            "tools/.island_ledger.jsonl is back. It is the retired tool's "
            "state file. Read the history with git log instead.")

    def test_its_test_file_is_gone(self):
        assert path_is_absent(
            "tests/test_island_promotion_refuses_stale.py"), (
            "the island test file is back. It pins a tool that no longer "
            "exists, so it can only pass vacuously or fail.")

    @pytest.mark.parametrize("relative_path", RETIRED_PATHS)
    def test_the_path_is_not_tracked(self, relative_path):
        assert tracked_paths_under(relative_path) == [], (
            f"{relative_path} is in the git index again")


class TestNothingImportsIt:
    def test_the_module_does_not_import(self):
        assert not module_imports(RETIRED_MODULE), (
            f"{RETIRED_MODULE} still imports, so the file is back")

    def test_no_live_python_file_imports_it(self):
        offenders = []
        for tree in _LIVE_TREES:
            root = REPO_ROOT / tree
            if not root.is_dir():
                continue
            for path in root.rglob("*.py"):
                text = path.read_text(encoding="utf-8", errors="replace")
                if files_importing_island(text):
                    offenders.append(
                        path.relative_to(REPO_ROOT).as_posix())
        assert not offenders, (
            f"these files import the retired module: {sorted(offenders)}")


class TestTheCallersWereRepaired:
    """The two callers that would break, not merely mention the tool."""

    def test_migrate_harness_does_not_name_the_tool(self):
        assert "tools/island.py" not in loose_tools(), (
            "migrate_harness.LOOSE_TOOLS names a file that is not there. "
            "It REFUSES a missing source by name, so every migration "
            "would stop.")

    @pytest.mark.parametrize("relative_path", loose_tools())
    def test_every_loose_tool_exists(self, relative_path):
        """The clause above is only useful while this one holds."""
        assert (REPO_ROOT / relative_path).is_file(), (
            f"migrate_harness copies {relative_path}, which is not there")

    def test_the_tools_inventory_does_not_declare_island(self):
        """`tests/` is not a package, so the file is loaded by path."""
        declared = {stem for stem, _runs in tools_inventory()}
        assert "island" not in declared, (
            "the issue #83 inventory still declares island")


class TestTheCascadeSectionIsGone:
    """`.gitignore` may not claim a rollback that does not exist."""

    def test_the_gitignore_does_not_declare_the_snapshot_protocol(self):
        text = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
        assert "ARE tracked on purpose" not in text, (
            ".gitignore declares the cascade snapshot protocol again")

    @pytest.mark.parametrize("directory", CASCADE_DIRECTORIES)
    def test_the_directory_holds_no_tracked_file(self, directory):
        tracked = tracked_paths_under(directory)
        assert tracked == [], (
            f"{directory}/ is tracked again, {len(tracked)} file(s). "
            "Git history is the rollback mechanism.")


class TestTheInstrumentCanFail:
    """Every probe above reports absence. Prove each can report presence."""

    def test_the_file_probe_sees_a_file_that_is_present(self):
        assert not path_is_absent("tools/gate.py")

    def test_the_import_probe_imports_a_module_that_is_present(self):
        assert module_imports("tools.gate")

    def test_the_import_probe_refuses_a_module_that_is_absent(self):
        assert not module_imports("tools.no_such_module_at_all")

    def test_the_scanner_finds_a_planted_import(self):
        for planted in (
            "from tools import island\n",
            "import tools.island\n",
            "    from tools.island import promote\n",
        ):
            assert files_importing_island(planted), planted

    def test_the_scanner_ignores_prose_that_names_the_module(self):
        prose = (
            "# tools/island.py was deleted under issue #67.\n"
            "MESSAGE = 'the old tools import island line is gone'\n"
        )
        assert not files_importing_island(prose)

    def test_the_tracked_probe_finds_a_directory_that_is_tracked(self):
        assert tracked_paths_under("tools"), (
            "git ls-files returned nothing for tools/, so every empty "
            "answer above is a broken query, not a clean result")

    def test_the_existence_check_can_fail(self):
        assert not (REPO_ROOT / "tools/never_existed.py").is_file()
