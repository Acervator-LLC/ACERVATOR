"""Every archetype stays reachable from every caller that names it.

Why this file exists
--------------------
Issue #84 moved the harness from `tools/harness/` to `dev_harness/harness/`.
The operator's ruling on that move was explicit:

    "Yeah, we can move but we are not retiring or disabling it at all.
     It has to be used."

A move cannot disable an archetype loudly. Every caller names its archetype
by a STRING, and the two callers that matter route by string at run time:

* `.claude/hooks/archetype_gate.py` builds a module list, then imports it.
* `dev_harness/touchset.py` maps module name to class name, then imports it.

`importlib.import_module` on a stale string raises inside a caller that
already catches import failure and degrades. So a missed caller does not
crash the gate. It removes one archetype from the run and reports the rest
as green. That is the exact outcome the ruling forbids, and no other test in
the suite would see it.

What this file measures
-----------------------
1. Each of the five archetypes imports at its declared path and exposes a
   `review` method. That is reachability at the API level.
2. Each archetype answers `python -m <module>` as a program. That is
   reachability at the CLI level, which is how the operator and the skills
   invoke them.
3. Every harness module string written into a caller file resolves. This is
   the anti-stale-caller check: it reads the callers, not a list kept here,
   so a caller that keeps an old path fails this file.
4. The five archetypes are each named by at least one caller. Without this,
   check 3 would pass on a tree where every caller had been deleted.
5. The OLD path is gone. A stale caller must break, not silently skip.

Two-sided control
-----------------
`test_probe_rejects_a_module_that_does_not_exist` and
`test_caller_scan_rejects_a_bogus_module_string` point the same helpers at a
wrong path and require them to report FAILURE. Without those two, a helper
that always returned "reachable" would satisfy every assertion above.
"""

# ruff: noqa: S603
# S607 IS FIXED BY CONSTRUCTION, NOT SUPPRESSED, following the reasoning at the
# top of dev_harness/harness/coding_archetype.py and the pattern already
# measured clean in tests/test_pre_push_gate_hook.py. Both spawns below use an
# absolute executable path — the interpreter via `sys.executable`, git via
# `_git_exe()` resolved through shutil.which — so a `git.cmd` planted earlier
# on PATH cannot run under the developer's token during a test.
#
# S603 remains and is not avoidable: an all-literal argv draws none, and every
# argv carrying a variable draws one. A resolved interpreter path is a variable
# by definition. This directive is the residue, narrowed to the one rule.
from __future__ import annotations

import importlib
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

_GIT = shutil.which("git")


def _git_exe() -> str:
    """Absolute git path, or fail loudly. A skipped test is not evidence."""
    if _GIT is None:
        pytest.fail("git not found; tracked files cannot be enumerated")
    return _GIT

# The five archetypes, and the class each one exposes. This list is the
# CONTRACT. It is deliberately written out rather than discovered, because a
# discovered list shrinks silently when a file disappears.
ARCHETYPES: tuple[tuple[str, str], ...] = (
    ("dev_harness.harness.coding_archetype", "CodingArchetype"),
    ("dev_harness.harness.gui_archetype", "GUIArchetype"),
    ("dev_harness.harness.ta_archetype", "TAArchetype"),
    ("dev_harness.harness.docs_archetype", "DocsArchetype"),
    ("dev_harness.harness.watchdog_archetype", "WatchdogArchetype"),
)

# Files that name a harness module by string and import it later. A stale
# string in any of these is a silently skipped check.
CALLERS: tuple[str, ...] = (
    ".claude/hooks/archetype_gate.py",
    ".claude/hooks/prompt_router.py",
    ".claude/hooks/verify_release_gate.py",
    "tools/gate.py",
    "tools/emitter_registry_check.py",
    "dev_harness/touchset.py",
    "dev_harness/harness/check_release_readiness.py",
)

# Matches a dotted harness module path wherever it appears in caller text:
# an import statement, a list literal, a subprocess argv or a printed hint.
_MODULE_RE = re.compile(r"\bdev_harness\.harness\.[A-Za-z_][A-Za-z0-9_.]*")

# The old home. Historical records keep it on purpose and are excluded.
_OLD_PATH_RE = re.compile(r"tools[./]harness")
_HISTORY = ("docs/audits", "docs/harness_archive", "CHANGELOG.md",
            "tools/.island_ledger.jsonl",
            ".claude/settings.local.json.pre_consolidation_20260806")

# Two sets name the old path on purpose and stay green.
#   1. The harness's own prose. Operator law forbids editing an archetype's
#      contents, so comments inside it keep the wording they shipped with.
#      Prose cannot route a call, so a stale comment disables no check.
#   2. THIS file. Its controls import the old path deliberately, to prove the
#      old path is gone. Without them the whole file could pass vacuously.
_ALLOWED_PREFIXES = ("dev_harness/",)
_ALLOWED_EXACT = frozenset({"tests/test_harness_is_reachable.py"})


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
            cwd=str(REPO), capture_output=True, text=True,
            timeout=120, check=False,
        )
        blob = run.stdout + run.stderr
        assert "ModuleNotFoundError" not in blob, (
            f"{module} did not load as a program:\n{blob[:800]}"
        )
        assert "usage:" in blob.lower(), (
            f"{module} reached no main():\n{blob[:800]}"
        )


class TestNoCallerIsStale:
    @pytest.mark.parametrize("rel", CALLERS)
    def test_caller_file_exists(self, rel):
        assert (REPO / rel).is_file(), f"caller {rel} is missing"

    @pytest.mark.parametrize("rel", CALLERS)
    def test_every_module_named_by_the_caller_resolves(self, rel):
        named = caller_modules((REPO / rel).read_text(encoding="utf-8"))
        assert named, f"{rel} names no harness module at all"
        broken = [(m, probe_module_only(m)[1]) for m in named
                  if not probe_module_only(m)[0]]
        assert not broken, f"{rel} names unreachable modules: {broken}"

    def test_all_five_archetypes_are_named_by_some_caller(self):
        """Check 3 alone passes on a tree with no callers left. This does not."""
        seen: set[str] = set()
        for rel in CALLERS:
            seen.update(caller_modules((REPO / rel).read_text(encoding="utf-8")))
        missing = [m for m, _ in ARCHETYPES if m not in seen]
        assert not missing, f"no caller invokes: {missing}"


class TestOldPathIsGone:
    def test_the_old_module_path_does_not_import(self):
        with pytest.raises(ImportError):
            importlib.import_module("tools.harness.coding_archetype")

    def test_the_old_directory_does_not_exist(self):
        assert not (REPO / "tools" / "harness").exists()

    def test_no_live_file_still_points_at_the_old_path(self):
        listing = subprocess.run(
            [_git_exe(), "ls-files"], cwd=str(REPO),
            capture_output=True, text=True, check=False,
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
        stale = {o for o in offenders
                 if not o.startswith(_ALLOWED_PREFIXES)
                 and o not in _ALLOWED_EXACT}
        assert not stale, (
            f"live files still name the old harness path: {sorted(stale)}"
        )

    def test_the_named_exceptions_still_exist(self):
        """An allowance that outlives its file would widen the check silently."""
        for rel in _ALLOWED_EXACT:
            assert (REPO / rel).is_file(), f"stale allowance for {rel}"


class TestTheInstrumentCanFail:
    """Positive controls. Without these the file proves nothing."""

    def test_probe_rejects_a_module_that_does_not_exist(self):
        ok, why = probe_import(
            "dev_harness.harness.no_such_archetype", "NoSuchArchetype")
        assert not ok
        assert "import failed" in why

    def test_probe_rejects_the_old_path(self):
        ok, why = probe_import(
            "tools.harness.coding_archetype", "CodingArchetype")
        assert not ok, "the old path still imports; the move is incomplete"

    def test_probe_rejects_a_module_without_the_class(self):
        ok, why = probe_import("dev_harness.harness.report", "CodingArchetype")
        assert not ok
        assert "no CodingArchetype" in why

    def test_caller_scan_rejects_a_bogus_module_string(self):
        named = caller_modules(
            'mods.append("dev_harness.harness.ghost_archetype")')
        assert named == ["dev_harness.harness.ghost_archetype"]
        ok, why = probe_module_only(named[0])
        assert not ok
        assert "import failed" in why

    def test_caller_scan_finds_nothing_in_text_that_names_nothing(self):
        assert caller_modules("no module names here at all") == []
