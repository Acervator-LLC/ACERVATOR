"""The faulthandler log must be redirectable away from the live tree.

HOW THIS WAS FOUND
==================
Not by reading code. A read-only census of the operator's runtime tree
on 2026-08-14 counted **2,154** ``faulthandler_*.log`` files in
``~/.acervator_logs``, 2,127 of them header-only at 91-92 bytes, 30 of
them created that day. The operator's application had been up for 15
hours, so the application did not write them.

THE WRITER, AND IT IS AN IMPORT
===============================
``main.py`` arms faulthandler as a module-level side effect::

    _FH_FILE, _FH_PATH = _setup_faulthandler()

so merely importing ``main`` opens a log. Test modules import it at the
top level -- ``test_async_pump_timer_precision.py`` and
``test_main_boot_guard.py`` -- and pytest executes those imports during
COLLECTION. One file per gate run, every gate run.

WHY THE EXISTING GUARD DID NOT CATCH IT
=======================================
``conftest.py``'s ``_assert_no_live_tree_writes`` DOES see the file, and
its own comment names ``faulthandler_*`` by pattern. But it is a
detector, not a cleanup: it deletes nothing. And it downgrades created
paths to a printed warning whenever a live Acervator process is running,
which on the operator's machine it almost always is. So the guard saw
the leak, said so quietly, failed nothing, and read as solved.

THE ASYMMETRY THAT LET IT SURVIVE
=================================
``crash_*.log`` and ``faulthandler_*.log`` are written side by side, to
one directory, by one import, and are correlated by timestamp. Measured
with ``ACERVATOR_CRASH_LOG_ROOT`` set exactly as conftest sets it::

    crash_20260814_135109.log        -> the override directory
    faulthandler_20260814_135109.log -> ~/.acervator_logs

``_get_crash_log_path`` read the override. ``_setup_faulthandler`` did
not. Same run, same directory, same purpose, one of the two redirected.

WHY THESE TESTS RE-ARM RATHER THAN INSPECT SOURCE
=================================================
``main`` arms faulthandler once, at import, and by the time this module
runs that has already happened. Asserting on the TEXT of
``_setup_faulthandler`` would pin the source and not the behaviour --
the failure mode that let a named pattern leak for 2,154 files. So the
runtime tests below CALL the real function again and assert where its
file actually landed.

HOW A FAILURE IS KEPT CONTAINED
===============================
The experiment must be safe when it FAILS. Running it and looking in the
operator's directory would prove the leak by committing it. So every
runtime test replaces ``Path.home`` with a temp directory FIRST and
refuses to call the function at all unless the replacement took. The
override says where the file SHOULD go; the temporary home bounds where
it CAN go.
"""

from __future__ import annotations

import ast
import faulthandler
import os
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import IO

import pytest

import main

REPO_ROOT = Path(__file__).resolve().parent.parent
MAIN_SRC = (REPO_ROOT / "main.py").read_text(encoding="utf-8")
MAIN_TREE = ast.parse(MAIN_SRC)

_OVERRIDE = "ACERVATOR_CRASH_LOG_ROOT"

# Given a fake home and an optional override root, arm faulthandler for
# real and return the path its log landed on.
Driver = Callable[[Path, "Path | None"], Path]


def _module_constant(src: str, name: str) -> object:
    """Read a module-level string constant without importing the module.

    Importing ``main`` to read it would arm faulthandler a second time,
    which is the behaviour under test rather than a way to observe it.
    """
    for node in ast.parse(src).body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return ast.literal_eval(node.value)
    return None


def _function(name: str) -> ast.FunctionDef:
    """Return the named top-level function's AST node from main.py."""
    return next(
        n
        for n in ast.walk(MAIN_TREE)
        if isinstance(n, ast.FunctionDef) and n.name == name
    )


@pytest.fixture
def drive_setup(monkeypatch: pytest.MonkeyPatch) -> Iterator[Driver]:
    """Arm the REAL faulthandler setup against a temp home, then undo it.

    Teardown matters more than setup here. ``_setup_faulthandler`` calls
    ``faulthandler.enable(file=...)``, which re-points the whole
    process's native crash dump at the handle it just opened. Closing
    that handle without first restoring the original would leave the
    interpreter dumping into a closed file for the rest of the suite --
    a test that silently disarms the crash reporting it is verifying.
    """
    opened: list[IO[str]] = []

    def _drive(fake_home: Path, override: Path | None) -> Path:
        fake_home.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(Path, "home", classmethod(lambda _cls: fake_home))
        # CONTAINMENT. Everything after this line can create a file, so
        # nothing after this line runs unless home is already fake.
        assert Path.home() == fake_home, (
            "Path.home() was not redirected, so driving the real setup "
            "here could write into the operator's tree. Refusing."
        )
        if override is None:
            monkeypatch.delenv(_OVERRIDE, raising=False)
        else:
            monkeypatch.setenv(_OVERRIDE, str(override))

        handle, path = main._setup_faulthandler()
        if handle is not None:
            opened.append(handle)
        assert path is not None, "_setup_faulthandler reported no path"
        return Path(path)

    yield _drive

    original = main._FH_FILE
    try:
        if original is not None and not original.closed:
            faulthandler.enable(file=original, all_threads=True)
        else:
            faulthandler.enable(file=sys.stderr, all_threads=True)
    finally:
        for handle in opened:
            if not handle.closed:
                handle.close()


class TestTheOverrideIsRead:
    """Source level: cheap, and it fails on a revert on its own."""

    def test_main_declares_the_constant(self) -> None:
        """POSITIVE CONTROL: every assertion below reads this name."""
        assert _module_constant(MAIN_SRC, "CRASH_LOG_ROOT_ENV") == _OVERRIDE

    def test_setup_faulthandler_consults_it(self) -> None:
        """Pin the override read to the function body, not the file.

        Asserted over the AST of the function itself, so a mention in a
        comment or a docstring cannot satisfy it.
        """
        node = _function("_setup_faulthandler")
        names = {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
        assert (
            "CRASH_LOG_ROOT_ENV" in names
        ), "_setup_faulthandler ignores the override; the leak is back"

    def test_it_still_defaults_to_the_runtime_tree(self) -> None:
        """NEGATIVE CONTROL: the operator's default must not move.

        With no override set, a native crash on the operator's machine
        must still dump where they look for it. A fix that silenced the
        leak by relocating the default would pass every other test in
        this file and quietly break the crash diagnostics.
        """
        segment = ast.get_source_segment(MAIN_SRC, _function("_setup_faulthandler"))
        assert ".acervator_logs" in (segment or "")

    def test_the_constant_is_defined_before_faulthandler_is_armed(self) -> None:
        """Ordering is load-bearing here, not a matter of style.

        ``_setup_faulthandler`` is CALLED at module level. If the
        constant were declared after that call, the lookup would raise
        NameError while main.py is still executing, outside the
        function's own try block, and kill the boot.
        """
        declared = min(
            n.lineno
            for n in MAIN_TREE.body
            if isinstance(n, ast.Assign)
            and any(
                isinstance(t, ast.Name) and t.id == "CRASH_LOG_ROOT_ENV"
                for t in n.targets
            )
        )
        armed = min(
            n.lineno
            for n in MAIN_TREE.body
            if isinstance(n, ast.Assign)
            and isinstance(n.value, ast.Call)
            and isinstance(n.value.func, ast.Name)
            and n.value.func.id == "_setup_faulthandler"
        )
        assert declared < armed, (
            f"CRASH_LOG_ROOT_ENV is declared at line {declared} but "
            f"_setup_faulthandler() is called at line {armed}"
        )


class TestTheRealPathHonoursIt:
    """Runtime: these call the function the application calls."""

    def test_the_log_lands_in_the_override_directory(
        self, tmp_path: Path, drive_setup: Driver
    ) -> None:
        """THE WHOLE POINT.

        If this goes red, a gate run is depositing files in the
        operator's log directory again.
        """
        override = tmp_path / "override"
        landed = drive_setup(tmp_path / "home", override).resolve()

        assert (
            landed.parent == override.resolve()
        ), f"the faulthandler log landed at {landed}, not under {override}"
        assert landed.is_file(), "a path was returned but no file exists"
        assert landed.name.startswith("faulthandler_")
        assert "faulthandler started" in landed.read_text(encoding="utf-8")

    def test_the_home_tree_is_left_alone_when_overridden(
        self, tmp_path: Path, drive_setup: Driver
    ) -> None:
        """Containment, stated as an assertion.

        With the override set, the home log directory must not even be
        CREATED. That absence is what the operator's tree is entitled to
        look like from this code's point of view.
        """
        home = tmp_path / "home"
        drive_setup(home, tmp_path / "override")

        stray = sorted((home / ".acervator_logs").glob("faulthandler_*"))
        assert stray == [], f"faulthandler logs leaked into home: {stray}"

    def test_it_still_arms_and_still_writes_home_with_no_override(
        self, tmp_path: Path, drive_setup: Driver
    ) -> None:
        """THE APPLICATION'S OWN BEHAVIOUR, driven rather than argued.

        faulthandler exists because the operator relies on a native
        crash dump. Removing the leak must not remove that, so this
        drives the default branch with the override deleted and asserts
        both that the handler armed and where its file went.
        """
        home = tmp_path / "home"
        landed = drive_setup(home, None).resolve()

        assert (
            faulthandler.is_enabled()
        ), "faulthandler did not arm; native crashes now dump nothing"
        assert (
            landed.parent == (home / ".acervator_logs").resolve()
        ), f"the default log root moved to {landed.parent}"
        assert landed.is_file()
        assert "faulthandler started" in landed.read_text(encoding="utf-8")


class TestThisSuiteIsRedirectedRightNow:
    """Not source inspection: the state of the process running this."""

    def test_the_variable_is_set_during_this_run(self) -> None:
        """The redirect must be armed for the whole session, not a test."""
        assert os.environ.get(_OVERRIDE), (
            f"{_OVERRIDE} is unset while the suite is running, so the "
            f"next import of main writes into the operator's tree"
        )

    def test_the_redirect_points_outside_the_live_tree(self) -> None:
        """A redirect that resolves back into the live tree is no redirect."""
        target = Path(os.environ[_OVERRIDE]).resolve()
        for forbidden in (Path.home() / ".acervator", Path.home() / ".acervator_logs"):
            assert (
                target != forbidden
            ), f"the redirect resolves onto the live tree: {target}"
            assert (
                forbidden not in target.parents
            ), f"the redirect resolves inside the live tree: {target}"
