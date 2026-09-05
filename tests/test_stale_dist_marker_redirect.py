"""The stale-dist marker must be redirectable, and must still be seen.

THE SIBLING THAT WAS MISSED
===========================
``tests/test_faulthandler_log_redirect.py`` closed one module-level
writer in ``main.py``: ``_setup_faulthandler`` was taught to read
``ACERVATOR_CRASH_LOG_ROOT``. Fifteen lines away, in the same file,
``_check_stale_dist_binary`` wrote ``STALE_DIST_WARNING.txt`` to a
hard-coded ``Path.home() / ".acervator_logs"`` and read no override at
all. Same class, same file, same import, one of the two fixed.

WHAT ARMS IT
============
The guard writes only when ``dist`` holds at least one bundle and none
of them carries the version the source resolves to.

The operator's standard cascade bumps the version and then runs the
gate. From that bump until ``dist`` is rebuilt -- normally many runs --
every gate run imports ``main`` at pytest COLLECTION time and drops
this file into the live log tree. One fixed name, so it overwrites
rather than accumulates, and ``conftest``'s live-tree guard degrades to
a printed warning whenever the application is running, which for this
operator is nearly always. Nothing fails; nothing even complains.

WHAT THE TWO SIDES ARE NOW
==========================
There is no ``__version__`` literal left to read. The live side is what
``src/_version.py`` resolves from the git tag; the dist side is what
the build baked into the bundle, or the literal a bundle built before
the bake still carries. The trees these tests build state their live
version through the baked file, because a temp tree has no repository;
``TestTheGuardComparesResolvedAgainstBaked`` drives the git path in a
throwaway repository so the resolver is not taken on trust.

THE CONSTRAINT THAT OUTRANKS THE REDIRECT
=========================================
This marker exists because a stale ``dist`` means the operator is
running code they believe they replaced. A redirect that hid the warning
from them would be worse than the leak it removes. So the default path
is tested as hard as the override path, and
``TestTheDefaultStillReachesTheOperator`` asserts it against the REAL
home directory.

HOW THAT IS DONE WITHOUT CREATING THE FILE
==========================================
Proving the default lands in the operator's tree by letting it land
there would commit the leak in order to measure it. So that one test
INTERCEPTS at ``Path.mkdir``, which the guard calls BEFORE it opens
anything: the interception records the directory that was aimed at and
then raises, so the ``open`` below it is never reached. The replacement
is proven to both record and raise on a decoy path before the real
function is driven.

Every other test replaces ``Path.home`` with a temp directory first and
refuses to run unless the replacement took, so a failure stays inside
``tmp_path``.
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

import main
from tools.migration_verifier import default_runner

REPO_ROOT = Path(__file__).resolve().parent.parent
MAIN_SRC = (REPO_ROOT / "main.py").read_text(encoding="utf-8")
MAIN_TREE = ast.parse(MAIN_SRC)

_OVERRIDE = "ACERVATOR_CRASH_LOG_ROOT"
_MARKER_FILE = "STALE_DIST_WARNING.txt"
_BAKED_FILE = "_baked_version.txt"
_BUNDLE_PARTS = ("dist", "Acervator", "_internal", "src")

# Given a temp tree, a fake home, an override root and a version pair,
# drive the real guard and return the directory it was pointed at.
Driver = Callable[..., Path]


def _function(name: str) -> ast.FunctionDef:
    """Return the named top-level function's AST node from main.py."""
    return next(
        n
        for n in ast.walk(MAIN_TREE)
        if isinstance(n, ast.FunctionDef) and n.name == name
    )


def _assign_line(name: str) -> int:
    """Return the line of the module-level assignment to `name`."""
    return min(
        n.lineno
        for n in MAIN_TREE.body
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == name for t in n.targets)
    )


def _call_line(func_name: str) -> int:
    """Return the line of the module-level bare call to `func_name`."""
    return min(
        n.lineno
        for n in MAIN_TREE.body
        if isinstance(n, ast.Expr)
        and isinstance(n.value, ast.Call)
        and isinstance(n.value.func, ast.Name)
        and n.value.func.id == func_name
    )


def _plant_package(root: Path) -> None:
    """Copy the real version machinery into a temp tree's ``src``.

    A child process resolves the live version out of the tree it imports,
    so the tree has to hold the same two files the operator runs.
    """
    pkg = root / "src"
    pkg.mkdir(parents=True, exist_ok=True)
    for name in ("__init__.py", "_version.py"):
        (pkg / name).write_bytes((REPO_ROOT / "src" / name).read_bytes())


def _build_tree(root: Path, live_ver: str | None, dist_ver: str | None) -> None:
    """Lay out ``live_ver`` beside the package and ``dist_ver`` in the bundle.

    ``None`` on either side states no version at all, which is the no-dist
    case ``_BUNDLE_PARTS`` then never resolves.
    """
    if live_ver is not None:
        _plant_package(root)
        (root / "src" / _BAKED_FILE).write_text(
            f"{live_ver}\n", encoding="utf-8", newline="\n"
        )
    if dist_ver is not None:
        dist = root.joinpath(*_BUNDLE_PARTS)
        dist.mkdir(parents=True, exist_ok=True)
        (dist / _BAKED_FILE).write_text(f"{dist_ver}\n", encoding="utf-8", newline="\n")


def _rebake_bundle(root: Path, version: str) -> None:
    """Restate the version a built bundle carries, as a rebuild would."""
    root.joinpath(*_BUNDLE_PARTS, _BAKED_FILE).write_text(
        f"{version}\n", encoding="utf-8", newline="\n"
    )


def _child_import(
    tree: Path, home: Path, override: Path | None
) -> subprocess.CompletedProcess[str]:
    """Import ``main`` in a child with ``Path.home`` bound to `home`.

    The home patch is installed BEFORE the import, because the import is
    what writes. Patching it afterwards would prove nothing and would
    leak into the real tree on the no-override run.

    The child's program text is an inline literal and the temp paths
    travel in the environment rather than in argv. That is not a style
    choice: a Windows path in an argv element is the quoting hazard the
    subprocess-input rules exist to name, and the containment here has
    to hold on the run where the assertion fails.
    """
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["ACERVATOR_TEST_FAKE_HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    env["HOME"] = str(home)
    if override is None:
        env.pop(_OVERRIDE, None)
    else:
        env[_OVERRIDE] = str(override)
    return subprocess.run(
        [
            sys.executable,
            "-c",
            "import os, pathlib\n"
            "fake = pathlib.Path(os.environ['ACERVATOR_TEST_FAKE_HOME'])\n"
            "pathlib.Path.home = classmethod(lambda cls: fake)\n"
            "assert pathlib.Path.home() == fake, 'home patch did not take'\n"
            "import main\n"
            "print('IMPORTED', main.CRASH_LOG_ROOT_ENV)\n",
        ],
        cwd=str(tree),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def _tag_repo(root: Path, tag: str) -> None:
    """Commit everything under ``root`` and tag it, so git can describe it.

    Spawning is delegated to the migration verifier's absolute-path
    runner, so no test spawns a process of its own.
    """
    for args in (
        ("init", "-q", "-b", "current"),
        ("config", "user.email", "fixture@example.invalid"),
        ("config", "user.name", "Fixture"),
        ("config", "commit.gpgsign", "false"),
        ("add", "-A"),
        ("commit", "-qm", "fixture"),
        ("tag", tag),
    ):
        done = default_runner(["git", "-C", str(root), *args], None)
        assert done.code == 0, f"git {args[0]} -> {done.code}: {done.err.strip()}"


def _run_guard(
    monkeypatch: pytest.MonkeyPatch,
    tree: Path,
    fake_home: Path,
    override: Path | None,
) -> Path:
    """Drive the real guard against a prepared tree, and say where it aimed.

    The guard derives every path it reads from ``main.__file__``, so
    pointing that at a temp directory is what makes a contained,
    two-sided experiment possible at all: the live ``src`` and ``dist``
    are never read and never need to disagree.
    """
    fake_home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(main, "__file__", str(tree / "main.py"))
    monkeypatch.setattr(Path, "home", classmethod(lambda _cls: fake_home))
    # CONTAINMENT. Everything past this line can create a file, so
    # nothing past this line runs unless home is already fake.
    assert Path.home() == fake_home, (
        "Path.home() was not redirected, so driving the real guard "
        "here could write into the operator's tree. Refusing."
    )
    if override is None:
        monkeypatch.delenv(_OVERRIDE, raising=False)
    else:
        override.mkdir(parents=True, exist_ok=True)
        monkeypatch.setenv(_OVERRIDE, str(override))

    main._check_stale_dist_binary()
    if override is not None:
        return override
    return fake_home / ".acervator_logs"


@pytest.fixture
def drive_guard(monkeypatch: pytest.MonkeyPatch) -> Driver:
    """Build a temp tree from a version pair, then drive the real guard."""

    def _drive(
        tree: Path,
        fake_home: Path,
        override: Path | None,
        live_ver: str | None = "9.9.9",
        dist_ver: str | None = "1.1.1",
    ) -> Path:
        tree.mkdir(parents=True, exist_ok=True)
        _build_tree(tree, live_ver, dist_ver)
        return _run_guard(monkeypatch, tree, fake_home, override)

    return _drive


class TestTheDefaultStillReachesTheOperator:
    """CONTROL (a) -- the default must still land in the real log root.

    If this goes red, the operator stops being told that they are
    running a stale binary: the exact failure the marker was written to
    prevent, now caused by the fix for its leak.
    """

    def test_the_write_is_aimed_at_the_real_home_log_root(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Drive the real guard against the real home, creating nothing.

        ``Path.mkdir`` is replaced with a recorder that raises, and the
        replacement is proven to do both on a decoy path BEFORE the
        guard runs. The guard's own best-effort ``except`` absorbs the
        raise, so no file is opened and none is created.
        """
        aimed: list[tuple[Path, int, bool, bool]] = []
        refusal = "intercepted: no directory may be created by this test"

        def fake_mkdir(
            self: Path,
            mode: int = 0o777,
            *,
            parents: bool = False,
            exist_ok: bool = False,
        ) -> None:
            aimed.append((Path(self), mode, parents, exist_ok))
            raise PermissionError(refusal)

        # Build the temp tree BEFORE the patch, since building it needs
        # a working mkdir.
        tree = tmp_path / "tree"
        _build_tree(tree, "9.9.9", "1.1.1")
        monkeypatch.setattr(main, "__file__", str(tree / "main.py"))
        monkeypatch.delenv(_OVERRIDE, raising=False)
        monkeypatch.delenv("ACERVATOR_DEBUG_BOOT", raising=False)
        monkeypatch.setattr(Path, "mkdir", fake_mkdir)

        # Positive control: prove the `mkdir` patch took before trusting a clean tree.
        decoy = tmp_path / "decoy"
        with pytest.raises(PermissionError):
            decoy.mkdir(parents=True, exist_ok=True)
        assert (
            not decoy.exists()
        ), "Path.mkdir was not intercepted; the guard could create a directory"
        assert aimed == [
            (decoy, 0o777, True, True)
        ], "the interception did not record the decoy it just blocked"
        aimed.clear()

        main._check_stale_dist_binary()

        expected = Path.home() / ".acervator_logs"
        assert [row[0] for row in aimed] == [expected], (
            f"with no override the marker aimed at {aimed}, not at the "
            f"operator's own log root {expected}"
        )

    def test_the_default_branch_is_in_the_function_not_a_comment(self) -> None:
        """Read the default over the guard's AST, so prose cannot pass."""
        segment = (
            ast.get_source_segment(MAIN_SRC, _function("_check_stale_dist_binary"))
            or ""
        )
        literals = [
            n.value
            for n in ast.walk(ast.parse(segment))
            if isinstance(n, ast.Constant) and n.value == ".acervator_logs"
        ]
        assert literals, "the guard no longer names the operator's log root"


class TestUnderTestItLandsInTheOverride:
    """CONTROL (b) -- with the override set, nothing reaches the home tree.

    If this goes red, a gate run after a version bump is depositing a
    file in the operator's live log directory again.
    """

    def test_the_marker_lands_in_the_override_directory(
        self, tmp_path: Path, drive_guard: Driver
    ) -> None:
        """The override directory holds the marker after a real call."""
        override = tmp_path / "override"
        landed = drive_guard(tmp_path / "tree", tmp_path / "home", override)

        marker = landed / _MARKER_FILE
        assert marker.is_file(), f"no marker under the override {override}"
        assert marker.parent == override.resolve()

    def test_the_home_tree_is_left_alone_when_overridden(
        self, tmp_path: Path, drive_guard: Driver
    ) -> None:
        """The home log directory must not even be CREATED.

        That absence is what the operator's tree is entitled to look
        like from this code's point of view.
        """
        home = tmp_path / "home"
        drive_guard(tmp_path / "tree", home, tmp_path / "override")

        assert not (
            home / ".acervator_logs"
        ).exists(), "the guard created the home log directory despite the override"

    def test_the_suite_is_redirected_right_now(self) -> None:
        """Assert the state of this very process, not the source."""
        assert os.environ.get(_OVERRIDE), (
            f"{_OVERRIDE} is unset while the suite runs, so the next "
            f"import of main writes into the operator's tree"
        )


class TestTheTriggerStillTriggers:
    """CONTROL (c) -- the redirect changed where, never whether.

    If this goes red, the fix altered WHAT the guard detects or WHEN it
    warns, which was never in scope.
    """

    def test_mismatched_versions_write_the_marker_with_both_numbers(
        self, tmp_path: Path, drive_guard: Driver
    ) -> None:
        """A stale dist still produces the full banner, both versions."""
        landed = drive_guard(
            tmp_path / "tree",
            tmp_path / "home",
            tmp_path / "override",
            live_ver="3.25.7",
            dist_ver="3.25.6",
        )
        body = (landed / _MARKER_FILE).read_text(encoding="utf-8")

        for expected in (
            "ACERVATOR STALE BINARY WARNING",
            "Live source version : 3.25.7",
            "dist/Acervator  (built from 3.25.6)",
            "rebuild with BUILD.py",
        ):
            assert expected in body, f"the marker never says {expected!r}"

    def test_matching_versions_write_nothing(
        self, tmp_path: Path, drive_guard: Driver
    ) -> None:
        """THE NEGATIVE SIDE.

        A guard that fired on a matched pair would cry wolf on every
        launch and get switched off.
        """
        landed = drive_guard(
            tmp_path / "tree",
            tmp_path / "home",
            tmp_path / "override",
            live_ver="3.25.6",
            dist_ver="3.25.6",
        )

        assert not (
            landed / _MARKER_FILE
        ).exists(), "the guard warned about a dist that matches its source"

    def test_the_marker_matches_what_went_to_stderr(
        self, tmp_path: Path, drive_guard: Driver, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The file is a copy of the stderr banner, not a summary.

        The banner is what the operator sees when a terminal is
        attached; the file is what they get when the GUI has swallowed
        stderr. They must not drift apart.
        """
        landed = drive_guard(
            tmp_path / "tree",
            tmp_path / "home",
            tmp_path / "override",
            live_ver="4.0.0",
            dist_ver="3.0.0",
        )

        assert (landed / _MARKER_FILE).read_text(
            encoding="utf-8"
        ) == capsys.readouterr().err


class TestNoDistNoWrite:
    """CONTROL (d) -- a missing file on either side is silent.

    Most developers have no ``dist`` at all. If this goes red, every one
    of them gets a marker file they cannot act on.
    """

    @pytest.mark.parametrize(
        ("live_ver", "dist_ver", "case"),
        [
            ("9.9.9", None, "no dist"),
            (None, "1.1.1", "no source"),
            (None, None, "neither"),
        ],
    )
    def test_a_missing_file_is_silent(
        self,
        tmp_path: Path,
        drive_guard: Driver,
        live_ver: str | None,
        dist_ver: str | None,
        case: str,
    ) -> None:
        """No marker appears when either version file is absent."""
        landed = drive_guard(
            tmp_path / "tree",
            tmp_path / "home",
            tmp_path / "override",
            live_ver=live_ver,
            dist_ver=dist_ver,
        )

        assert not (landed / _MARKER_FILE).exists(), f"the guard warned with {case}"

    def test_no_dist_is_silent_against_the_real_home_too(
        self, tmp_path: Path, drive_guard: Driver
    ) -> None:
        """The default branch has to be silent as well.

        The no-dist case is the common one and it is the one that would
        reach the operator, so it is checked on the default branch and
        not only on the override branch.
        """
        home = tmp_path / "home"
        landed = drive_guard(
            tmp_path / "tree", home, None, live_ver="9.9.9", dist_ver=None
        )

        assert not (landed / _MARKER_FILE).exists()
        assert not (home / ".acervator_logs").exists()


class TestTheGuardComparesResolvedAgainstBaked:
    """CONTROL (f) -- the guard reads the mechanism that replaced the literal.

    The literal is gone from both trees. A guard still line-parsing
    ``__version__`` reads the same text on each side, always matches, and
    never warns again: the operator loses the only thing that tells them
    the .exe predates their source.
    """

    def test_a_bundle_built_before_the_bake_is_still_measured(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A bundle carrying a literal and no baked file must still warn.

        Every bundle already on disk was built before the bake existed.
        Reading only the baked file would go silent against exactly the
        stale binary this guard was written for.
        """
        tree = tmp_path / "tree"
        _build_tree(tree, "3.25.7", None)
        bundle = tree.joinpath(*_BUNDLE_PARTS)
        bundle.mkdir(parents=True, exist_ok=True)
        (bundle / "__init__.py").write_text(
            '__version__ = "3.15.43"\n', encoding="utf-8", newline="\n"
        )

        landed = _run_guard(monkeypatch, tree, tmp_path / "home", tmp_path / "override")

        body = (landed / _MARKER_FILE).read_text(encoding="utf-8")
        assert "Live source version : 3.25.7" in body
        assert "dist/Acervator  (built from 3.15.43)" in body

    def test_a_baked_file_outranks_a_literal_left_beside_it(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """POSITIVE CONTROL on the fallback: the baked file wins.

        The whole bundled ``src`` directory ships, so a bundle can carry
        both files. Reading the literal first would report a version the
        build did not resolve.
        """
        tree = tmp_path / "tree"
        _build_tree(tree, "3.25.7", "3.25.6")
        bundle = tree.joinpath(*_BUNDLE_PARTS)
        (bundle / "__init__.py").write_text(
            '__version__ = "3.15.43"\n', encoding="utf-8", newline="\n"
        )

        landed = _run_guard(monkeypatch, tree, tmp_path / "home", tmp_path / "override")

        body = (landed / _MARKER_FILE).read_text(encoding="utf-8")
        assert "dist/Acervator  (built from 3.25.6)" in body
        assert "3.15.43" not in body

    def test_the_live_side_is_the_version_git_describes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A tagged checkout must be measured by its tag.

        Driven against a real throwaway repository, because every other
        tree here answers from a baked file and would look identical if
        the git path had been dropped.
        """
        tree = tmp_path / "tree"
        _plant_package(tree)
        _tag_repo(tree, "v9.9.9")
        bundle = tree.joinpath(*_BUNDLE_PARTS)
        bundle.mkdir(parents=True, exist_ok=True)
        (bundle / _BAKED_FILE).write_text("1.1.1\n", encoding="utf-8", newline="\n")

        landed = _run_guard(monkeypatch, tree, tmp_path / "home", tmp_path / "override")

        body = (landed / _MARKER_FILE).read_text(encoding="utf-8")
        assert "Live source version : 9.9.9" in body, body
        assert "dist/Acervator  (built from 1.1.1)" in body, body

    def test_a_bundle_baked_at_the_tag_is_silent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """THE NEGATIVE SIDE of the git-derived comparison.

        Same repository, same tag, only the baked value differs. A guard
        that warned here would fire on every launch after a fresh build.
        """
        tree = tmp_path / "tree"
        _plant_package(tree)
        _tag_repo(tree, "v9.9.9")
        bundle = tree.joinpath(*_BUNDLE_PARTS)
        bundle.mkdir(parents=True, exist_ok=True)
        (bundle / _BAKED_FILE).write_text("9.9.9\n", encoding="utf-8", newline="\n")

        landed = _run_guard(monkeypatch, tree, tmp_path / "home", tmp_path / "override")

        assert not (landed / _MARKER_FILE).exists(), (
            "the guard warned about a bundle baked at the tag the source "
            "tree is standing on"
        )

    def test_a_tree_that_resolves_nothing_is_silent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No repository and no baked file is "cannot tell", not "stale"."""
        tree = tmp_path / "tree"
        _plant_package(tree)
        bundle = tree.joinpath(*_BUNDLE_PARTS)
        bundle.mkdir(parents=True, exist_ok=True)
        (bundle / _BAKED_FILE).write_text("1.1.1\n", encoding="utf-8", newline="\n")

        landed = _run_guard(monkeypatch, tree, tmp_path / "home", tmp_path / "override")

        assert not (
            landed / _MARKER_FILE
        ).exists(), "an unresolvable source tree was reported as a stale binary"


class TestTheImportOrderHolds:
    """CONTROL (e) -- the constant is bound before the guard reads it.

    ``CRASH_LOG_ROOT_ENV`` is read INSIDE a function whose call site is
    module level. Declared below that call site, the lookup raises
    NameError -- and the guard's own best-effort ``except`` swallows it,
    so the redirect would read as applied while writing nothing at all.
    A clean exit code cannot see that, which is why the subprocess tests
    check for the FILE rather than for the return code alone.
    """

    def test_the_constant_is_declared_above_the_guards_call_site(self) -> None:
        """Ordering is load-bearing here, not a matter of style."""
        declared = _assign_line("CRASH_LOG_ROOT_ENV")
        called = _call_line("_check_stale_dist_binary")
        assert declared < called, (
            f"CRASH_LOG_ROOT_ENV is declared at line {declared} but "
            f"_check_stale_dist_binary() is called at line {called}, so the "
            f"override lookup raises NameError into a swallowing except"
        )

    def test_it_is_declared_above_every_reader(self) -> None:
        """Pin the constant above ALL readers, not above one.

        Any future module-level reader inherits the same ordering
        constraint, so the assertion is written over every reference
        rather than over the two that exist today.
        """
        declared = _assign_line("CRASH_LOG_ROOT_ENV")
        readers = [
            n.lineno
            for n in ast.walk(MAIN_TREE)
            if isinstance(n, ast.Name)
            and n.id == "CRASH_LOG_ROOT_ENV"
            and n.lineno != declared
        ]
        assert readers, "nothing reads CRASH_LOG_ROOT_ENV; the redirect is dead"
        assert declared < min(readers), (
            f"CRASH_LOG_ROOT_ENV declared at {declared}, first read at "
            f"{min(readers)}"
        )

    def test_a_bare_import_arms_the_marker_in_the_override(
        self, tmp_path: Path
    ) -> None:
        """The runtime half of the ordering claim, in a child process.

        A bare ``import main`` with the trigger armed must produce the
        marker in the override directory. If the constant were unbound
        at the call site, the NameError would be swallowed and this
        directory would simply be empty.
        """
        tree = tmp_path / "tree"
        _build_tree(tree, "3.25.7", "3.25.6")
        (tree / "main.py").write_bytes((REPO_ROOT / "main.py").read_bytes())
        override = tmp_path / "override"
        home = tmp_path / "home"
        override.mkdir(parents=True, exist_ok=True)
        home.mkdir(parents=True, exist_ok=True)

        result = _child_import(tree, home, override)

        assert result.returncode == 0, result.stderr
        assert "NameError" not in result.stderr, result.stderr
        assert (override / _MARKER_FILE).is_file(), (
            f"a bare import wrote no marker into {override}; the override "
            f"lookup is failing silently. stderr:\n{result.stderr}"
        )
        assert not (
            home / ".acervator_logs" / _MARKER_FILE
        ).exists(), "the marker leaked into the home tree despite the override"

    def test_a_bare_import_without_the_override_does_not_raise(
        self, tmp_path: Path
    ) -> None:
        """The operator's own launch path, driven rather than argued.

        No override, trigger armed, home contained. The marker must land
        in the home log root and the import must not raise.
        """
        tree = tmp_path / "tree"
        _build_tree(tree, "3.25.7", "3.25.6")
        (tree / "main.py").write_bytes((REPO_ROOT / "main.py").read_bytes())
        home = tmp_path / "home"
        home.mkdir(parents=True, exist_ok=True)

        result = _child_import(tree, home, None)

        assert result.returncode == 0, result.stderr
        assert "NameError" not in result.stderr, result.stderr
        assert (home / ".acervator_logs" / _MARKER_FILE).is_file(), (
            "the operator's default path produced no marker. stderr:\n"
            f"{result.stderr}"
        )
