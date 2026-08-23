"""Print, check and lock the dependency set that `pyproject.toml` states.

WHY THIS TOOL EXISTS
====================
Issue #94. The pip install list was hand-copied into eight places and no
two of them agreed. Measured on 2026-08-23 at commit 4965bab:

    build_mac.sh:46          14 names
    build_windows.ps1:28     14 names, the same 14
    Acervator_win.spec:8     14 names, in a docstring
    Acervator_mac.spec:8     14 names, in a docstring
    BUILD.py:79              12 names, as (import name, pip name) pairs
    os/install.sh:177        11 names, plus 4 more at :192
    os/update.sh:71          11 names
    README.md:123             6 names
    pyproject.toml           11 names

    In `pyproject.toml` and in no other list: psutil, defusedxml.
    In every build list, and in `pyproject.toml` in none of them:
    certifi, requests, reportlab, pillow.
    `defusedxml` is a module-level import at
    src/gui/crypto_news_ticker.py:51, so every build list was missing a
    hard requirement.
    `requests` is imported by no file in the repository.

Every one of those lists is now a call to this tool, so a package name
lives in exactly one place: `[project] dependencies` and
`[project.optional-dependencies]` in `pyproject.toml`.

WHAT THIS TOOL WILL NOT DO
==========================
It never installs anything, and it never writes outside `requirements/`.
`requirements` prints lines for a caller to pass to pip. `check` reports
and sets an exit code. `lock` writes one file and refuses when it cannot.

It also refuses an empty answer. A tool that reads a file with no
`[project]` table, prints nothing and exits 0 reads exactly like a clean
result. Issue #83 removed three tools that did that. Every subcommand
below fails loudly instead.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tomllib
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = REPO_ROOT / "pyproject.toml"
REQUIREMENTS_DIR = REPO_ROOT / "requirements"

# The extras each consumer asks for. Written here, and not in the
# consumer script, so that `tests/test_one_dependency_source.py` reads
# one table instead of parsing five scripts.
#
#   build   a PyInstaller HOST. It compiles the application, so it adds
#           pyinstaller. It also takes `report`, because reportlab ships
#           INSIDE the frozen application for the version sweep PDF.
#   os      an AcervatorOS TARGET, a Raspberry Pi. It runs from source
#           in a venv and never compiles, so it must NOT get pyinstaller.
#   display the mini-panel libraries. Separate from `os` because
#           `os/install.sh` installs them with failure tolerated: a Pi
#           with no panel is a supported machine.
#   dev     the checkers the archetypes spawn, and the type stubs.
CONSUMER_EXTRAS: dict[str, tuple[str, ...]] = {
    "build": ("build", "report"),
    "os": ("report",),
    "display": ("display",),
    "dev": ("dev",),
    "all": ("report", "video", "charts", "monitor", "display", "build", "dev"),
}


class DependencySourceError(RuntimeError):
    """The one source could not be read, or it answered nothing."""


def load_project(pyproject: Path = PYPROJECT) -> dict[str, Any]:
    """Return the `[project]` table, or raise.

    A missing file, a missing table, and an empty `dependencies` list are
    all failures. None of them may return an empty answer, because an
    empty answer downstream means "install nothing", and that reads as
    success.
    """
    if not pyproject.is_file():
        raise DependencySourceError(f"no dependency source at {pyproject}")
    with pyproject.open("rb") as handle:
        parsed = tomllib.load(handle)
    project = parsed.get("project")
    if not isinstance(project, dict):
        raise DependencySourceError(
            f"{pyproject} has no [project] table; there is no source to read")
    core = project.get("dependencies")
    if not isinstance(core, list) or not core:
        raise DependencySourceError(
            f"{pyproject} states no [project] dependencies; refusing to "
            "report an empty install set")
    return project


def optional_table(project: dict[str, Any]) -> dict[str, list[str]]:
    """Return `[project.optional-dependencies]`, or an empty mapping."""
    extras = project.get("optional-dependencies")
    if not isinstance(extras, dict):
        return {}
    return {name: [str(req) for req in reqs]
            for name, reqs in extras.items() if isinstance(reqs, list)}


def distribution_name(requirement: str) -> str:
    """Return the distribution name at the front of a requirement string.

    `"pytest-xdist>=3.8.0"` answers `"pytest-xdist"`. The specifier
    grammar is PEP 508. Only the name is needed here, and it ends at the
    first character that cannot be part of a name.
    """
    name = requirement.strip()
    for index, char in enumerate(name):
        if not (char.isalnum() or char in "-_."):
            return name[:index]
    return name


def requirements_for(
    extras: tuple[str, ...] = (),
    *,
    include_core: bool = True,
    pyproject: Path = PYPROJECT,
) -> list[str]:
    """Return the requirement strings for the core set plus `extras`.

    Order is stable: the core list in the order the file states it, then
    each extra in the order named, with a duplicate dropped after its
    first sight. `pillow` is in three extras and must be emitted once.
    """
    project = load_project(pyproject)
    table = optional_table(project)
    unknown = [name for name in extras if name not in table]
    if unknown:
        raise DependencySourceError(
            f"pyproject.toml declares no extra named {unknown}; "
            f"it declares {sorted(table)}")
    source: list[str] = []
    if include_core:
        source.extend(str(req) for req in project["dependencies"])
    for name in extras:
        source.extend(table[name])
    ordered: list[str] = []
    seen: set[str] = set()
    for req in source:
        key = distribution_name(req).lower()
        if key not in seen:
            seen.add(key)
            ordered.append(req)
    if not ordered:
        raise DependencySourceError("the requirement set came out empty")
    return ordered


def installed_version(requirement: str) -> str | None:
    """Return the installed version of a requirement, or None."""
    try:
        return distribution(distribution_name(requirement)).version
    except PackageNotFoundError:
        return None


def cmd_requirements(args: argparse.Namespace) -> int:
    """Print one requirement string per line for the named consumer."""
    for req in requirements_for(_extras_from(args),
                                include_core=not args.extras_only):
        print(req)
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    """Report which of the consumer's requirements are not installed.

    Presence only. This does NOT evaluate the version specifier, and the
    reason is written down rather than left to be found: evaluating one
    needs `packaging`, which `pyproject.toml` does not declare, and this
    tool may not depend on something the one source does not state.
    `requirements/` holds the resolved versions for that comparison.
    """
    reqs = requirements_for(_extras_from(args),
                            include_core=not args.extras_only)
    missing: list[str] = []
    for req in reqs:
        version = installed_version(req)
        if version is None:
            missing.append(req)
        else:
            print(f"  ok      {distribution_name(req):18s} {version}")
    for req in missing:
        print(f"  MISSING {distribution_name(req):18s} ({req})")
    print(f"\n  {len(reqs) - len(missing)} of {len(reqs)} present "
          f"({args.consumer})")
    return 1 if missing else 0


def cmd_lock(args: argparse.Namespace) -> int:
    """Regenerate the resolved requirement file with pip-compile.

    Refuses when pip-tools is absent. A lock file that no resolver
    produced is a claim, not a measurement.
    """
    if installed_version("pip-tools") is None:
        print("  pip-tools is not installed in this interpreter.",
              file=sys.stderr)
        print('  Install the dev extra first:  pip install -e ".[dev]"',
              file=sys.stderr)
        return 2
    REQUIREMENTS_DIR.mkdir(exist_ok=True)
    out = REQUIREMENTS_DIR / lock_name(args.consumer)
    # `--no-header` is deliberately NOT passed. pip-compile writes the
    # exact command line it ran into the head of the file, which is the
    # only provenance a reader gets for a resolved set.
    argv = [sys.executable, "-m", "piptools", "compile",
            "--quiet", "--strip-extras", "--output-file", str(out)]
    for extra in _extras_from(args):
        argv += ["--extra", extra]
    argv.append(str(PYPROJECT))
    # S607 IS FIXED BY CONSTRUCTION, NOT SUPPRESSED, following the
    # reasoning at the top of dev_harness/harness/coding_archetype.py:
    # `sys.executable` is an absolute path, so a `python.exe` planted
    # earlier on PATH cannot run here. S603 is the residue and is not
    # avoidable, because an argv carrying a variable draws it and a
    # resolved interpreter path is a variable by definition.
    result = subprocess.run(argv, cwd=str(REPO_ROOT), check=False)  # noqa: S603
    if result.returncode != 0:
        print(f"  pip-compile failed, exit {result.returncode}",
              file=sys.stderr)
        return result.returncode
    print(f"  wrote {out}")
    return 0


def lock_name(consumer: str) -> str:
    """Return the lock file name for a consumer on this platform.

    The platform and the interpreter are IN THE NAME, because a resolved
    set is true for one of each and for no other. A Windows lock file
    installs the wrong wheels on a Raspberry Pi.
    """
    return (f"{consumer}-{sys.platform}-py"
            f"{sys.version_info.major}.{sys.version_info.minor}.txt")


def _extras_from(args: argparse.Namespace) -> tuple[str, ...]:
    """Return the extras to use: the explicit ones, else the consumer's."""
    if args.extra:
        return tuple(args.extra)
    return CONSUMER_EXTRAS[args.consumer]


def _add_common(parser: argparse.ArgumentParser) -> None:
    """Give a subcommand the consumer selector every subcommand shares."""
    parser.add_argument("consumer", nargs="?", default="all",
                        choices=sorted(CONSUMER_EXTRAS),
                        help="which install this is for, default all")
    parser.add_argument("--extra", action="append", default=[],
                        help="name an extra directly, overriding the consumer")
    parser.add_argument("--extras-only", action="store_true",
                        help="omit the core [project] dependencies")


def build_parser() -> argparse.ArgumentParser:
    """Return the argument parser. Named so that a test can reach it."""
    parser = argparse.ArgumentParser(
        prog="python -m tools.deps",
        description="Read the dependency set out of pyproject.toml. "
                    "A package name lives in that file and nowhere else.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_req = sub.add_parser("requirements",
                           help="print one requirement string per line")
    _add_common(p_req)
    p_req.set_defaults(func=cmd_requirements)

    p_check = sub.add_parser(
        "check", help="report which requirements are not installed")
    _add_common(p_check)
    p_check.set_defaults(func=cmd_check)

    p_lock = sub.add_parser(
        "lock", help="regenerate requirements/<consumer>-<platform>-<py>.txt")
    _add_common(p_lock)
    p_lock.set_defaults(func=cmd_lock)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns a process exit code and never raises."""
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except DependencySourceError as exc:
        print(f"  ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
