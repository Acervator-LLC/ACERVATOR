"""The stale-dist marker is a latch, and a latch needs a reset.

WHAT WAS MEASURED
=================
``tests/test_stale_dist_marker_redirect.py`` proved WHERE the marker
goes. It never asked what removes it. Driven 2026-08-14 in a contained
tree with ``ACERVATOR_CRASH_LOG_ROOT`` set, two sequential bare
``import main`` runs against the UNPATCHED file:

    step 1  live 3.25.7 / dist 3.25.6
            rc 0, stderr banner fires, marker written, 807 bytes,
            naming both versions
    step 2  dist rebuilt, live 3.25.7 / dist 3.25.7
            rc 0, banner correctly SILENT, and the marker STILL THERE,
            still 807 bytes, still sha256 4f18e5d4..., still naming
            3.25.7 vs 3.25.6

The stderr banner was EDGE-correct. The file was LEVEL-latched with no
clear: ``_check_stale_dist_binary`` fell out of the version comparison
when the versions agreed, before the marker directory was even
resolved, and nothing on that path removed anything.

WHY A STALE MARKER IS WORSE THAN NO MARKER
==========================================
The file exists to answer one question -- "which code am I actually
running". On 2026-08-14 the operator hit exactly that confusion: the
running executable reported v3.25.5 and the source reported v3.25.5 and
they were not the same code. A marker naming a version pair that is no
longer current re-creates the problem it was written to end.

The unit before this one made it worse by making it good: the marker
now honours ``ACERVATOR_CRASH_LOG_ROOT``, so a test run writes it into
a temp root and a real run writes it to home. Two locations, one
latched file, no clear.

WHAT THIS FILE PINS
===================
It pins the RESET, and ``TestTheMarkerIsTheBanner`` holds the marker's
text equal to what the same call writes to stderr.

The reset is armed by the SAME evidence as the warning, inverted: the
source states a version and a bundle in ``dist`` carries it. An
unreadable version and a missing ``dist`` both mean "cannot tell", never
"the mismatch is gone" -- clearing on either would delete a true
warning, and a rebuild in flight is exactly when ``dist`` is momentarily
unreadable.

The two sides are no longer two ``__version__`` literals. The live side
is what ``src/_version.py`` resolves, and the dist side is what the
build baked into the bundle. A version pair the tests state is a pair
the guard resolves; "cannot tell" is a side that resolves to nothing.

WHY IT IMPORTS ITS SIBLING
==========================
``_build_tree`` and ``_child_import`` already exist next door and are
already load-bearing there: the child's program text is an inline
literal and the temp paths travel in the environment, because a Windows
path in an argv element is a quoting hazard, and the containment has to
hold on the run where the assertion fails. Re-typing them here would
give this repository two copies to keep in step, which is the same
shape of defect the marker itself had.
"""

from __future__ import annotations

import ast
import importlib.util
import os
import stat
import sys
from pathlib import Path
from types import ModuleType

import pytest

import main


def _sibling() -> ModuleType:
    """Load the neighbouring redirect test module by PATH, not by name.

    ``import test_stale_dist_marker_redirect`` works under pytest, which
    puts ``tests/`` on sys.path, and nowhere else -- so every static
    analyser reports it unresolvable, which is a HIGH finding for an
    import that is genuinely fine at runtime. Loading by path says what
    is actually happening and resolves for both readers.

    The private module name keeps this copy out of pytest's way: pytest
    imports the same file under its own name during collection, and two
    entries under one key is how "import file mismatch" errors start.
    Re-executing it costs one AST parse of main.py.
    """
    path = Path(__file__).with_name("test_stale_dist_marker_redirect.py")
    key = "_acervator_stale_dist_redirect_helpers"
    cached = sys.modules.get(key)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(key, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load the sibling helpers from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[key] = module
    spec.loader.exec_module(module)
    return module


_SIB = _sibling()
_build_tree = _SIB._build_tree
_child_import = _SIB._child_import
_function = _SIB._function
_rebake_bundle = _SIB._rebake_bundle
MAIN_SRC = _SIB.MAIN_SRC

_OVERRIDE = "ACERVATOR_CRASH_LOG_ROOT"
_MARKER_FILE = "STALE_DIST_WARNING.txt"
_BAKED_FILE = _SIB._BAKED_FILE
_BUNDLE_PARTS = _SIB._BUNDLE_PARTS

# The banner byte for byte, compared through `read_text`, whose
# universal-newline decode reads the same on either platform.
BANNER_TEMPLATE = (
    "\n"
    "============================================================\n"
    "  ACERVATOR STALE BINARY WARNING\n"
    "============================================================\n"
    "  Live source version : {live}\n"
    "\n"
    "  No bundle in dist was built from this source. Launching\n"
    "  any of the bundles below runs OLD code with bugs that\n"
    "  have since been fixed:\n"
    "\n"
    "    dist/Acervator  (built from {dist})\n"
    "\n"
    "  ACTION: run `python main.py` from this source tree, or\n"
    "  rebuild with BUILD.py before launching a bundle.\n"
    "============================================================\n"
)

REPO_ROOT = Path(__file__).resolve().parent.parent


def _plant_main(tree: Path) -> None:
    """Copy the real main.py into ``tree``, bytes in, bytes out.

    ``read_bytes``/``write_bytes`` and not ``read_text``, so a text
    round-trip cannot rewrite the copy's line endings.
    """
    tree.mkdir(parents=True, exist_ok=True)
    (tree / "main.py").write_bytes((REPO_ROOT / "main.py").read_bytes())


class Latch:
    """Drive the REAL guard, repeatedly, against one contained tree.

    The sibling's ``drive_guard`` rebuilds the tree on every call, which
    is right for its one-shot questions and wrong for every question
    here: a latch is only visible across two runs that share a
    directory. So this keeps the tree, the home and the override fixed
    and lets a test change one thing between runs.
    """

    def __init__(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self._mp = monkeypatch
        self.tree = tmp_path / "tree"
        self.home = tmp_path / "home"
        # NOT created. A test that needs it absent needs it absent, and
        # the write path is what is entitled to create it.
        self.override = tmp_path / "override"
        self.tree.mkdir(parents=True, exist_ok=True)
        self.home.mkdir(parents=True, exist_ok=True)

    @property
    def marker(self) -> Path:
        return self.override / _MARKER_FILE

    @property
    def home_marker(self) -> Path:
        return self.home / ".acervator_logs" / _MARKER_FILE

    def versions(self, live: str | None, dist: str | None) -> None:
        """Lay out (or remove) the source version and the one bundle under dist."""
        bundle = self.tree.joinpath(*_BUNDLE_PARTS)
        for path in (
            self.tree / "src" / "__init__.py",
            self.tree / "src" / _BAKED_FILE,
            bundle / "__init__.py",
            bundle / _BAKED_FILE,
        ):
            if path.exists():
                path.unlink()
        _build_tree(self.tree, live, dist)

    def unparseable(self, *, live: bool = True) -> None:
        """Leave one side in place while it states no version at all.

        This is the "cannot tell" input that must NOT clear: the layout
        is intact and readable, and the side still resolves to nothing.
        The live side loses its baked file and has no repository to
        answer from; the bundle side keeps an init module with no
        ``__version__`` line, which is what a pre-bake build looks like
        when the literal has been retired.
        """
        if live:
            (self.tree / "src" / _BAKED_FILE).unlink(missing_ok=True)
            return
        bundle = self.tree.joinpath(*_BUNDLE_PARTS)
        bundle.mkdir(parents=True, exist_ok=True)
        (bundle / _BAKED_FILE).unlink(missing_ok=True)
        (bundle / "__init__.py").write_text(
            'RELEASE = "3.25.7"\n', encoding="utf-8", newline="\n"
        )

    def run(self, *, override: bool = True) -> None:
        """One call of the guard, contained before anything can write."""
        self._mp.setattr(main, "__file__", str(self.tree / "main.py"))
        self._mp.setattr(Path, "home", classmethod(lambda _cls: self.home))
        # CONTAINMENT. Everything past this line can touch the file
        # system, so nothing past this line runs unless home is fake.
        assert Path.home() == self.home, (
            "Path.home() was not redirected, so driving the real guard "
            "here could reach the operator's tree. Refusing."
        )
        self._mp.delenv("ACERVATOR_DEBUG_BOOT", raising=False)
        if override:
            self._mp.setenv(_OVERRIDE, str(self.override))
        else:
            self._mp.delenv(_OVERRIDE, raising=False)
        main._check_stale_dist_binary()


@pytest.fixture
def latch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Latch:
    return Latch(tmp_path, monkeypatch)


class TestTheFullCycle:
    """CONTROL (a) -- write, rebuild, clear, then no-op.

    If this goes red the latch is back: a marker naming a version pair
    that no longer exists outlives the rebuild that fixed it, and the
    operator reads it as current.
    """

    def test_three_sequential_imports_write_then_clear_then_do_nothing(
        self, tmp_path: Path
    ) -> None:
        """One tree, three bare imports, existence reported after each.

        Bare ``import main`` and not a direct call, because module
        import is what actually runs this guard in production -- at
        launch, and at pytest collection time.
        """
        tree = tmp_path / "tree"
        home = tmp_path / "home"
        override = tmp_path / "override"
        _plant_main(tree)
        home.mkdir()
        override.mkdir()
        seen = []

        _build_tree(tree, "3.25.7", "3.25.6")  # 1: stale dist
        first = _child_import(tree, home, override)
        seen.append((override / _MARKER_FILE).is_file())

        _rebake_bundle(tree, "3.25.7")
        second = _child_import(tree, home, override)  # 2: rebuilt
        seen.append((override / _MARKER_FILE).is_file())

        third = _child_import(tree, home, override)  # 3: still matched
        seen.append((override / _MARKER_FILE).is_file())

        for result in (first, second, third):
            assert result.returncode == 0, result.stderr
        assert seen == [True, False, False], (
            f"marker existence after each import was {seen}, expected "
            f"[True, False, False]: written on the mismatch, removed by "
            f"the rebuild, and not resurrected by a matched run"
        )

    def test_the_operators_default_path_clears_too(self, tmp_path: Path) -> None:
        """No override at all -- the launch the operator actually runs.

        A clear that only worked under the test override would leave the
        one copy that matters latched forever.
        """
        tree = tmp_path / "tree"
        home = tmp_path / "home"
        _plant_main(tree)
        home.mkdir()
        marker = home / ".acervator_logs" / _MARKER_FILE

        _build_tree(tree, "3.25.7", "3.25.6")
        assert _child_import(tree, home, None).returncode == 0
        assert marker.is_file(), "the mismatch wrote no marker to fake home"

        _rebake_bundle(tree, "3.25.7")
        result = _child_import(tree, home, None)

        assert result.returncode == 0, result.stderr
        assert not marker.exists(), (
            "the marker survived a rebuild on the default path; the "
            "operator is still being told about a mismatch that is gone"
        )


class TestATrueWarningSurvives:
    """CONTROL (b) -- a mismatch that is still true keeps its marker.

    If this goes red the clear is over-eager and the guard has become
    silent about a genuinely stale binary, which is strictly worse than
    the latch it replaced.
    """

    def test_a_second_mismatched_run_leaves_the_marker_in_place(
        self, latch: Latch
    ) -> None:
        latch.versions("3.25.7", "3.25.6")
        latch.run()
        assert latch.marker.is_file(), "the first run wrote no marker"

        latch.run()

        assert latch.marker.is_file(), (
            "a second run with the versions STILL mismatched removed the "
            "warning; the operator loses a true warning on every relaunch"
        )

    def test_the_content_is_refreshed_not_merely_survived(self, latch: Latch) -> None:
        """Present is not enough -- it has to be CURRENT.

        A marker left untouched across a version bump would still be
        naming the wrong pair, which is the same defect wearing the
        answer to the previous question.
        """
        latch.versions("3.25.7", "3.25.6")
        latch.run()
        first = latch.marker.read_text(encoding="utf-8")

        latch.versions("4.0.0", "3.25.6")
        latch.run()
        second = latch.marker.read_text(encoding="utf-8")

        assert "Live source version : 3.25.7" in first
        assert second != first, "the marker was not rewritten at all"
        assert "Live source version : 4.0.0" in second
        assert "3.25.7" not in second, (
            "the marker still names the previous live version, so it is "
            "stale content sitting in a present file"
        )


class TestAnUnknownVersionDoesNotClear:
    """CONTROL (c) -- "cannot tell" is not "the mismatch is gone".

    DECISION, DEFENDED: an unreadable or unparseable version leaves the
    marker exactly where it is. A bundle that states no version is
    dropped before the comparison, so it neither warns nor clears.
    Clearing here would delete a TRUE warning on a transient read
    failure, and a rebuild in flight is precisely when a version file is
    momentarily unreadable.

    If this goes red, a locked file during a build silently deletes the
    operator's stale-binary warning.
    """

    def test_an_unparseable_live_version_keeps_the_marker(self, latch: Latch) -> None:
        latch.versions("3.25.7", "3.25.6")
        latch.run()
        body = latch.marker.read_text(encoding="utf-8")

        latch.unparseable(live=True)
        latch.run()

        assert latch.marker.is_file(), (
            "a version file with no __version__ line cleared the marker; "
            "an unknown version was treated as agreement"
        )
        assert latch.marker.read_text(encoding="utf-8") == body

    def test_an_unreadable_version_file_keeps_the_marker(
        self, latch: Latch, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Drive the version readers' own OSError branches, not a fake."""
        latch.versions("3.25.7", "3.25.6")
        latch.run()
        body = latch.marker.read_text(encoding="utf-8")

        def unreadable(*_a: object, **_kw: object) -> None:
            raise OSError("simulated unreadable version file")

        monkeypatch.setattr(Path, "read_text", unreadable)
        latch.run()

        assert (
            latch.marker.is_file()
        ), "an OSError while reading a version cleared the marker"
        monkeypatch.undo()
        assert latch.marker.read_text(encoding="utf-8") == body

    def test_an_unparseable_bundle_version_keeps_the_marker(self, latch: Latch) -> None:
        """The same rule on the bundle side, where a literal can still live."""
        latch.versions("3.25.7", "3.25.6")
        latch.run()
        body = latch.marker.read_text(encoding="utf-8")

        latch.unparseable(live=False)
        latch.run()

        assert latch.marker.is_file(), (
            "a bundle that states no version cleared the marker; an "
            "unknown version was treated as agreement"
        )
        assert latch.marker.read_text(encoding="utf-8") == body

    def test_the_same_driver_DOES_clear_on_a_readable_match(self, latch: Latch) -> None:
        """POSITIVE CONTROL for the two tests above.

        Both of them assert that a file is still there. A driver that
        had stopped calling the guard at all would pass them both. This
        one fails unless the identical sequence, differing only in that
        the versions are readable and equal, removes the file.
        """
        latch.versions("3.25.7", "3.25.6")
        latch.run()
        assert latch.marker.is_file()

        # `versions` removes the old version files, so it runs before the veto.
        latch.versions("3.25.7", "3.25.7")
        latch.run()

        assert not latch.marker.exists(), (
            "the driver never cleared anything, so the survival tests "
            "beside it prove nothing"
        )

    def test_a_vanished_dist_keeps_the_marker(self, latch: Latch) -> None:
        """DECISION, DEFENDED: a missing ``dist`` does not clear.

        The guard returns before the marker directory is resolved when no
        bundle states a version. A dist that has been deleted, renamed or
        moved aside is not a dist that was rebuilt; it is a dist we can no
        longer measure. The same return also covers a missing
        ``src/__init__.py``, i.e. a tree whose layout we do not recognise,
        which is the last place to start removing files.
        """
        latch.versions("3.25.7", "3.25.6")
        latch.run()
        assert latch.marker.is_file()

        latch.versions("3.25.7", None)
        latch.run()

        assert latch.marker.is_file(), (
            "removing dist cleared the marker; absence of evidence was "
            "read as evidence of a rebuild"
        )


class TestNoDirectoryIsCreatedByTheClearPath:
    """CONTROL (d) -- the clear probes, it does not build.

    ``mkdir(parents=True, exist_ok=True)`` on the clear path would put
    an empty ``.acervator_logs`` into every temp root the suite makes
    and onto every developer machine that has none. If this goes red,
    the fix for a leaked file leaks a directory instead.
    """

    def test_a_missing_override_root_is_still_missing_afterwards(
        self, latch: Latch
    ) -> None:
        # `versions` removes the old version files, so it runs before the veto.
        latch.versions("3.25.7", "3.25.7")
        assert not latch.override.exists(), "the fixture pre-created it"

        latch.run()

        assert not latch.override.exists(), (
            f"the clear path created {latch.override} in order to look "
            f"for a file that was never in it"
        )

    def test_the_home_log_root_is_not_created_either(self, latch: Latch) -> None:
        """The same question on the branch that reaches the operator."""
        # `versions` removes the old version files, so it runs before the veto.
        latch.versions("3.25.7", "3.25.7")

        latch.run(override=False)

        assert not (
            latch.home / ".acervator_logs"
        ).exists(), "a matched pair created the operator's log directory"

    def test_the_probe_can_see_a_directory_appear(self, latch: Latch) -> None:
        """POSITIVE CONTROL. The two tests above assert an absence.

        An absence is a claim about the instrument until the instrument
        is shown reporting a presence. Same fixture, same override, same
        assertion target -- only the version pair differs.
        """
        latch.versions("3.25.7", "3.25.6")
        assert not latch.override.exists()

        latch.run()

        assert latch.override.is_dir(), (
            "even the WRITE path created nothing, so the absence "
            "measured above is a blind instrument, not a result"
        )


class TestTheGuardStillNeverRaises:
    """CONTROL (e) -- an unlink can fail, and the guard must not care.

    The outer ``except Exception`` exists because this runs at module
    level before the GUI: anything that escapes kills boot. A delete is
    the first thing in this function that another process can veto --
    on Windows a file held open, or one marked read-only.

    And it must not fail SILENTLY. ``_early_debug`` is quiet unless
    ACERVATOR_DEBUG_BOOT=1, so it alone would hide a marker that
    outlived its mismatch forever. The clear path therefore reports a
    failed removal on stderr, unconditionally, and only on failure.
    """

    def test_a_failing_unlink_neither_raises_nor_goes_quiet(
        self,
        latch: Latch,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        latch.versions("3.25.7", "3.25.6")
        latch.run()
        assert latch.marker.is_file()
        capsys.readouterr()

        def vetoed(_self: Path, **_kw: object) -> None:
            raise PermissionError("simulated: another process holds it")

        # `versions` removes the old version files, so it runs before the veto.
        latch.versions("3.25.7", "3.25.7")
        monkeypatch.setattr(Path, "unlink", vetoed)

        latch.run()  # must not raise

        monkeypatch.undo()
        err = capsys.readouterr().err
        assert latch.marker.is_file(), "the test's own veto did not bite"
        assert "could not be removed" in err, (
            f"a failed clear produced no visible report; stderr was "
            f"{err!r}. The marker now names versions that are not "
            f"current and nothing says so."
        )
        assert _MARKER_FILE in err, "the report does not name the file"

    def test_a_read_only_marker_does_not_kill_the_guard(
        self, latch: Latch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The real Windows refusal, not a simulated one."""
        latch.versions("3.25.7", "3.25.6")
        latch.run()
        marker = latch.marker
        assert marker.is_file()

        probe = latch.override / "probe.txt"
        probe.write_text("x", encoding="utf-8", newline="\n")
        probe.chmod(stat.S_IREAD)
        try:
            probe.unlink()
        except PermissionError:
            pass
        else:
            pytest.skip(
                "this platform deletes read-only files, so a "
                "read-only marker cannot exercise the failure"
            )

        marker.chmod(stat.S_IREAD)
        capsys.readouterr()
        try:
            latch.versions("3.25.7", "3.25.7")
            latch.run()  # must not raise
            err = capsys.readouterr().err
            assert marker.is_file(), "the read-only file was removed anyway"
            assert (
                "could not be removed" in err
            ), f"a read-only marker failed to clear in silence: {err!r}"
        finally:
            marker.chmod(stat.S_IWRITE)
            probe.chmod(stat.S_IWRITE)

    def test_a_directory_in_the_markers_place_is_left_alone(self, latch: Latch) -> None:
        """The probe is ``is_file``, so a directory is skipped by shape.

        Stated rather than assumed: nothing here reaches ``unlink``, and
        that is the point. A clear that called ``unlink`` unconditionally
        would raise PermissionError on Windows against a directory, and
        a clear that reached for ``rmtree`` would be deleting a tree it
        was never asked about.
        """
        # `versions` removes the old version files, so it runs before the veto.
        latch.versions("3.25.7", "3.25.7")
        latch.override.mkdir(parents=True, exist_ok=True)
        imposter = latch.override / _MARKER_FILE
        imposter.mkdir()
        (imposter / "not_ours.txt").write_text(
            "someone else's file", encoding="utf-8", newline="\n"
        )

        latch.run()  # must not raise

        assert imposter.is_dir(), "the guard removed a directory"
        assert (imposter / "not_ours.txt").is_file(), (
            "the guard deleted the contents of a directory that merely "
            "shares the marker's name"
        )

    def test_a_child_import_survives_a_read_only_marker(self, tmp_path: Path) -> None:
        """rc 0 and no traceback, measured across a real process.

        The in-process tests above run the guard long after boot. Only a
        child import can say that a failed clear does not kill the
        process before the GUI starts.
        """
        tree = tmp_path / "tree"
        home = tmp_path / "home"
        override = tmp_path / "override"
        _plant_main(tree)
        home.mkdir()
        override.mkdir()
        marker = override / _MARKER_FILE

        _build_tree(tree, "3.25.7", "3.25.6")
        assert _child_import(tree, home, override).returncode == 0
        assert marker.is_file()
        marker.chmod(stat.S_IREAD)
        try:
            probe_removable = True
            try:
                (override / "probe").mkdir()
                (override / "probe").rmdir()
            except OSError:  # pragma: no cover
                probe_removable = False
            assert probe_removable, "the override root is not writable"

            _rebake_bundle(tree, "3.25.7")
            result = _child_import(tree, home, override)

            assert result.returncode == 0, result.stderr
            assert "Traceback" not in result.stderr, result.stderr
            if marker.is_file():
                assert "could not be removed" in result.stderr, (
                    f"the child could not clear the marker and said "
                    f"nothing: {result.stderr!r}"
                )
        finally:
            # The child clears the marker on success, so it may be gone.
            if marker.exists():
                marker.chmod(stat.S_IWRITE)


class TestTheMarkerIsTheBanner:
    """CONTROL (f) -- the marker holds ``BANNER_TEMPLATE``.

    The same ``Latch.run`` writes that string to stderr, and the two sinks
    must not drift apart.
    """

    def test_the_marker_is_the_pinned_banner_character_for_character(
        self, latch: Latch
    ) -> None:
        latch.versions("3.25.7", "3.25.6")
        latch.run()

        assert latch.marker.read_text(encoding="utf-8") == BANNER_TEMPLATE.format(
            live="3.25.7", dist="3.25.6"
        )

    def test_the_marker_still_equals_what_went_to_stderr(
        self, latch: Latch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Two sinks, one string. They must not drift apart."""
        capsys.readouterr()
        latch.versions("3.25.7", "3.25.6")
        latch.run()

        assert latch.marker.read_text(encoding="utf-8") == capsys.readouterr().err

    def test_a_matched_pair_still_prints_nothing(
        self, latch: Latch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The clear must be silent. A guard that announced every
        successful removal would print on every launch and be muted."""
        latch.versions("3.25.7", "3.25.6")
        latch.run()
        capsys.readouterr()

        # `versions` removes the old version files, so it runs before the veto.
        latch.versions("3.25.7", "3.25.7")
        latch.run()

        captured = capsys.readouterr()
        assert not latch.marker.exists()
        assert captured.err == "", f"the clear path printed {captured.err!r}"
        assert captured.out == ""


class TestTheClearIsStructurallyWhereItClaimsToBe:
    """The properties behaviour alone cannot pin.

    A green behavioural suite is compatible with a clear that builds a
    directory on a machine whose temp root happens to exist already, or
    with one armed by a condition that a future edit widens. These read
    the guard's own AST.
    """

    @staticmethod
    def _guard() -> ast.FunctionDef:
        return _function("_check_stale_dist_binary")

    @staticmethod
    def _attr_calls(node: ast.AST, name: str) -> list[ast.Call]:
        return [
            n
            for n in ast.walk(node)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == name
        ]

    def _branch(self) -> ast.If:
        """The mismatch ``if`` whose ``orelse`` holds the clear."""
        found = [
            n
            for n in ast.walk(self._guard())
            if isinstance(n, ast.If)
            and self._attr_calls(n, "mkdir")
            and any(self._attr_calls(s, "unlink") for s in n.orelse)
        ]
        assert len(found) == 1, (
            f"expected exactly one branch with a mkdir on one side and an "
            f"unlink on the other, found {len(found)}"
        )
        return found[0]

    def test_the_clear_path_contains_no_mkdir(self) -> None:
        branch = self._branch()
        offenders = [s for s in branch.orelse if self._attr_calls(s, "mkdir")]
        assert not offenders, (
            "the clear path calls mkdir; it would create a directory in "
            "order to look for a file that is not in it"
        )

    def test_the_guard_reads_the_override_before_it_deletes(self) -> None:
        """One spelling of the directory, or the clear misses a copy.

        The marker can land in a temp root or in home. A clear that
        resolved the path independently could remove one copy and leave
        the other, which is the same half-applied redirect that let this
        marker outlive the fix to its sibling faulthandler log.
        """
        guard = self._guard()
        # Nested helpers only. `ast.walk` yields the guard itself first,
        # and the guard trivially "contains" every name in its own body.
        resolvers = [
            n
            for n in ast.walk(guard)
            if isinstance(n, ast.FunctionDef)
            and n is not guard
            and any(
                isinstance(c, ast.Name) and c.id == "CRASH_LOG_ROOT_ENV"
                for c in ast.walk(n)
            )
        ]
        assert len(resolvers) == 1, (
            f"{len(resolvers)} places inside the guard resolve the marker "
            f"directory; there must be exactly one"
        )
        assert ".acervator_logs" in ast.get_source_segment(
            MAIN_SRC, resolvers[0]
        ), "the single resolver no longer names the operator's log root"


class TestTheSuiteIsStillContained:
    """This file drives a real delete. It must never reach home."""

    def test_the_override_is_set_for_this_process(self) -> None:
        assert os.environ.get(_OVERRIDE), (
            f"{_OVERRIDE} is unset, so an import of main in this process "
            f"reads and writes the operator's own log tree"
        )

    def test_the_only_use_of_real_home_is_the_containment_assert(self) -> None:
        """Read this file's own source. One use of ``Path.home()`` is
        legitimate -- the assertion in ``Latch.run`` that refuses to
        proceed unless home has been redirected. Any OTHER use would be
        a real path pointed at the operator's tree by a file that drives
        a real delete, so the rule is "inside an assert, or not at all"
        rather than a blanket ban that the fixture itself would break.
        """
        body = ast.parse(Path(__file__).read_text(encoding="utf-8"))
        everywhere = [
            n
            for n in ast.walk(body)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == "home"
        ]
        in_asserts = [
            n
            for stmt in ast.walk(body)
            if isinstance(stmt, ast.Assert)
            for n in ast.walk(stmt)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == "home"
        ]
        assert everywhere, (
            "the containment assertion that reads Path.home() is gone, so "
            "nothing checks that home was redirected before a delete"
        )
        loose = [n.lineno for n in everywhere if n not in in_asserts]
        assert not loose, (
            f"Path.home() is called outside an assert at line(s) {loose}; "
            f"every path this file touches must be under tmp_path"
        )


def test_the_platform_is_the_one_that_was_measured() -> None:
    """State the ground rather than assume it.

    The read-only control depends on Windows refusing to delete a
    read-only file. It proves that precondition before relying on it, so
    this is a note for whoever reads a skip, not a gate.
    """
    assert sys.platform in {"win32", "linux", "darwin"}
