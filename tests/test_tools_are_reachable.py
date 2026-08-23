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
INVENTORY: tuple[tuple[str, bool], ...] = (
    ("build_release_zip", True),
    ("emitter_registry_check", True),
    ("gate", False),
    ("migrate_harness", True),
    ("orphan_widget_scan", True),
    ("queue_state", True),
)

# Deleted under issue #83. Each was a one-shot whose migration had already
# run, proved by the artefacts it left on disk. They are named here so the
# deletion is a contract: restoring one silently would fail this file.
DELETED_ONE_SHOTS: tuple[str, ...] = (
    "migrate_stone_tablets",
    "purge_orphan_reservations",
    "quarantine_sim_contamination",
)


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


def declared_stems() -> set[str]:
    return {stem for stem, _ in INVENTORY}


def stems_on_disk() -> set[str]:
    """Every tool module actually present, ignoring private helpers."""
    return {p.stem for p in TOOLS.glob("*.py")
            if not p.stem.startswith("_")}


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

    def test_the_inventory_check_rejects_a_declaration_with_no_file(self):
        """The comparison, driven with a name that is not on disk."""
        bogus = declared_stems() | {"no_such_tool_at_all"}
        assert sorted(bogus - stems_on_disk()) == ["no_such_tool_at_all"]

    def test_the_directory_holds_something(self):
        """Both inventory tests pass on an empty tools/. This does not."""
        assert len(stems_on_disk()) >= len(INVENTORY)
