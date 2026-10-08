"""Print, check and lock the dependency set that `pyproject.toml` states.

`load_project` reads `[project]` and raises `DependencySourceError` on a missing
table or an empty `dependencies` list. `CONSUMER_EXTRAS` names the extras each
build and install script asks for, so no script spells a package name itself.
`requirements` prints the lines a caller passes to pip, `check` reports what is
not installed, and `lock` writes one file under `REQUIREMENTS_DIR`.
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

# `os` targets a Raspberry Pi running from source, so it never gets pyinstaller.
CONSUMER_EXTRAS: dict[str, tuple[str, ...]] = {
    "build": ("build", "report", "monitor"),
    "os": ("report",),
    "display": ("display",),
    "dev": ("dev",),
    "contracts": ("contracts",),
    "ci": ("test", "lint"),
    "all": (
        "report",
        "test",
        "lint",
        "charts",
        "monitor",
        "display",
        "build",
        "dev",
        "contracts",
    ),
}


class DependencySourceError(RuntimeError):
    """The one source could not be read, or it answered nothing."""


def load_project(pyproject: Path = PYPROJECT) -> dict[str, Any]:
    """Return the `[project]` table in `pyproject`, or raise.

    `DependencySourceError` covers a missing file, a missing table and an
    empty `dependencies` list alike.
    """
    if not pyproject.is_file():
        raise DependencySourceError(f"no dependency source at {pyproject}")
    with pyproject.open("rb") as handle:
        parsed = tomllib.load(handle)
    project = parsed.get("project")
    if not isinstance(project, dict):
        raise DependencySourceError(
            f"{pyproject} has no [project] table; there is no source to read"
        )
    core = project.get("dependencies")
    if not isinstance(core, list) or not core:
        raise DependencySourceError(
            f"{pyproject} states no [project] dependencies; refusing to "
            "report an empty install set"
        )
    return project


def optional_table(project: dict[str, Any]) -> dict[str, list[str]]:
    """Return `[project.optional-dependencies]`, or an empty mapping."""
    extras = project.get("optional-dependencies")
    if not isinstance(extras, dict):
        return {}
    return {
        name: [str(req) for req in reqs]
        for name, reqs in extras.items()
        if isinstance(reqs, list)
    }


def distribution_name(requirement: str) -> str:
    """Return the distribution name at the front of a requirement string.

    `"pytest-xdist>=3.8.0"` answers `"pytest-xdist"`.
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

    The core list comes first, then each extra in the order named, once each.
    """
    project = load_project(pyproject)
    table = optional_table(project)
    unknown = [name for name in extras if name not in table]
    if unknown:
        raise DependencySourceError(
            f"pyproject.toml declares no extra named {unknown}; "
            f"it declares {sorted(table)}"
        )
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
    for req in requirements_for(_extras_from(args), include_core=not args.extras_only):
        print(req)
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    """Report which of the consumer's requirements are not installed.

    Presence only: `distribution_name` is checked, the version specifier is not.
    """
    reqs = requirements_for(_extras_from(args), include_core=not args.extras_only)
    missing: list[str] = []
    for req in reqs:
        version = installed_version(req)
        if version is None:
            missing.append(req)
        else:
            print(f"  ok      {distribution_name(req):18s} {version}")
    for req in missing:
        print(f"  MISSING {distribution_name(req):18s} ({req})")
    print(
        f"\n  {len(reqs) - len(missing)} of {len(reqs)} present " f"({args.consumer})"
    )
    return 1 if missing else 0


def cmd_lock(args: argparse.Namespace) -> int:
    """Regenerate the `lock_name` file under `REQUIREMENTS_DIR` with pip-compile.

    Returns exit code 2 when pip-tools is absent.
    """
    if installed_version("pip-tools") is None:
        print("  pip-tools is not installed in this interpreter.", file=sys.stderr)
        print(
            '  Install the dev extra first:  pip install -e ".[dev]"', file=sys.stderr
        )
        return 2
    REQUIREMENTS_DIR.mkdir(exist_ok=True)
    out = REQUIREMENTS_DIR / lock_name(args.consumer)
    # Without `--no-header`, pip-compile records its own command line in `out`.
    argv = [
        sys.executable,
        "-m",
        "piptools",
        "compile",
        "--quiet",
        "--strip-extras",
        "--output-file",
        str(out),
    ]
    for extra in _extras_from(args):
        argv += ["--extra", extra]
    argv.append(str(PYPROJECT))
    # `sys.executable` is absolute, so S607 does not apply here.
    result = subprocess.run(argv, cwd=str(REPO_ROOT), check=False)  # noqa: S603
    if result.returncode != 0:
        print(f"  pip-compile failed, exit {result.returncode}", file=sys.stderr)
        return result.returncode
    print(f"  wrote {out}")
    return 0


def lock_name(consumer: str) -> str:
    """Return the lock file name for `consumer` on this platform.

    The platform and the interpreter version are both in the name.
    """
    return (
        f"{consumer}-{sys.platform}-py"
        f"{sys.version_info.major}.{sys.version_info.minor}.txt"
    )


def _extras_from(args: argparse.Namespace) -> tuple[str, ...]:
    """Return the extras to use: the explicit ones, else the consumer's."""
    if args.extra:
        return tuple(args.extra)
    return CONSUMER_EXTRAS[args.consumer]


def _add_common(parser: argparse.ArgumentParser) -> None:
    """Give a subcommand the consumer selector every subcommand shares."""
    parser.add_argument(
        "consumer",
        nargs="?",
        default="all",
        choices=sorted(CONSUMER_EXTRAS),
        help="which install this is for, default all",
    )
    parser.add_argument(
        "--extra",
        action="append",
        default=[],
        help="name an extra directly, overriding the consumer",
    )
    parser.add_argument(
        "--extras-only",
        action="store_true",
        help="omit the core [project] dependencies",
    )


def build_parser() -> argparse.ArgumentParser:
    """Return the `argparse` parser `main` uses."""
    parser = argparse.ArgumentParser(
        prog="python -m tools.deps",
        description="Read the dependency set out of pyproject.toml. "
        "A package name lives in that file and nowhere else.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_req = sub.add_parser("requirements", help="print one requirement string per line")
    _add_common(p_req)
    p_req.set_defaults(func=cmd_requirements)

    p_check = sub.add_parser(
        "check", help="report which requirements are not installed"
    )
    _add_common(p_check)
    p_check.set_defaults(func=cmd_check)

    p_lock = sub.add_parser(
        "lock", help="regenerate requirements/<consumer>-<platform>-<py>.txt"
    )
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
