"""Issue #86 — the top-level ``os/`` directory does NOT shadow the stdlib.

WHY THIS FILE EXISTS
====================
Issue #86 says the top-level ``os/`` directory "shadows the stdlib".
Measured on 2026-08-23, it does not, and the rename the issue proposes
was refused on that evidence. This file pins the reason, so the refusal
is enforced by the suite instead of remembered by a reader.

``tests/conftest.py`` inserts the repository root at ``sys.path[0]`` for
the whole session, and a directory named ``os`` sits at that root. That
looks like a collision. Two independent mechanisms prevent it, and
either one alone is sufficient.

PROTECTION 1 — ``os/`` is not an importable package
---------------------------------------------------
``os/`` holds no ``__init__.py``. A directory without ``__init__.py`` is
only a *namespace portion*. When ``PathFinder`` walks ``sys.path`` it
records a portion and KEEPS WALKING; it only builds a namespace package
if no path entry yields a module with a real loader. The stdlib
``Lib/os.py`` has a real loader, so it wins even though it is later on
the path.

This protection belongs to this repository. It is the one the guard
below enforces.

PROTECTION 2 — ``os`` is frozen into the interpreter
-----------------------------------------------------
Since CPython 3.11, ``os`` and ``os.path`` are frozen for startup.
``sys.meta_path`` runs ``FrozenImporter`` BEFORE ``PathFinder``, and
``PathFinder`` is the only finder that reads ``sys.path``. So no
``sys.path`` entry can reach ``os`` at all. ``pyproject.toml`` declares
``requires-python = ">=3.11"``, so this holds on every supported
interpreter.

This protection belongs to CPython, not to us, and it LAPSES under
``python -X frozen_modules=off`` — a flag debuggers do set. That is
exactly why protection 1 is the one worth guarding: it is the one that
survives the debugger, and it is the one a future commit could remove
by adding a single file.

PROTECTION 3 — ``os`` is already imported before user code runs
----------------------------------------------------------------
``site.py`` imports ``os`` while the interpreter starts, so ``os`` is in
``sys.modules`` before any application module, any conftest, or any
``-c`` string executes. A cached module is returned without consulting
``sys.meta_path`` at all. Reaching the shadow therefore also needs
somebody to purge ``sys.modules['os']`` and import it again.

MEASURED EVIDENCE (2026-08-23, CPython 3.14.4, Windows)
--------------------------------------------------------
Shadowing needs all three protections defeated at once:

    os/__init__.py  frozen  how `os` is imported     resolves to
    --------------  ------  -----------------------  -----------
    absent          on      any                      stdlib   <- tree today
    absent          off     any                      stdlib   <- prot. 1
    present         on      any                      stdlib   <- prot. 2
    present         off     normal startup           stdlib   <- prot. 3
    present         off     purged, then re-imported os/      <- ONLY failure

Only the last row shadows. It needs a new file that is not in the tree,
a non-default interpreter flag, AND a deliberate re-import. That is why
issue #86's rename was refused: the collision it reports is not
reachable.

Note that ``PYTHONFROZENMODULES=off`` does NOT defeat protection 2 on
this interpreter; only the ``-X frozen_modules=off`` flag does. Measured
the same day.

SCOPE
-----
This file does not defend the NAME. "os" reads as "operating-system
helpers" when the directory is really AcervatorOS, the Raspberry Pi OS
and Debian deployment. That is a real mislabelling and issue #86 keeps
it. This file only settles the import question.
"""
from __future__ import annotations

import sys
from importlib.machinery import PathFinder
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Top-level directories whose name equals a stdlib top-level module name.
#
# Measured 2026-08-23: exactly one, `os`. It is AcervatorOS, the
# Raspberry Pi deployment suite. It is safe because it is not an
# importable package, which `test_no_stdlib_named_root_directory_is_a_package`
# enforces.
#
# A NEW name landing here is not automatically a defect, but it is
# automatically a review: it must satisfy the same guard.
KNOWN_STDLIB_NAMED_ROOT_DIRS: frozenset[str] = frozenset({"os"})

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
    * the search path is restricted to the repository root alone, so a
      stdlib hit cannot be mistaken for safety.

    The result today is NOT ``None``. ``PathFinder`` reports the
    directory as a namespace portion::

        ModuleSpec(name='os', loader=None,
                   submodule_search_locations=_NamespacePath([...os]))

    A LOADER is what matters, and this spec has none. When ``PathFinder``
    walks the real ``sys.path`` it records a loaderless portion and keeps
    walking, so the stdlib ``Lib/os.py`` — which does have a loader —
    still wins. Adding ``os/__init__.py`` is what fills in the loader,
    and that is the moment the shadow becomes real.

    So the assertion is on the loader, not on the spec. Asserting
    ``spec is None`` would fail on a tree that is perfectly safe, and
    would be a test of the wrong mechanism.

    Verified 2026-08-23 that the loader IS populated when an
    ``os/__init__.py`` is planted, so this is a control and not a
    tautology. A probe that cannot fail would prove nothing.
    """
    spec = PathFinder.find_spec("os", [str(REPO)])
    loader = None if spec is None else spec.loader
    assert loader is None, (
        f"The repository root offers an importable `os` with a real "
        f"loader: {spec}. A loaderless namespace portion is harmless, but "
        "a loader beats the standard library. The top-level os/ directory "
        "can now shadow it (issue #86)."
    )
