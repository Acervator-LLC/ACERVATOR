"""Issue #86 — no top-level directory is named after a stdlib module.

WHAT THIS FILE GUARDS
=====================
``tests/conftest.py`` inserts the repository root at ``sys.path[0]`` for
the whole session. A top-level directory whose name equals a stdlib
top-level module name therefore sits on the import path beside the
standard library.

Issue #86 reported that the top-level ``os/`` directory shadowed the
stdlib ``os`` module. Measured 2026-08-23 and again 2026-08-27: it did
not. Three independent protections stood, and each was sufficient alone.
The directory was renamed to ``deploy/kiosk/`` anyway, because the name
mislabelled the contents: the suite is AcervatorOS, the Raspberry Pi OS
and Debian deployment, and ``os`` reads as operating-system helpers.

The collision set is now EMPTY, so the guard below is strictly stronger
than it was: it no longer carries an exception.

PROTECTION 1 — a stdlib-named directory must not be an importable package
--------------------------------------------------------------------------
A directory without ``__init__.py`` is only a *namespace portion*. When
``PathFinder`` walks ``sys.path`` it records a portion and KEEPS WALKING;
it builds a namespace package only if no path entry yields a module with
a real loader. The stdlib ``Lib/os.py`` has a real loader, so it wins
even though it is later on the path.

This protection belongs to this repository. It is the one the guard
below enforces, and the one a single new file could remove.

PROTECTION 2 — the module is frozen into the interpreter
---------------------------------------------------------
Since CPython 3.11, ``os`` and ``os.path`` are frozen for startup.
``sys.meta_path`` runs ``FrozenImporter`` BEFORE ``PathFinder``, and
``PathFinder`` is the only finder that reads ``sys.path``. So no
``sys.path`` entry can reach ``os`` at all. ``pyproject.toml`` declares
``requires-python``, so this holds on every supported interpreter.

This protection belongs to CPython, and it LAPSES under
``python -X frozen_modules=off`` — a flag debuggers set.
``PYTHONFROZENMODULES=off`` does NOT defeat it. It also covers only the
frozen modules, not the rest of the standard library.

PROTECTION 3 — the module is already imported before user code runs
--------------------------------------------------------------------
``site.py`` imports ``os`` while the interpreter starts, so ``os`` is in
``sys.modules`` before any application module, any conftest, or any
``-c`` string executes. A cached module is returned without consulting
``sys.meta_path``. Reaching a shadow therefore also needs somebody to
purge ``sys.modules`` and import again.

MEASURED EVIDENCE (2026-08-27, CPython 3.14.4, Windows)
--------------------------------------------------------
Re-measured before the rename, with the repository root on
``sys.path[0]``. ``import os`` resolved to ``Lib/os.py`` in all four
cases: default, ``sys.modules`` purged, ``-X frozen_modules=off``, and
both together. Planting ``os/__init__.py`` and repeating the last case
resolved to the planted file, so the measurement could observe a shadow
and did not.

SCOPE
-----
This file settles the import question for every stdlib name, not only
``os``. ``KNOWN_STDLIB_NAMED_ROOT_DIRS`` is empty and a new entry is a
review, not a silent addition.
"""

from __future__ import annotations

import importlib
import sys
from importlib.machinery import PathFinder
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Top-level directories whose name equals a stdlib top-level module name.
#
# Measured 2026-08-27: none. Issue #86 renamed the one entry, `os`, to
# `deploy/kiosk/`.
#
# A NEW name landing here is not automatically a defect, but it is
# automatically a review: it must satisfy
# `test_no_stdlib_named_root_directory_is_a_package` as well.
KNOWN_STDLIB_NAMED_ROOT_DIRS: frozenset[str] = frozenset()

# A directory becomes importable as a real package when it holds one of
# these. Source, bytecode and extension forms all give PathFinder a
# loader, and a loader is what beats the stdlib module.
PACKAGE_MARKERS: tuple[str, ...] = (
    "__init__.py",
    "__init__.pyc",
    "__init__.pyd",
    "__init__.so",
)


def stdlib_named_directories(root: Path) -> set[str]:
    """Return the top-level directory names that collide with the stdlib.

    Pure over ``root`` so the positive control can point it at a
    synthetic tree instead of mutating the real one.
    """
    stdlib = sys.stdlib_module_names
    return {
        child.name
        for child in root.iterdir()
        if child.is_dir() and child.name in stdlib
    }


def shadowing_packages(root: Path) -> dict[str, str]:
    """Return every stdlib-named top-level directory that IS a package.

    Maps the directory name to the marker file that makes it importable.
    An empty result is the safe state: a stdlib-named directory may
    exist, but it must not carry a package marker.

    Pure over ``root``, for the same reason as above.
    """
    found: dict[str, str] = {}
    for name in stdlib_named_directories(root):
        for marker in PACKAGE_MARKERS:
            if (root / name / marker).exists():
                found[name] = marker
                break
    return found


# ---------------------------------------------------------------------------
# The invariant
# ---------------------------------------------------------------------------


def test_no_stdlib_named_root_directory_is_a_package() -> None:
    """No top-level directory named after a stdlib module is importable.

    This is protection 1, and it is the whole safety argument that this
    repository controls. It survives `-X frozen_modules=off`.

    If this fails, do not add a suppression. Either delete the
    ``__init__.py``, or rename the directory.
    """
    offenders = shadowing_packages(REPO)
    assert offenders == {}, (
        "A top-level directory named after a stdlib module has become an "
        f"importable package: {offenders}. This can shadow the standard "
        "library under `python -X frozen_modules=off`. Remove the package "
        "marker or rename the directory (issue #86)."
    )


def test_the_set_of_stdlib_named_root_directories_is_known() -> None:
    """The collision set is exactly the one that was measured.

    A new stdlib-named directory is a review trigger, not a silent
    addition. Update ``KNOWN_STDLIB_NAMED_ROOT_DIRS`` deliberately, and
    say in the commit why the new one is safe.
    """
    assert stdlib_named_directories(REPO) == KNOWN_STDLIB_NAMED_ROOT_DIRS


# ---------------------------------------------------------------------------
# The positive control — the guard must FIRE, not only stay quiet
# ---------------------------------------------------------------------------


def test_the_guard_fires_on_a_planted_package(tmp_path: Path) -> None:
    """A planted ``os/__init__.py`` is detected.

    Without this, a guard that always returned ``{}`` would pass the
    invariant test above and prove nothing. The synthetic tree keeps the
    control out of the real repository, so nothing is mutated and
    nothing needs restoring.
    """
    planted = tmp_path / "os"
    planted.mkdir()
    (planted / "install.sh").write_text("echo hi\n", encoding="utf-8")

    # Shaped like the real tree: stdlib-named, but not yet a package.
    assert stdlib_named_directories(tmp_path) == {"os"}
    assert shadowing_packages(tmp_path) == {}

    # One file turns it into a shadowing package.
    (planted / "__init__.py").write_text("", encoding="utf-8")
    assert shadowing_packages(tmp_path) == {"os": "__init__.py"}


def test_the_guard_stays_quiet_on_a_legitimate_package(tmp_path: Path) -> None:
    """A normal package whose name is NOT a stdlib module is ignored.

    The negative half of the control. The guard must key on the stdlib
    name collision, not on the presence of ``__init__.py``, or it would
    condemn every ordinary package in the tree.
    """
    ordinary = tmp_path / "acervator_deploy"
    ordinary.mkdir()
    (ordinary / "__init__.py").write_text("", encoding="utf-8")

    assert stdlib_named_directories(tmp_path) == set()
    assert shadowing_packages(tmp_path) == {}


# ---------------------------------------------------------------------------
# End-to-end: the claim itself, under the worst supported conditions
# ---------------------------------------------------------------------------


def test_the_path_finder_finds_no_importable_os_in_the_repository() -> None:
    """`PathFinder` asked to search ONLY the repository root finds nothing.

    This tests protection 1 at its source, with protections 2 and 3
    removed by construction rather than by flags:

    * ``PathFinder`` is called directly, so ``FrozenImporter`` never runs
      and protection 2 cannot mask the result.
    * ``find_spec`` consults no cache, so protection 3 cannot mask it
      either.
    * the search path is the repository root alone, so a stdlib hit
      cannot be mistaken for safety.

    Before issue #86 renamed the directory this returned a LOADERLESS
    ``ModuleSpec`` — a namespace portion, harmless because ``PathFinder``
    records a portion and keeps walking. It now returns ``None``.

    The assertion is on the LOADER and not on the spec, because a
    loaderless portion is safe and a loader is not. Asserting ``spec is
    None`` would report a safe tree as broken, and would be a test of the
    wrong mechanism. ``test_the_path_finder_reports_a_loader_for_a_real_
    package`` drives the same call to a non-None loader, so this
    assertion is a control and not a tautology.
    """
    spec = PathFinder.find_spec("os", [str(REPO)])
    loader = None if spec is None else spec.loader
    assert loader is None, (
        f"The repository root offers an importable `os` with a real "
        f"loader: {spec}. A loaderless namespace portion is harmless, but "
        "a loader beats the standard library. A top-level os/ directory "
        "can now shadow it (issue #86)."
    )


def test_the_path_finder_reports_a_loader_for_a_real_package(
    tmp_path: Path,
) -> None:
    """Positive control for the call above, on a synthetic tree.

    Three states of one directory, through the same ``PathFinder`` call:
    absent, a namespace portion, and a package. Only the third yields a
    loader. Without this, an assertion of ``loader is None`` would pass
    on a ``find_spec`` that had stopped working.

    ``importlib.invalidate_caches`` runs after every mutation.
    ``FileFinder`` caches a directory listing and keys the cache on the
    directory mtime, whose resolution is coarser than the interval
    between these three writes. Without the invalidation this test reads
    a stale listing and fails intermittently.
    """
    assert PathFinder.find_spec("os", [str(tmp_path)]) is None

    planted = tmp_path / "os"
    planted.mkdir()
    (planted / "install.sh").write_text("echo hi", encoding="utf-8")
    importlib.invalidate_caches()
    portion = PathFinder.find_spec("os", [str(tmp_path)])
    assert portion is not None and portion.loader is None, portion

    (planted / "__init__.py").write_text("", encoding="utf-8")
    importlib.invalidate_caches()
    package = PathFinder.find_spec("os", [str(tmp_path)])
    assert package is not None, "PathFinder found no spec for a real package"
    assert package.loader is not None, (
        "PathFinder reported no loader for a directory holding "
        "__init__.py; the call this file relies on is not working"
    )
