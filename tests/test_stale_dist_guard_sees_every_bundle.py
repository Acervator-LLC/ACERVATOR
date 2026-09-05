"""``_check_stale_dist_binary`` measures every bundle under ``dist``.

A build writes ``dist/Acervator-<version>-<variant>`` and older bundles stay
beside it. The guard warns only when no bundle carries the source version, and
its message names each bundle it found.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import main

REPO_ROOT = Path(__file__).resolve().parent.parent

_OVERRIDE = "ACERVATOR_CRASH_LOG_ROOT"
_MARKER_FILE = "STALE_DIST_WARNING.txt"
_BAKED_FILE = "_baked_version.txt"
_SOURCE_FILES = ("__init__.py", "_version.py")


class Guard:
    """Drive the real guard against one contained tree, repeatedly.

    ``source`` states the version the tree resolves to, ``bundle`` adds a built
    bundle under ``dist``, and ``run`` calls the guard with ``home`` and the
    marker root redirected into ``tmp_path``.
    """

    def __init__(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self._mp = monkeypatch
        self.tree = tmp_path / "tree"
        self.home = tmp_path / "home"
        self.override = tmp_path / "override"
        self.tree.mkdir(parents=True, exist_ok=True)
        self.home.mkdir(parents=True, exist_ok=True)

    @property
    def marker(self) -> Path:
        return self.override / _MARKER_FILE

    def source(self, version: str) -> None:
        """Write ``_SOURCE_FILES`` and ``_BAKED_FILE`` so the tree resolves ``version``."""
        pkg = self.tree / "src"
        pkg.mkdir(parents=True, exist_ok=True)
        for name in _SOURCE_FILES:
            (pkg / name).write_bytes((REPO_ROOT / "src" / name).read_bytes())
        (pkg / _BAKED_FILE).write_text(version + "\n", encoding="utf-8", newline="\n")

    def bundle(self, name: str, version: str | None) -> Path:
        """Create the bundle ``name`` under ``dist``, baked at ``version``."""
        internal = self.tree / "dist" / name / "_internal" / "src"
        internal.mkdir(parents=True, exist_ok=True)
        if version is not None:
            (internal / _BAKED_FILE).write_text(
                version + "\n", encoding="utf-8", newline="\n"
            )
        return internal

    def strand(self, body: str) -> Path:
        """Write ``body`` to ``marker``, as an earlier run would have."""
        self.override.mkdir(parents=True, exist_ok=True)
        self.marker.write_text(body, encoding="utf-8", newline="\n")
        return self.marker

    def run(self) -> None:
        self._mp.setattr(main, "__file__", str(self.tree / "main.py"))
        self._mp.setattr(Path, "home", classmethod(lambda _cls: self.home))
        assert Path.home() == self.home, (
            "Path.home() was not redirected, so driving the real guard "
            "here could reach the operator's tree. Refusing."
        )
        self._mp.delenv("ACERVATOR_DEBUG_BOOT", raising=False)
        self._mp.setenv(_OVERRIDE, str(self.override))
        main._check_stale_dist_binary()


@pytest.fixture
def guard(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Guard:
    return Guard(tmp_path, monkeypatch)


class TestOneBundle:
    """One ``bundle`` under ``dist``, carrying the source version or not."""

    def test_a_matching_bundle_writes_no_warning(self, guard: Guard) -> None:
        guard.source("3.25.9")
        guard.bundle("Acervator-3.25.8-react", "3.25.8")
        guard.run()
        assert guard.marker.is_file(), (
            "the one bundle raised no warning while the source stood on "
            "another version, so the silence below proves nothing"
        )

        guard.source("3.25.8")
        guard.run()

        assert not guard.marker.exists(), (
            f"a bundle built from the source version was reported as "
            f"stale: {guard.marker.read_text(encoding='utf-8')}"
        )

    def test_a_matching_bundle_deletes_a_warning_left_by_an_earlier_run(
        self, guard: Guard
    ) -> None:
        guard.source("3.25.8")
        guard.bundle("Acervator-3.25.8-react", "3.25.8")
        stranded = guard.strand("a warning naming 3.25.6\n")

        guard.run()

        assert not stranded.exists(), (
            "the marker from an earlier run outlived the rebuild that "
            "answered it, so the operator still reads a dead warning"
        )

    def test_a_differing_bundle_writes_a_warning_naming_it(self, guard: Guard) -> None:
        guard.source("3.25.8")
        guard.bundle("Acervator-3.25.6-react", "3.25.6")

        guard.run()

        body = guard.marker.read_text(encoding="utf-8")
        assert "dist/Acervator-3.25.6-react  (built from 3.25.6)" in body, (
            f"the warning does not name the bundle that is stale, so the "
            f"operator cannot act on it:\n{body}"
        )
        assert "Live source version : 3.25.8" in body, body

    def test_the_warning_goes_to_stderr_as_well_as_the_file(
        self, guard: Guard, capsys: pytest.CaptureFixture[str]
    ) -> None:
        guard.source("3.25.8")
        guard.bundle("Acervator-3.25.6-qt", "3.25.6")
        capsys.readouterr()

        guard.run()

        assert guard.marker.read_text(encoding="utf-8") == capsys.readouterr().err


class TestSeveralBundlesCoexist:
    """``_check_stale_dist_binary`` warns only when no bundle is current."""

    def test_a_retained_older_bundle_beside_a_current_one_is_silent(
        self, guard: Guard
    ) -> None:
        guard.source("3.25.8")
        guard.bundle("Acervator-3.25.6-react", "3.25.6")
        guard.run()
        assert guard.marker.is_file(), (
            "the older bundle alone raised no warning, so the silence "
            "measured below says nothing about the retained build"
        )

        guard.bundle("Acervator-3.25.8-react", "3.25.8")
        guard.run()

        assert not guard.marker.exists(), (
            f"a deliberately retained older build was turned into a "
            f"warning:\n{guard.marker.read_text(encoding='utf-8')}"
        )

    def test_an_older_qt_bundle_beside_a_current_react_bundle_is_silent(
        self, guard: Guard
    ) -> None:
        """A qt ``bundle`` kept for comparison is a retained build, not a stale one."""
        guard.source("3.25.8")
        guard.bundle("Acervator-3.25.1-qt", "3.25.1")
        guard.run()
        assert guard.marker.is_file(), (
            "the qt bundle alone raised no warning, so the silence "
            "measured below says nothing"
        )

        guard.bundle("Acervator-3.25.8-react", "3.25.8")
        guard.run()

        assert not guard.marker.exists(), (
            f"keeping an old qt bundle for troubleshooting produced a "
            f"warning:\n{guard.marker.read_text(encoding='utf-8')}"
        )

    def test_a_current_bundle_clears_a_warning_left_beside_older_ones(
        self, guard: Guard
    ) -> None:
        guard.source("3.25.8")
        guard.bundle("Acervator-3.25.6-react", "3.25.6")
        guard.bundle("Acervator-3.25.8-qt", "3.25.8")
        stranded = guard.strand("a warning naming 3.25.6\n")

        guard.run()

        assert not stranded.exists(), (
            "a current bundle sitting beside retained older ones did not "
            "clear the earlier warning"
        )

    def test_every_bundle_is_named_when_none_of_them_is_current(
        self, guard: Guard
    ) -> None:
        guard.source("3.25.8")
        guard.bundle("Acervator-3.25.1-qt", "3.25.1")
        guard.bundle("Acervator-3.25.6-react", "3.25.6")

        guard.run()

        body = guard.marker.read_text(encoding="utf-8")
        for expected in (
            "dist/Acervator-3.25.1-qt  (built from 3.25.1)",
            "dist/Acervator-3.25.6-react  (built from 3.25.6)",
        ):
            assert expected in body, (
                f"the warning never says {expected!r}, so it reports that a "
                f"stale build exists without saying which:\n{body}"
            )

    def test_the_old_single_bundle_name_is_still_measured(self, guard: Guard) -> None:
        """A ``bundle`` named ``Acervator`` is measured like the newer names."""
        guard.source("3.25.8")
        guard.bundle("Acervator", "3.25.6")

        guard.run()

        body = guard.marker.read_text(encoding="utf-8")
        assert "dist/Acervator  (built from 3.25.6)" in body, body


class TestNoBundleTouchesNothing:
    """With no ``bundle`` to read, the guard writes nothing and removes nothing."""

    def test_an_empty_dist_leaves_a_stranded_marker_in_place(
        self, guard: Guard
    ) -> None:
        guard.source("3.25.8")
        (guard.tree / "dist").mkdir(parents=True, exist_ok=True)
        stranded = guard.strand("a warning naming 3.25.6\n")

        guard.run()
        assert stranded.is_file(), (
            "an empty dist cleared the marker; absence of evidence was "
            "read as evidence of a rebuild"
        )

        guard.bundle("Acervator-3.25.8-react", "3.25.8")
        guard.run()

        assert not stranded.exists(), (
            "POSITIVE CONTROL: the same marker survived a bundle that "
            "does carry the source version, so the survival above is a "
            "blind instrument"
        )

    def test_no_dist_directory_creates_nothing(self, guard: Guard) -> None:
        guard.source("3.25.8")

        guard.run()

        assert (
            not guard.override.exists()
        ), f"the guard created {guard.override} with no bundle to measure"
        assert not (
            guard.home / ".acervator_logs"
        ).exists(), "the guard created the operator's log directory"

    def test_the_same_driver_does_write_when_a_bundle_is_there(
        self, guard: Guard
    ) -> None:
        """POSITIVE CONTROL: the same ``Guard`` writes once a ``bundle`` exists."""
        guard.source("3.25.8")
        guard.bundle("Acervator-3.25.6-react", "3.25.6")

        guard.run()

        assert guard.override.is_dir(), (
            "the driver never wrote anything, so the absences measured "
            "beside it prove nothing"
        )
        assert guard.marker.is_file()


class TestTheWarningClearsWhenTheConditionClears:
    """Three ``run`` calls on one tree: warn, warn again, then clear."""

    def test_a_rebuild_that_lands_a_matching_bundle_clears_the_warning(
        self, guard: Guard
    ) -> None:
        guard.source("3.25.8")
        guard.bundle("Acervator-3.25.6-react", "3.25.6")
        seen = []

        guard.run()
        seen.append(guard.marker.is_file())

        guard.run()
        seen.append(guard.marker.is_file())

        guard.bundle("Acervator-3.25.8-react", "3.25.8")
        guard.run()
        seen.append(guard.marker.is_file())

        assert seen == [True, True, False], (
            f"marker existence after each run was {seen}, expected "
            f"[True, True, False]: written while nothing matched, kept "
            f"while nothing matched, removed once a build matched"
        )

    def test_the_message_is_rewritten_when_the_bundles_change(
        self, guard: Guard
    ) -> None:
        guard.source("3.25.8")
        guard.bundle("Acervator-3.25.6-react", "3.25.6")
        guard.run()
        first = guard.marker.read_text(encoding="utf-8")

        guard.bundle("Acervator-3.25.7-qt", "3.25.7")
        guard.run()
        second = guard.marker.read_text(encoding="utf-8")

        assert "Acervator-3.25.7-qt" not in first
        assert "Acervator-3.25.7-qt" in second, (
            f"the second bundle never reached the marker, so it names an "
            f"incomplete list of what is in dist:\n{second}"
        )


class TestABundleThatStatesNoVersion:
    """A ``bundle`` with no baked version is no evidence, in either direction."""

    def test_it_is_not_named_in_a_warning(self, guard: Guard) -> None:
        guard.source("3.25.8")
        guard.bundle("Acervator-3.25.6-react", "3.25.6")
        undated = guard.bundle("Acervator-unknown-qt", None)
        (undated / "__init__.py").write_text(
            "__version__ = resolve_version()\n", encoding="utf-8", newline="\n"
        )

        guard.run()

        body = guard.marker.read_text(encoding="utf-8")
        assert "resolve_version()" not in body, (
            f"a bundle whose __init__ calls resolve_version was reported "
            f"as carrying the version 'resolve_version()':\n{body}"
        )
        assert "Acervator-unknown-qt" not in body, body

    def test_a_bundle_carrying_only_a_literal_is_still_dated(
        self, guard: Guard
    ) -> None:
        """POSITIVE CONTROL: a real ``__version__`` literal is read."""
        guard.source("3.25.8")
        pre_bake = guard.bundle("Acervator", None)
        (pre_bake / "__init__.py").write_text(
            '__version__ = "3.15.43"\n', encoding="utf-8", newline="\n"
        )

        guard.run()

        body = guard.marker.read_text(encoding="utf-8")
        assert "dist/Acervator  (built from 3.15.43)" in body, body

    def test_bundles_that_state_nothing_leave_a_marker_alone(
        self, guard: Guard
    ) -> None:
        guard.source("3.25.8")
        guard.bundle("Acervator-3.25.8-react", None)
        stranded = guard.strand("a warning naming 3.25.6\n")

        guard.run()
        assert stranded.is_file(), (
            "a bundle stating no version was read as a rebuild and the "
            "marker was deleted on no evidence"
        )

        guard.bundle("Acervator-3.25.8-react", "3.25.8")
        guard.run()

        assert not stranded.exists(), (
            "POSITIVE CONTROL: baking the same bundle at the source "
            "version did not clear the marker, so the survival above is "
            "a blind instrument"
        )
