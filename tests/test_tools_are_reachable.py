"""Every script under `tools/` runs, and the ones that were deleted stay gone.

Why this file exists
--------------------
Issue #83 audited `tools/`. Four kinds of rot were found in one directory:

* a shim that raised `ModuleNotFoundError` before its first statement
  (`orphan_widget_scan.py`, repaired under issue #68);
* three one-shot migration scripts whose migrations had already run, kept
  on disk as if they were still tools;
* a migration script that skipped a missing source file with `continue`,
  so it could copy nothing and still print a count and exit 0;
* three more tools that could each scan an empty tree, report zeroes and
  exit 0, which reads exactly like a clean result.

Every one of those passed every check in the repository, because nothing
in the suite ever ran a tool.

Why this is a separate file from `test_harness_is_reachable.py`
---------------------------------------------------------------
That file measures ONE contract: the five archetypes under `dev_harness/`
stay reachable from the callers that name them by string. Its subject is
the harness move of issue #84. This file measures a different contract:
the INVENTORY of `tools/`. The two share the probe pattern and the
two-sided-control discipline, and they share nothing else. Folding the
inventory into the harness file would give that file two subjects and
would make a failure there ambiguous about which contract broke.

`tests/test_no_dead_sadp_references.py` already asserts that every tool
imports. It discovers the list by glob, so a tool that DISAPPEARS leaves
no trace: the loop simply has one fewer item and still passes. This file
holds the inventory as a written contract instead, so both directions
fail loudly -- a new tool must be declared, and a deleted tool must be
removed from the list.

Importing is not running
------------------------
A tool that imports can still be unable to reach its own `main()`. So the
tools that carry an argument parser are spawned as programs, and the one
that does not is checked at the API level with the reason written down.

What each tool must refuse
--------------------------
The last class of tests is the point of the file. Each repaired tool is
driven into the state where it used to do nothing and report success, and
must now refuse. Each of those is paired with the state where it must
still succeed, because a tool that refuses everything guards nothing.

Two-sided control
-----------------
`TestTheInstrumentCanFail` points the probes at a module that does not
exist and at a module with no `main()`, and requires FAILURE. Without it
a probe that always returned "reachable" would satisfy every assertion
above.
"""

# ruff: noqa: S603
# S607 IS FIXED BY CONSTRUCTION, NOT SUPPRESSED, following the reasoning at
# the top of dev_harness/harness/coding_archetype.py and the pattern already
# measured clean in tests/test_harness_is_reachable.py. The spawn below uses
# an absolute executable path through `sys.executable`, so no planted
# executable earlier on PATH can run under the developer's token.
#
# S603 remains and is not avoidable: an all-literal argv draws none, and any
# argv carrying a variable draws one. A resolved interpreter path is a
# variable by definition. This directive is the residue, narrowed to the one
# rule.
from __future__ import annotations

import ast
import importlib
import subprocess
import sys
import types
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
TOOLS = REPO / "tools"

# The inventory. Written out, never discovered, because a discovered list
# shrinks in silence when a file disappears. Each entry is
# (module suffix, reachable as a program).
#
# `gate.py` is False on purpose and the reason is load-bearing: it carries
# no argument parser, so `python -m tools.gate --help` would not print a
# usage line, it would RUN THE RELEASE GATE. A test may not do that. Its
# entry point is checked at the API level instead, one test below.
#
# `island` left this list under issue #67. It was a branch-and-merge
# simulator, retired by operator decision on 2026-08-19 when the work moved
# to git. `test_every_tool_on_disk_is_declared` below already fails if the
# file returns undeclared; `tests/test_island_machinery_stays_retired.py`
# holds the wider contract, because the tool had a ledger, a test file and
# seven skill documents around it.
#
# `deps` entered this list under issue #94. It reads the dependency set
# out of pyproject.toml so that no script has to hold one. It carries an
# argument parser and three subcommands, so it is True.
INVENTORY: tuple[tuple[str, bool], ...] = (
    ("build_release_zip", True),
    ("deps", True),
    ("emitter_registry_check", True),
    ("gate", False),
    ("migrate_harness", True),
    ("orphan_widget_scan", True),
    ("queue_state", True),
    # Issue #85 moved this in from the repository root, where it was
    # called `test_scrumming_v3.py`. It wore pytest's discovery prefix,
    # sat outside `testpaths`, and defined no test function, so nothing
    # collected it and nothing ran it. It reached its scenarios from a
    # bare `__main__` block; the move gave it the `main()` and the parser
    # this inventory requires, so it is True.
    ("scrumming_v3_sim", True),
)

# Deleted under issue #83. Each was a one-shot whose migration had already
# run, proved by the artefacts it left on disk. They are named here so the
# deletion is a contract: restoring one silently would fail this file.
DELETED_ONE_SHOTS: tuple[str, ...] = (
    "migrate_stone_tablets",
    "purge_orphan_reservations",
    "quarantine_sim_contamination",
)

# Shared LIBRARIES under `tools/`. A library is IMPORTED and never run, so
# the `main` contract above is the wrong question to ask of one.
#
# `spec_common` entered this directory under issue #87, which lifted the
# text both `.spec` files shared into one module: `read_acervator_version`,
# `datas_candidates`, `build_graceful_datas`, `hiddenimports_for`,
# `COMMON_HIDDENIMPORTS`, `KEYRING_BACKENDS` and `EXCLUDES`. PyInstaller
# EXECS a spec file, and the spec then says
# `from tools.spec_common import ...`. Nothing starts spec_common as a
# program, and nothing should: a `main()` on it would be an entry point
# with no caller.
#
# Issue #85 measured it undeclared and RED at 0bb82bb and refused it while
# issue #87 still owned the file. #87 is merged, so the row is taken here.
# It is NOT a tool row with a softer rule. A library owes three things,
# and `TestEveryLibraryIsALibrary` asks for all three:
#
#   1. it imports;
#   2. it exposes every name its importers ask for, READ FROM THE
#      IMPORTERS rather than restated in this file;
#   3. it exposes NO `main`.
#
# Rule 3 is what stops this category becoming a hiding place. A tool whose
# entry point broke cannot be moved here to silence the failure, because
# the ABSENCE of `main` is what makes a library a library.
LIBRARIES: tuple[tuple[str, str], ...] = (
    ("spec_common",
     "shared PyInstaller spec content, imported by Acervator_win.spec "
     "and Acervator_mac.spec"),
)

# The importers rule 2 is read from.
SPEC_FILES: tuple[str, ...] = ("Acervator_win.spec", "Acervator_mac.spec")


def probe_import(stem: str) -> tuple[bool, str]:
    """Report whether `tools.<stem>` imports and exposes a callable main.

    Returns (reachable, reason); `reason` is '' when reachable. A control
    below feeds this a module that does not exist and requires False.
    """
    try:
        mod = importlib.import_module(f"tools.{stem}")
    except ImportError as exc:
        return False, f"import failed: {exc}"
    if not callable(getattr(mod, "main", None)):
        return False, f"tools.{stem} has no callable main"
    return True, ""


def library_stems() -> set[str]:
    return {stem for stem, _ in LIBRARIES}


def declared_stems() -> set[str]:
    """Every module this file declares, tool or library.

    Widening a comparison is how a guard quietly stops guarding, so
    `test_the_directory_check_still_catches_an_undeclared_script` below
    drives the widened set with a file that neither list names.
    """
    return {stem for stem, _ in INVENTORY} | library_stems()


def stems_on_disk(directory: Path = TOOLS) -> set[str]:
    """Every module actually present, ignoring private helpers.

    `directory` is a parameter and not a constant read, following
    `product_python_files` in tests/test_one_dependency_source.py, so a
    control can drive this walk over a planted tree. A comparison that
    can only ever read the real directory cannot be SHOWN reporting a
    straggler.
    """
    return {p.stem for p in directory.glob("*.py")
            if not p.stem.startswith("_")}


def names_imported_from(module: str, source: str) -> set[str]:
    """Every name a source file asks `module` for.

    Parsed, not text-searched. Both spec files name `tools.spec_common`
    in their prose as well as in their import statement, and prose is not
    an import.
    """
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom) and node.module == module:
            found.update(alias.name for alias in node.names)
    return found


class TestTheInventoryMatchesTheDirectory:
    """Both directions. Either one alone passes on a half-empty tree."""

    def test_every_declared_tool_is_on_disk(self):
        missing = sorted(declared_stems() - stems_on_disk())
        assert not missing, f"declared but absent from tools/: {missing}"

    def test_every_tool_on_disk_is_declared(self):
        extra = sorted(stems_on_disk() - declared_stems())
        assert not extra, (
            f"tools/ holds undeclared scripts: {extra}. Add each to "
            "INVENTORY with its own reachability, or delete it."
        )


class TestEveryToolImports:
    @pytest.mark.parametrize(("stem", "_runs"), INVENTORY)
    def test_tool_imports_and_exposes_main(self, stem, _runs):
        ok, why = probe_import(stem)
        assert ok, f"tools/{stem}.py is UNREACHABLE: {why}"


class TestEveryToolRunsAsAProgram:
    @pytest.mark.parametrize(
        "stem", [s for s, runs in INVENTORY if runs])
    def test_tool_answers_dash_m_help(self, stem):
        """`python -m tools.<stem> --help` must reach the tool's parser.

        A module that does not load exits with a traceback naming
        ModuleNotFoundError instead, which is what this separates.
        """
        run = subprocess.run(
            [sys.executable, "-m", f"tools.{stem}", "--help"],
            cwd=str(REPO), capture_output=True, text=True,
            timeout=180, check=False,
        )
        blob = run.stdout + run.stderr
        assert "ModuleNotFoundError" not in blob, (
            f"tools/{stem}.py did not load as a program:\n{blob[:800]}")
        assert run.returncode == 0, (
            f"tools/{stem}.py --help exited {run.returncode}:\n{blob[:800]}")
        assert "usage:" in blob.lower(), (
            f"tools/{stem}.py reached no parser:\n{blob[:800]}")

    def test_the_gate_wrapper_exposes_its_entry_point(self):
        """`tools/gate.py` is excluded from the spawn above by design.

        It has no parser, so spawning it with any argument would run the
        release gate. Its reachability is the same question asked of the
        object instead of the process.
        """
        mod = importlib.import_module("tools.gate")
        assert callable(mod.main)
        assert callable(mod.head_sha)
        assert callable(mod.tree_is_dirty)


class TestEveryLibraryIsALibrary:
    """A library imports, serves its importers, and is not a program."""

    @pytest.mark.parametrize(("stem", "_why"), LIBRARIES)
    def test_library_imports(self, stem, _why):
        """Rule 1. An unimportable library stops both builds."""
        importlib.import_module(f"tools.{stem}")

    @pytest.mark.parametrize(("stem", "_why"), LIBRARIES)
    def test_library_exposes_no_main(self, stem, _why):
        """Rule 3. The rule that keeps this category honest."""
        mod = importlib.import_module(f"tools.{stem}")
        assert not callable(getattr(mod, "main", None)), (
            f"tools/{stem}.py is declared a library and carries a "
            f"callable main. Either it is a tool and belongs in "
            f"INVENTORY, or that main has no caller and must go. This "
            f"category is not a place to park a tool whose entry point "
            f"broke."
        )

    @pytest.mark.parametrize(("stem", "_why"), LIBRARIES)
    def test_library_carries_a_reason(self, stem, _why):
        assert _why.strip(), f"tools/{stem}.py is declared with no reason"

    def test_a_module_is_a_tool_or_a_library_and_never_both(self):
        both = sorted({stem for stem, _ in INVENTORY} & library_stems())
        assert not both, f"declared as both tool and library: {both}"


class TestTheSharedSpecLibraryServesItsImporters:
    """Rule 2, read from the importers and not from a list here.

    A hand-written list of names would drift the moment a spec asked for
    a new one. The spec files ARE the list.
    """

    @pytest.mark.parametrize("spec", SPEC_FILES)
    def test_every_name_a_spec_asks_for_is_defined(self, spec):
        source = (REPO / spec).read_text(encoding="utf-8")
        wanted = names_imported_from("tools.spec_common", source)
        assert wanted, (
            f"{spec} imports nothing from tools.spec_common; this check "
            f"has no input and can report nothing")
        mod = importlib.import_module("tools.spec_common")
        missing = sorted(name for name in wanted if not hasattr(mod, name))
        assert not missing, (
            f"{spec} imports {missing} from tools.spec_common and the "
            f"module defines none of them. PyInstaller would stop with "
            f"an ImportError on the operator's machine."
        )

    def test_both_specs_read_the_same_library(self):
        """The module exists to hold what the two specs SHARE."""
        asked = [
            names_imported_from(
                "tools.spec_common",
                (REPO / spec).read_text(encoding="utf-8"))
            for spec in SPEC_FILES
        ]
        assert asked[0] & asked[1], (
            "the two specs now share no name from tools.spec_common; the "
            "reason that module exists has gone")


class TestTheDeletedOneShotsStayDeleted:
    @pytest.mark.parametrize("stem", DELETED_ONE_SHOTS)
    def test_the_file_is_gone(self, stem):
        assert not (TOOLS / f"{stem}.py").exists(), (
            f"{stem}.py is back. It is a fired one-shot, not a tool.")

    @pytest.mark.parametrize("stem", DELETED_ONE_SHOTS)
    def test_the_module_does_not_import(self, stem):
        ok, why = probe_import(stem)
        assert not ok, f"tools.{stem} still imports"
        assert "import failed" in why


class TestARefusalWhereSilenceUsedToBe:
    """Each tool, driven into the state where it used to report success.

    Every case is paired: the refusal, and the run that must still pass.
    A tool that refuses everything guards nothing.
    """

    def test_queue_state_refuses_a_tree_with_no_source(self, tmp_path,
                                                       monkeypatch):
        mod = importlib.import_module("tools.queue_state")
        (tmp_path / "src").mkdir()
        monkeypatch.setattr(mod, "ROOT", tmp_path)
        assert mod.report(set()) == 2

    def test_queue_state_still_reports_on_a_tree_with_source(self, tmp_path,
                                                             monkeypatch):
        mod = importlib.import_module("tools.queue_state")
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
        monkeypatch.setattr(mod, "ROOT", tmp_path)
        assert mod.report({6}) == 0

    def test_orphan_scan_refuses_a_root_holding_no_module(self, tmp_path):
        mod = importlib.import_module("tools.orphan_widget_scan")
        empty = tmp_path / "empty"
        empty.mkdir()
        assert mod.main(["--root", str(empty), "--strict"]) == 2

    def test_orphan_scan_still_finds_an_orphan(self, tmp_path):
        mod = importlib.import_module("tools.orphan_widget_scan")
        root = tmp_path / "gui"
        root.mkdir()
        (root / "w.py").write_text(
            "class T:\n"
            "    def build(self):\n"
            "        self.btn = QPushButton('go')\n",
            encoding="utf-8")
        report = mod.build_report(root)
        assert report["files_scanned"] == 1
        assert len(report["orphan_candidates"]) == 1
        assert mod.main(["--root", str(root), "--strict"]) == 1

    def test_release_zip_reads_no_session_from_a_bare_directory(self,
                                                               tmp_path):
        mod = importlib.import_module("tools.build_release_zip")
        assert mod.read_session_number(tmp_path) is None

    def test_release_zip_takes_the_session_off_the_newest_version(self,
                                                                 tmp_path):
        """The number follows the highest VERSION, never the highest session.

        Measured on 2026-08-16: session numbers on this disk do not rise
        with version, and `max(session)` named two packages `session79`
        off a build that was v3.25.x.
        """
        mod = importlib.import_module("tools.build_release_zip")
        for name in ("acervator_session79_CLOSE_hop5_v3_23_20.zip",
                     "acervator_session27_CLOSE_hop5_v3_25_7.zip"):
            (tmp_path / name).write_bytes(b"")
        measured = mod.read_session_number(tmp_path)
        assert measured is not None
        session, evidence = measured
        assert session == 27
        assert "v3_25_7" in evidence

    def test_release_zip_names_a_routing_rule_that_matched_nothing(self):
        mod = importlib.import_module("tools.build_release_zip")
        absent = min(mod.ADDITIONAL_FILES_EXACT)
        stale = mod.unmatched_rules([Path("tools/gate.py")], [])
        assert f"file {absent}" in stale

    def test_release_zip_names_no_rule_when_every_rule_matched(self):
        mod = importlib.import_module("tools.build_release_zip")
        matched = [Path(name) for name in mod.ADDITIONAL_FILES_EXACT]
        matched += [Path(d) / "x" for d in mod.ADDITIONAL_DIRS]
        assert mod.unmatched_rules([], matched) == []

    def test_migrate_harness_refuses_a_source_missing_a_loose_tool(
            self, tmp_path, monkeypatch):
        mod = importlib.import_module("tools.migrate_harness")
        source, target = tmp_path / "src", tmp_path / "dst"
        for path in (source, target):
            path.mkdir()
        monkeypatch.setattr(mod, "HERE", source)
        monkeypatch.setattr(sys, "argv",
                            ["migrate_harness", "--to", str(target)])
        assert mod.main() == 3

    def test_migrate_harness_proceeds_when_every_loose_tool_is_there(
            self, tmp_path, monkeypatch):
        mod = importlib.import_module("tools.migrate_harness")
        source, target = tmp_path / "src", tmp_path / "dst"
        for path in (source, target):
            path.mkdir()
        for rel in mod.LOOSE_TOOLS:
            planted = source / rel
            planted.parent.mkdir(parents=True, exist_ok=True)
            planted.write_text("x = 1\n", encoding="utf-8")
        monkeypatch.setattr(mod, "HERE", source)
        monkeypatch.setattr(sys, "argv",
                            ["migrate_harness", "--to", str(target)])
        assert mod.main() == 0

    def test_migrate_harness_will_not_call_an_absent_tools_dir_clean(
            self, tmp_path):
        """An empty result must mean "measured, none", never "not measured"."""
        mod = importlib.import_module("tools.migrate_harness")
        with pytest.raises(FileNotFoundError):
            mod.report_absolute_paths(tmp_path)


class TestTheInstrumentCanFail:
    """Positive controls. Without these the file proves nothing."""

    def test_probe_rejects_a_module_that_does_not_exist(self):
        ok, why = probe_import("no_such_tool_at_all")
        assert not ok
        assert "import failed" in why

    def test_probe_rejects_a_module_that_imports_but_has_no_main(
            self, monkeypatch):
        """The second branch. Import success alone must not read as green.

        A module object with no `main` is planted in the import cache, so
        `import_module` returns it and the entry-point check is the only
        thing left to decide the answer.
        """
        faux = types.ModuleType("tools.faux_no_main")
        monkeypatch.setitem(sys.modules, "tools.faux_no_main", faux)
        ok, why = probe_import("faux_no_main")
        assert not ok
        assert "no callable main" in why

    def test_the_directory_check_still_catches_an_undeclared_script(
            self, tmp_path):
        """The widened allowlist must still report a real straggler.

        LIBRARIES made `declared_stems` bigger. A bigger allowlist is
        exactly how a guard stops guarding, so the comparison is driven
        over a planted tree holding every declared name, one file that is
        declared nowhere, and one private helper that must stay ignored.
        """
        planted = tmp_path / "tools"
        planted.mkdir()
        for stem in sorted(declared_stems()):
            (planted / f"{stem}.py").write_text("x = 1", encoding="utf-8")
        (planted / "zz_undeclared_straggler.py").write_text(
            "x = 1", encoding="utf-8")
        (planted / "_private_helper.py").write_text("x = 1", encoding="utf-8")

        extra = sorted(stems_on_disk(planted) - declared_stems())
        assert extra == ["zz_undeclared_straggler"], extra

    def test_the_library_rule_rejects_a_library_that_grew_a_main(
            self, monkeypatch):
        """Rule 3, driven with the case it exists for.

        A module object carrying a `main` is planted in the import cache,
        so the rule reads a real module and the `main` is the only thing
        left to decide the answer.
        """
        faux = types.ModuleType("tools.faux_library")
        faux.main = lambda: 0
        monkeypatch.setitem(sys.modules, "tools.faux_library", faux)
        mod = importlib.import_module("tools.faux_library")
        assert callable(getattr(mod, "main", None)), (
            "the planted module lost its main; the rule cannot be shown "
            "rejecting anything")

    def test_the_spec_surface_check_rejects_a_name_that_is_absent(self):
        """Rule 2, driven with a name tools.spec_common does not define."""
        mod = importlib.import_module("tools.spec_common")
        wanted = {"EXCLUDES", "no_such_name_at_all"}
        missing = sorted(name for name in wanted if not hasattr(mod, name))
        assert missing == ["no_such_name_at_all"]

    def test_the_inventory_check_rejects_a_declaration_with_no_file(self):
        """The comparison, driven with a name that is not on disk."""
        bogus = declared_stems() | {"no_such_tool_at_all"}
        assert sorted(bogus - stems_on_disk()) == ["no_such_tool_at_all"]

    def test_the_directory_holds_something(self):
        """Both inventory tests pass on an empty tools/. This does not."""
        assert len(stems_on_disk()) >= len(INVENTORY)
