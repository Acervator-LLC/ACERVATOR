"""Every archetype stays reachable from every caller that names it.

``ARCHETYPES`` pins each module and the class it exposes; each is imported,
asked for a ``review`` method, and spawned as ``python -m <module>``. Every
harness module string written into a ``CALLERS`` file must resolve, and every
archetype must be named by at least one caller. ``_OLD_PATH_RE`` requires the
pre-move path to be gone outside ``_ALLOWED_PREFIXES`` and ``_ALLOWED_EXACT``,
and ``TestTheCallerSearchCanFail`` is the control for the resolver.
"""

# ruff: noqa: S603
# `sys.executable` and `_git_exe()` are resolved paths, so an all-literal argv
# is impossible.
from __future__ import annotations

import importlib
import re
import shutil
import subprocess
import sys
import warnings
from pathlib import Path

import pytest

from tools import claude_home
from tools.claude_home import absent_reason, find

REPO = Path(__file__).resolve().parents[1]

_GIT = shutil.which("git")


def _git_exe() -> str:
    """Absolute git path, or fail loudly. A skipped test is not evidence."""
    if _GIT is None:
        pytest.fail("git not found; tracked files cannot be enumerated")
    return _GIT


# (module, the class it exposes). Written out, not discovered: a globbed
# list shrinks in silence when a file disappears.
ARCHETYPES: tuple[tuple[str, str], ...] = (
    ("dev_harness.harness.coding_archetype", "CodingArchetype"),
    ("dev_harness.harness.gui_archetype", "GUIArchetype"),
    ("dev_harness.harness.ta_archetype", "TAArchetype"),
    ("dev_harness.harness.docs_archetype", "DocsArchetype"),
    ("dev_harness.harness.watchdog_archetype", "WatchdogArchetype"),
)

# Files that name a harness module by string and import it later. The hook
# scripts live outside the repository and `caller_path` resolves them.
HOOK_CALLERS: tuple[str, ...] = (
    "archetype_gate.py",
    "prompt_router.py",
    "verify_release_gate.py",
)

REPO_CALLERS: tuple[str, ...] = (
    "tools/gate.py",
    "dev_harness/touchset.py",
    "dev_harness/harness/check_release_readiness.py",
)

CALLERS: tuple[str, ...] = HOOK_CALLERS + REPO_CALLERS


def caller_path(name: str) -> Path | None:
    """Where `name` is on this machine, or None if it is not installed.

    A repository caller is always answered, because it is tracked and a
    clone carries it. A hook caller can be absent, and None says so.
    """
    if name in HOOK_CALLERS:
        return find("hooks", name)
    return REPO / name


_UNINSTALLED = [name for name in HOOK_CALLERS if caller_path(name) is None]
if _UNINSTALLED:
    warnings.warn(absent_reason("hooks"), stacklevel=1)


def _skip_if_uninstalled(name: str) -> None:
    """Skip on an absent hook caller, naming every path searched."""
    if caller_path(name) is None:
        pytest.skip(absent_reason("hooks", name))


# Matches a dotted harness module path wherever it appears in caller text:
# an import statement, a list literal, a subprocess argv or a printed hint.
_MODULE_RE = re.compile(r"\bdev_harness\.harness\.[A-Za-z_][A-Za-z0-9_.]*")

# The harness's old home. `_HISTORY` names the trees whose records keep it
# on purpose; `test_the_named_exceptions_still_exist` fails when one is gone.
_OLD_PATH_RE = re.compile(r"tools[./]harness")
_HISTORY = (
    "docs/audits",
    "docs/engineering-notes",
    "docs-archive/llm-session-history/"
    "CHANGELOG-narrative-2026-08-04-to-2026-08-25.md",
)

# Paths that name the old harness path on purpose: the harness's own prose,
# this file's controls, and the handoffs. Named, never globbed.
_ALLOWED_PREFIXES = ("dev_harness/",)
_ALLOWED_EXACT = frozenset(
    {
        "tests/test_harness_is_reachable.py",
        "ACERVATOR_HOP7.md",
        "ACERVATOR_HOP8.md",
    }
)


def probe_import(module_name: str, class_name: str) -> tuple[bool, str]:
    """Report whether `module_name` imports and carries a usable archetype.

    Returns (reachable, reason). `reason` is '' when reachable. This helper
    is the instrument, so a control test below feeds it a module that does
    not exist and requires False.
    """
    try:
        mod = importlib.import_module(module_name)
    except ImportError as exc:
        return False, f"import failed: {exc}"
    cls = getattr(mod, class_name, None)
    if cls is None:
        return False, f"{module_name} has no {class_name}"
    if not callable(getattr(cls, "review", None)):
        return False, f"{class_name}.review is not callable"
    return True, ""


def probe_module_only(module_name: str) -> tuple[bool, str]:
    """Report whether `module_name` imports at all. No class contract."""
    try:
        importlib.import_module(module_name)
    except ImportError as exc:
        return False, f"import failed: {exc}"
    return True, ""


def caller_modules(text: str) -> list[str]:
    """Every harness module string in `text`, de-duplicated and sorted."""
    return sorted(set(_MODULE_RE.findall(text)))


class TestArchetypesImport:
    @pytest.mark.parametrize(("module", "klass"), ARCHETYPES)
    def test_archetype_imports_and_exposes_review(self, module, klass):
        ok, why = probe_import(module, klass)
        assert ok, f"{module} is UNREACHABLE: {why}"


class TestArchetypesRunAsPrograms:
    @pytest.mark.parametrize(("module", "klass"), ARCHETYPES)
    def test_archetype_answers_python_dash_m(self, module, klass):
        """`python -m <module>` must reach the archetype's own main().

        Called with no target, each archetype prints its usage line and
        exits non-zero. A module that is not importable exits 1 with a
        traceback naming ModuleNotFoundError instead, which is what this
        assertion separates.
        """
        run = subprocess.run(
            [sys.executable, "-m", module],
            cwd=str(REPO),
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        blob = run.stdout + run.stderr
        assert (
            "ModuleNotFoundError" not in blob
        ), f"{module} did not load as a program:\n{blob[:800]}"
        assert "usage:" in blob.lower(), f"{module} reached no main():\n{blob[:800]}"


class TestNoCallerIsStale:
    @pytest.mark.parametrize("rel", CALLERS)
    def test_caller_file_exists(self, rel):
        """Existence only, and on its own it proves nothing.

        This assertion would stay green against an empty file. The one
        below reads the file and resolves every module it names, and that
        is where the coverage is.
        """
        _skip_if_uninstalled(rel)
        path = caller_path(rel)
        assert path is not None
        assert path.is_file(), f"caller {rel} is missing"

    @pytest.mark.parametrize("rel", CALLERS)
    def test_every_module_named_by_the_caller_resolves(self, rel):
        _skip_if_uninstalled(rel)
        path = caller_path(rel)
        assert path is not None
        named = caller_modules(path.read_text(encoding="utf-8"))
        assert named, f"{rel} names no harness module at all"
        broken = [
            (m, probe_module_only(m)[1]) for m in named if not probe_module_only(m)[0]
        ]
        assert not broken, f"{rel} names unreachable modules: {broken}"

    def test_all_five_archetypes_are_named_by_some_caller(self):
        """Check 3 alone passes on a tree with no callers left. This does not.

        Deliberately NOT skipped when the hooks are uninstalled. The four
        repository callers name all five archetypes between them, so the
        check keeps its full force on a machine with no harness, and a
        deletion inside the tree still fails it.
        """
        seen: set[str] = set()
        for rel in CALLERS:
            path = caller_path(rel)
            if path is None:
                continue
            seen.update(caller_modules(path.read_text(encoding="utf-8")))
        missing = [m for m, _ in ARCHETYPES if m not in seen]
        assert not missing, f"no caller invokes: {missing}"

    def test_the_repository_callers_alone_name_all_five(self):
        """The reason the test above may skip nothing.

        If this ever fails, an uninstalled machine would stop measuring
        check 4, and the skip above would start hiding a real gap.
        """
        seen: set[str] = set()
        for rel in REPO_CALLERS:
            seen.update(caller_modules((REPO / rel).read_text(encoding="utf-8")))
        missing = [m for m, _ in ARCHETYPES if m not in seen]
        assert not missing, (
            f"only a hook names {missing}; the skip for an uninstalled "
            f"harness would now hide a deletion"
        )


class TestTheCallerSearchCanFail:
    """Positive control for the hook-caller search. Runs in both states."""

    def test_an_empty_home_reports_every_hook_caller_absent(
        self, tmp_path, monkeypatch
    ):
        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setattr(claude_home, "REPO", tmp_path / "no-such-repo")
        monkeypatch.setenv("HOME", str(home))
        monkeypatch.setenv("USERPROFILE", str(home))
        for name in HOOK_CALLERS:
            assert (
                claude_home.find("hooks", name) is None
            ), f"the search claims {name} under a home that holds none"

    def test_a_planted_hook_caller_resolves(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        planted = home / claude_home.CLAUDE_DIR_NAME / "hooks"
        planted.mkdir(parents=True)
        for name in HOOK_CALLERS:
            (planted / name).write_text("", encoding="utf-8")
        monkeypatch.setattr(claude_home, "REPO", tmp_path / "no-such-repo")
        monkeypatch.setenv("HOME", str(home))
        monkeypatch.setenv("USERPROFILE", str(home))
        for name in HOOK_CALLERS:
            assert claude_home.find("hooks", name) == planted / name

    def test_a_repository_caller_is_never_reported_absent(self):
        """A tracked file travels with the clone. None here means the
        splitting of the two lists has gone wrong."""
        for rel in REPO_CALLERS:
            assert caller_path(rel) is not None


class TestOldPathIsGone:
    def test_the_old_module_path_does_not_import(self):
        with pytest.raises(ImportError):
            importlib.import_module("tools.harness.coding_archetype")

    def test_the_old_directory_does_not_exist(self):
        assert not (REPO / "tools" / "harness").exists()

    def test_no_live_file_still_points_at_the_old_path(self):
        listing = subprocess.run(
            [_git_exe(), "ls-files"],
            cwd=str(REPO),
            capture_output=True,
            text=True,
            check=False,
        )
        assert listing.returncode == 0, "git could not enumerate tracked files"
        offenders = []
        for rel in listing.stdout.splitlines():
            if not rel or rel.startswith(_HISTORY) or rel in _HISTORY:
                continue
            path = REPO / rel
            if not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if _OLD_PATH_RE.search(text):
                offenders.append(rel)
        stale = {
            o
            for o in offenders
            if not o.startswith(_ALLOWED_PREFIXES) and o not in _ALLOWED_EXACT
        }
        assert not stale, f"live files still name the old harness path: {sorted(stale)}"

    def test_the_named_exceptions_still_exist(self):
        """An allowance that outlives its file would widen the check silently."""
        for rel in _ALLOWED_EXACT:
            assert (REPO / rel).is_file(), f"stale allowance for {rel}"


class TestTheInstrumentCanFail:
    """Positive controls. Without these the file proves nothing."""

    def test_probe_rejects_a_module_that_does_not_exist(self):
        ok, why = probe_import(
            "dev_harness.harness.no_such_archetype", "NoSuchArchetype"
        )
        assert not ok
        assert "import failed" in why

    def test_probe_rejects_the_old_path(self):
        ok, why = probe_import("tools.harness.coding_archetype", "CodingArchetype")
        assert not ok, "the old path still imports; the move is incomplete"

    def test_probe_rejects_a_module_without_the_class(self):
        ok, why = probe_import("dev_harness.harness.report", "CodingArchetype")
        assert not ok
        assert "no CodingArchetype" in why

    def test_caller_scan_rejects_a_bogus_module_string(self):
        named = caller_modules('mods.append("dev_harness.harness.ghost_archetype")')
        assert named == ["dev_harness.harness.ghost_archetype"]
        ok, why = probe_module_only(named[0])
        assert not ok
        assert "import failed" in why

    def test_caller_scan_finds_nothing_in_text_that_names_nothing(self):
        assert caller_modules("no module names here at all") == []
