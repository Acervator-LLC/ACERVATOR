"""A backup copy of a source file may not be a tracked file.

WHAT WAS MEASURED
=================
Issue #82, on 2026-08-22, in a clone at commit 29d7f71. The tree held 705
tracked files. Four of them were hand-made backup copies:

    853909 B  settings.local.json.pre_consolidation_20260806 (.claude)
    287335 B  src/gui/main_window.py.PRIVACY_ARC_BACKUP_2026-06-14
    101970 B  src/gui/bot_visualizer.py.BOT_SWARM_ARC_BACKUP_2026-06-14
     34647 B  src/gui/history_tab.py.D01_BACKUP_2026-06-14

Each one was checked for three hazards, because a backup of a source file
is not inert.

IS IT IMPORTABLE?
    No. All four carry text after the extension, so the name is not a
    module name. Measured: ``glob.glob('src/**/*.py', recursive=True)``
    returned 164 files and none of them was a backup, and
    ``Path('src').rglob('*.py')`` returned none either. That is the only
    reason these four were harmless to the interpreter, and it is a
    property of the name, not of the content. A copy whose stem ended in
    "_backup" and which kept ".py" last would import.

DOES ANY TOOL GLOB IT?
    Yes. Both spec files pass ``(<root>/src, 'src')`` to
    ``Analysis(datas=...)``. PyInstaller expands a directory entry into
    every file under it. Measured with PyInstaller 6.22.2, by calling its
    own ``format_binaries_and_datas([('src', 'src')], workingdir='.')``:
    the entry expanded to 238 files, and three of them were the GUI
    backups. So every Windows and macOS build shipped all three stale
    copies inside the bundle. The release zip did not, which is why the
    fault stayed hidden.

    Nothing else read them. pytest collects from ``tests`` only, and
    collection returned 7392 tests. Vulture reads ``*.py`` and reported
    no finding in any backup. Coverage traces imported modules, and it
    omits ``src/gui/*`` as well.

DOES ANYTHING REFERENCE IT BY NAME?
    Two files did, and only one was a defect.

    tools/build_release_zip.py holds three of the names as substrings in
    JUNK_NAME_SUBSTRINGS. That tool walks the file system with
    ``_REPO.rglob('*')``, not the index, so the list filters scratch
    copies that are never tracked. It stays correct and useful after the
    four are gone, and it already carries an entry for a copy that is
    not in the tree. It was left as written.

    tests/test_harness_is_reachable.py named the settings backup in
    _HISTORY, to skip it while scanning tracked files for the old harness
    path. That entry existed only for the deleted file, so it was
    removed in the same change.

WHY DELETION LOSES NOTHING
    All four were committed, so git holds them. Measured: for each file
    the sha256 of ``git show HEAD:<path>`` equalled the sha256 of the
    file on disk. The settings backup entered at commit ec6a63c; the
    three GUI copies entered at commit be6aa04.

    All three live GUI files are present, and each is larger than its
    backup: main_window.py 9993 lines against 5531, bot_visualizer.py
    3718 against 2265, history_tab.py 1320 against 809. The backups are
    older states.

    The history tab copy also imported ``sadp._tools.trade_grader`` at
    its line 703. No directory of that name is in the tree and no commit
    ever added one, so that copy named a package this repository has
    never held.

    The settings backup copied a file that a global ignore rule keeps out
    of every commit, so it could never track its original. It held 3866
    permission entries, 2598 mentions of the retired SADP subsystem and
    62 mentions of the old harness path.

WHY A SEPARATE FILE
===================
tests/test_no_missing_file_references.py is the sibling guard from issues
69 and 89. It was not extended, for one reason: it and this file read
different things. That file opens four shipped documents and asks whether
the paths inside them resolve, so its input is file CONTENT and its
subject is a claim. This file reads the output of ``git ls-files`` and
asks whether a NAME has the shape of a backup, so its input is the index
and its subject is a file. Its docstring states one thesis, "a shipped
file may not name a path that is not in the tree", and a shape rule over
705 tracked files would make that thesis false.

WHAT THE SHAPE RULE IS
======================
Three clauses, each one narrow, so that a legitimate name cannot trip it.
The rule reads the last element of the path and nothing else.

    1. A source extension is not the last extension.
       ``main_window.py.PRIVACY_ARC_BACKUP_2026-06-14`` matches.
       ``settings.local.json`` does not, because ``.local`` is not a
       source extension and ``.json`` is last.
    2. The last extension is a backup extension, or the name ends in
       a tilde.
    3. The stem ends in a backup marker, with an optional date or
       number after it. A stem of "history_tab_backup" matches, and so
       does "notes_backup_2026-06-14". A stem of "backup_manager" does
       not, because the marker must END the stem.

Clause 3 carries the importable case, which is the dangerous one.

The rule never opens the file, so CONTENT may say anything. A control
below points it at tools/build_release_zip.py, which says "backup" many
times, and requires the rule to stay quiet.

TWO-SIDED CONTROL
==================
Driven both ways on 2026-08-22.

    IN THE SUITE  test_the_scan_catches_a_planted_backup builds a git
                  repository in a temporary directory, tracks one file
                  named like a backup, and requires the same enumeration
                  and the same rule to report it. Without it this file
                  could pass because the scan found nothing to read.

    ON THE REPO   A copy named like the history tab backup, stamped
                  2026-08-22, was written into the working tree and
                  staged. test_no_backup_shaped_file_is_tracked failed
                  and named that file. The plant was then removed. Every
                  other file in the tree kept its sha256.
"""

# ruff: noqa: S603
# S607 IS FIXED BY CONSTRUCTION, NOT SUPPRESSED, following the reasoning at
# the top of dev_harness/harness/coding_archetype.py and the pattern already
# measured clean in tests/test_harness_is_reachable.py. Every spawn below
# runs git through `_git_exe()`, which resolves an absolute path with
# shutil.which, so a `git.cmd` planted earlier on PATH cannot run under the
# developer's token during a test.
#
# S603 remains and is not avoidable: an all-literal argv draws none, and
# every argv carrying a variable draws one. A resolved executable path is a
# variable by definition. This directive is the residue, narrowed to the one
# rule.
from __future__ import annotations

import glob
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# Extensions that make a name a source or config file. A name that carries
# one of these and then carries more text has been renamed away from its
# real type, which is what a hand-made copy does.
SOURCE_EXTENSIONS: tuple[str, ...] = (
    "py",
    "pyw",
    "json",
    "jsonl",
    "md",
    "toml",
    "txt",
    "cfg",
    "ini",
    "yml",
    "yaml",
    "spec",
    "sh",
    "ps1",
    "bat",
    "csv",
    "sql",
    "service",
)

# Extensions that an editor or a person appends to make a copy.
BACKUP_EXTENSIONS: tuple[str, ...] = (
    "bak",
    "orig",
    "rej",
    "swp",
    "save",
    "old",
    "tmp",
    "backup",
)

# Words that end the stem of a copy. The marker must END the stem, with at
# most a date or a number after it, so that a file whose name merely opens
# with one of these words is not a subject.
STEM_MARKERS: tuple[str, ...] = ("backup", "bak", "old", "orig", "copy")

_EXTENSION_NOT_LAST = re.compile(
    r"\.(?:" + "|".join(SOURCE_EXTENSIONS) + r")\.[^.]", re.IGNORECASE
)
_BACKUP_EXTENSION = re.compile(
    r"\.(?:" + "|".join(BACKUP_EXTENSIONS) + r")$", re.IGNORECASE
)
_STEM_MARKER = re.compile(
    r"_(?:" + "|".join(STEM_MARKERS) + r")"
    r"(?:[_-]?(?:\d{4}[-_]?\d{2}[-_]?\d{2}|\d+))?$",
    re.IGNORECASE,
)

# The four copies issue #82 removed, written out so that a reader can see
# what the rule was built against. The settings entry is joined from its
# directory because the path no longer resolves, and a dead path written
# whole reads as a live claim.
_CLAUDE_DIR = ".claude"
REMOVED_BY_ISSUE_82: tuple[str, ...] = (
    "src/gui/main_window.py.PRIVACY_ARC_BACKUP_2026-06-14",
    "src/gui/bot_visualizer.py.BOT_SWARM_ARC_BACKUP_2026-06-14",
    "src/gui/history_tab.py.D01_BACKUP_2026-06-14",
    f"{_CLAUDE_DIR}/settings.local.json.pre_consolidation_20260806",
)

_GIT = shutil.which("git")


def _git_exe() -> str:
    """Return an absolute git path, or fail. A skip is not evidence."""
    if _GIT is None:
        pytest.fail("git not found; tracked files cannot be enumerated")
    return _GIT


def backup_shape(relative_path: str) -> str:
    """Return why a name has the shape of a backup, or '' if it has not.

    The reason is returned rather than a bool, so that a failure names the
    clause that fired. Only the last element of the path is read.
    """
    name = relative_path.replace("\\", "/").rsplit("/", 1)[-1]
    if name.endswith("~"):
        return "the name ends with a tilde"
    if _EXTENSION_NOT_LAST.search(name):
        return "a source extension is not the last extension"
    if _BACKUP_EXTENSION.search(name):
        return "the last extension is a backup extension"
    stem = name.rsplit(".", 1)[0] if "." in name else name
    if _STEM_MARKER.search(stem):
        return "the stem ends with a backup marker"
    return ""


def tracked_files(repo: Path) -> list[str]:
    """Return every path in the index of `repo`, as a posix string."""
    result = subprocess.run(
        [_git_exe(), "ls-files"],
        cwd=str(repo),
        capture_output=True,
        text=True,
        check=True,
    )
    return [line for line in result.stdout.replace("\r\n", "\n").split("\n") if line]


def offenders(repo: Path) -> list[str]:
    """Return 'path: reason' for every tracked name of a backup shape."""
    return [
        f"{path}: {reason}"
        for path in tracked_files(repo)
        if (reason := backup_shape(path))
    ]


# ── the guard ────────────────────────────────────────────────────────


def test_no_backup_shaped_file_is_tracked() -> None:
    """git holds every prior version, so a copy beside the file is rot.

    A hand-made copy is a second source of truth that nothing keeps in
    step. It also travels: the two spec files ship the whole ``src``
    directory as data, so a copy under ``src`` reaches every build.
    """
    assert offenders(REPO_ROOT) == []


def test_the_four_copies_issue_82_removed_are_gone() -> None:
    """The named copies may not come back under their own names."""
    present = [name for name in REMOVED_BY_ISSUE_82 if (REPO_ROOT / name).exists()]
    assert present == []


def test_no_gui_source_file_carries_a_suffix_after_its_extension() -> None:
    """The three GUI copies were the ones a build shipped.

    ``datas`` copies a directory whole, so this glob is the shape that
    reached the bundle. It reads the working tree rather than the index,
    because PyInstaller reads the working tree.
    """
    assert glob.glob("src/**/*.py.*", root_dir=str(REPO_ROOT), recursive=True) == []


# ── controls: the rule fires ─────────────────────────────────────────


@pytest.mark.parametrize(
    "name",
    [
        # Shapes the tree really held.
        "main_window.py.PRIVACY_ARC_BACKUP_2026-06-14",
        "bot_visualizer.py.BOT_SWARM_ARC_BACKUP_2026-06-14",
        "history_tab.py.D01_BACKUP_2026-06-14",
        "settings.local.json.pre_consolidation_20260806",
        "scrumming_bot.py.RECOVERY_PRE_v3_23_7.BAK",
        # The importable shape. This one is the danger.
        "history_tab_backup.py",
        "history_tab_backup_2026-06-14.py",
        "history_tab_old.py",
        "history_tab_copy.py",
        "history_tab_orig.py",
        # Editor and shell leavings.
        "history_tab.py.bak",
        "history_tab.py~",
        "history_tab.orig",
        "settings.json.save",
    ],
)
def test_the_rule_catches_a_backup_shape(name: str) -> None:
    """Every shape the tree has held, and the importable shape."""
    assert backup_shape(name) != ""


def test_the_importable_shape_keeps_its_extension_last() -> None:
    """Name the reason the four removed copies could not be imported.

    A copy that keeps ".py" last is read by every tool that globs
    ``*.py``, so clause 3 must catch it on the stem alone. This test
    fails if clause 1 is ever widened to cover clause 3's cases, which
    would leave the importable shape to clause 1 and hide the gap.
    """
    importable = "history_tab_backup.py"
    assert _EXTENSION_NOT_LAST.search(importable) is None
    assert backup_shape(importable) == "the stem ends with a backup marker"


def test_the_rule_reads_the_last_path_element_only() -> None:
    """A directory name may not decide the verdict."""
    for directory in ("", "src/", "src/gui/", "a/b/c/"):
        assert backup_shape(directory + "history_tab_backup.py") != ""
        assert backup_shape(directory + "history_tab.py") == ""
    assert (
        backup_shape("backup/history_tab.py") == ""
    ), "a directory called backup does not make its files copies"


# ── controls: the rule stays quiet ───────────────────────────────────


@pytest.mark.parametrize(
    "name",
    [
        "build_release_zip.py",
        "test_no_committed_backup_copies.py",
        "backup_manager.py",
        "test_backup_flow.py",
        "scrumming_v3_sim.py",
        "test_nuclear_panel_drives_v2.py",
        ".vale.ini",
        ".release_ready.json",
        "settings.local.json",
        "acervator.service",
        "Acervator_win.spec",
        "2026-08-04_needed_fixes_list.md",
        "README.md",
    ],
)
def test_the_rule_clears_a_legitimate_name(name: str) -> None:
    """A narrow rule is the point. A loose one gets switched off."""
    assert backup_shape(name) == ""


def test_a_file_whose_content_says_backup_is_not_a_subject() -> None:
    """The rule reads the name, so content may say anything.

    tools/build_release_zip.py carries the word many times, in the
    JUNK_NAME_SUBSTRINGS list that strips scratch copies from a release
    zip. It is a live tool and it must stay clear of this guard.
    """
    path = REPO_ROOT / "tools" / "build_release_zip.py"
    assert path.is_file()
    text = path.read_text(encoding="utf-8", errors="replace")
    assert (
        text.lower().count("backup") > 5
    ), "the control is vacuous unless the file really says backup"
    assert backup_shape(str(path.relative_to(REPO_ROOT))) == ""


# ── control: the instrument can fail ─────────────────────────────────


def test_the_scan_catches_a_planted_backup(tmp_path: Path) -> None:
    """Plant a tracked copy in a fresh repository and require a hit.

    This drives the whole instrument, not the rule alone: git enumerates
    the index, and the rule reads what git returned. Without it, this
    file would pass on an empty listing and prove nothing.
    """
    git = _git_exe()
    repo = tmp_path / "planted"
    (repo / "src" / "gui").mkdir(parents=True)
    for command in (
        [git, "init", "-q"],
        [git, "config", "user.email", "control@example.invalid"],
        [git, "config", "user.name", "control"],
    ):
        subprocess.run(command, cwd=str(repo), capture_output=True, check=True)

    live = "src/gui/history_tab.py"
    (repo / live).write_text("VALUE = 1\n", encoding="utf-8")
    subprocess.run(
        [git, "add", "--", live], cwd=str(repo), capture_output=True, check=True
    )
    assert offenders(repo) == [], "the clean repository must start green"

    plant = "src/gui/history_tab.py.D01_BACKUP_2026-06-14"
    (repo / plant).write_text("VALUE = 0\n", encoding="utf-8")
    subprocess.run(
        [git, "add", "--", plant], cwd=str(repo), capture_output=True, check=True
    )

    found = offenders(repo)
    assert len(found) == 1, found
    assert found[0].startswith(plant + ": ")


def test_the_scan_reads_a_real_index() -> None:
    """A count guards against an enumeration that returns nothing.

    ``git ls-files`` returns an empty list in a directory that is not a
    repository, and every assertion above would then hold vacuously.
    """
    assert len(tracked_files(REPO_ROOT)) > 500
