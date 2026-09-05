"""
BUILD - Acervator Build Launcher
Double-click this file to build the application.
Automatically detects and installs all required dependencies.
``parse_variants`` reads ``--variant NAME``; a double-click builds every variant.
"""

# S607 IS FIXED BY CONSTRUCTION, NOT SUPPRESSED, following the reasoning at
# the top of dev_harness/harness/coding_archetype.py. Every spawn below runs
# either `sys.executable`, which is already absolute, or a PowerShell path
# resolved with shutil.which, so a `powershell.cmd` planted earlier on PATH
# cannot run under the operator token during a build.
#
# S603 remains and is not avoidable: an all-literal argv draws none, and every
# argv carrying a variable draws one. A resolved executable path is a variable
# by definition. This directive is the residue, narrowed to the one rule.
# ruff: noqa: S603
import argparse
import os
import shutil
import subprocess
import sys

from tools.build_variants import selected_variants

_script_dir = os.path.dirname(os.path.abspath(__file__))
try:
    os.chdir(_script_dir)
except OSError as exc:
    # Not fatal: run_build uses absolute paths anyway. It is printed and
    # not swallowed, because a build that cannot enter its own directory
    # is worth seeing.
    print(f"  NOTE: could not change directory to {_script_dir}: {exc}")

HEADER = """
============================================================
  Acervator - Build Launcher
============================================================
"""

SMARTSCREEN_NOTICE = """
------------------------------------------------------------
  IF WINDOWS BLOCKS THE EXE:

  1. Click "More info" then "Run anyway"
     (one-time per build)

  2. OR permanently fix it:
     Settings > Privacy & Security > Windows Security
     > App & Browser Control > Smart App Control
     > Set to "Off"

  3. OR right-click the exe > Properties > Unblock > OK
------------------------------------------------------------
"""

SMARTSCREEN_HELP = """QUANTUM AUTO TRADER - IF WINDOWS BLOCKS THIS APP
=================================================

Windows SmartScreen may block this application because it is
not signed with a commercial code-signing certificate. This
is normal for self-built applications and does not indicate
a security threat.

TO RUN THE APPLICATION:

Option 1: Click "More info" then "Run anyway"
  - This works once per build

Option 2: Disable Smart App Control (permanent)
  - Open Settings
  - Go to Privacy & Security > Windows Security
  - Click App & Browser Control
  - Click Smart App Control settings
  - Set to "Off"
  - Note: This cannot be re-enabled without resetting Windows

Option 3: Unblock the exe file
  - Right-click Acervator.exe
  - Select Properties
  - Check "Unblock" at the bottom
  - Click OK

Option 4: Add Defender exclusion (done automatically by build)
  - The build script attempts to add this folder to
    Windows Defender exclusions. If it failed, you can
    add it manually:
  - Open Windows Security > Virus & Threat Protection
  - Click Manage Settings under Virus & Threat Protection Settings
  - Scroll to Exclusions > Add or Remove Exclusions
  - Add this folder as an exclusion
"""

# Issue #94 - REQUIRED_PACKAGES used to be a hand-copied list of 12
# (import name, pip name) pairs. It disagreed with pyproject.toml in both
# directions: it was missing `tomli_w`, `aiohttp` and `defusedxml`, and it
# named `certifi` and `pyinstaller`, which pyproject.toml did not declare.
#
# The names now come from `tools/deps.py`, which reads pyproject.toml. This
# file holds no package name at all. `CONSUMER = "build"` selects the core
# set plus the `build` and `report` extras, which is what a PyInstaller HOST
# needs. `tests/test_one_dependency_source.py` fails if a list returns here.
CONSUMER = "build"


def check_python() -> bool:
    """Verify Python version meets minimum requirements.

    The floor repeats the `requires-python` lower bound in pyproject.toml.
    """
    print(f"  Python: {sys.version}")
    if sys.version_info < (3, 14):
        print("\n  ERROR: Python 3.14 or higher is required.")
        print("  Download from https://www.python.org/downloads/")
        return False
    print(f"  Path:   {sys.executable}")
    return True


def check_pip() -> bool:
    """Ensure pip is available."""
    result = subprocess.run(
        [sys.executable, "-m", "pip", "--version"],
        capture_output=True,
    )
    if result.returncode == 0:
        return True
    print("\n  pip not found. Installing...")
    try:
        subprocess.check_call(
            [sys.executable, "-m", "ensurepip", "--upgrade"],
            stdout=subprocess.DEVNULL,
        )
        return True
    except subprocess.CalledProcessError as exc:
        print(f"  ERROR: Could not install pip: {exc}")
        print("  Manual fix: python -m ensurepip --upgrade")
        return False


def install_package(requirement: str) -> bool:
    """Install a single requirement via pip."""
    cmd = [sys.executable, "-m", "pip", "install", requirement, "--quiet"]
    if sys.version_info >= (3, 12):
        cmd.append("--break-system-packages")
    return subprocess.run(cmd, capture_output=True, check=False).returncode == 0


def check_and_install_deps() -> bool:
    """Check every requirement the one source states; install the missing.

    The requirement set is READ, never held. `tools.deps` raises when
    pyproject.toml is absent, has no `[project]` table, or states an
    empty dependency list, and this function then refuses. An empty set
    would otherwise install nothing and print "All dependencies
    satisfied", which reads exactly like a clean result.
    """
    from tools.deps import (
        CONSUMER_EXTRAS,
        DependencySourceError,
        distribution_name,
        installed_version,
        requirements_for,
    )

    try:
        required = requirements_for(CONSUMER_EXTRAS[CONSUMER])
    except DependencySourceError as exc:
        print(f"\n  ERROR: {exc}")
        print("  pyproject.toml is the only dependency source. Restore it.")
        return False

    print(
        f"  Source: pyproject.toml, {len(required)} requirements "
        f"for the {CONSUMER} install"
    )

    missing = [req for req in required if installed_version(req) is None]
    present = [req for req in required if installed_version(req) is not None]

    if present:
        names = ", ".join(distribution_name(req) for req in present)
        print(f"  Installed: {names}")

    if not missing:
        print("  All dependencies satisfied.")
        return True

    absent = ", ".join(distribution_name(req) for req in missing)
    print(f"\n  Missing: {absent}")
    print("  Installing...\n")

    failed = []
    for req in missing:
        print(f"    Installing {req}...", end=" ", flush=True)
        if install_package(req):
            print("OK")
        else:
            print("FAILED")
            failed.append(req)

    if failed:
        print(f"\n  ERROR: Failed to install: {', '.join(failed)}")
        print(f"  Manual fix: pip install {' '.join(failed)}")
        return False

    print("\n  All dependencies installed.")
    return True


def powershell_exe() -> str:
    """Return an absolute PowerShell path, or an empty string.

    The bare name `powershell` used to go into the argv. PATH plus
    PATHEXT would then run a `powershell.cmd` planted anywhere earlier
    on PATH, under the operator token, during a build. Resolving the
    name here removes that, and it removes ruff S607 by construction
    rather than by a directive.
    """
    return shutil.which("powershell") or ""


def parse_variants(argv: list[str] | None = None) -> tuple[str, ...]:
    """Return the variants ``--variant`` names in ``argv``, or every known one.

    Raises ``ValueError`` through ``selected_variants`` on an unknown name.
    """
    parser = argparse.ArgumentParser(
        prog="BUILD.py",
        description="Build Acervator. Every variant is built unless one is named.",
    )
    parser.add_argument(
        "--variant",
        action="append",
        default=[],
        metavar="NAME",
        help="build only this variant; repeat or comma-separate for several",
    )
    parsed = parser.parse_args(sys.argv[1:] if argv is None else argv)
    return selected_variants(parsed.variant)


def run_build(variants: tuple[str, ...]) -> bool:
    """Execute the PowerShell build script for ``variants``."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    ps1_path = os.path.join(script_dir, "build_windows.ps1")

    if not os.path.exists(ps1_path):
        print(f"\n  ERROR: build_windows.ps1 not found at:\n  {ps1_path}")
        print("  Make sure BUILD.py and build_windows.ps1 are in the " "same folder.")
        return False

    powershell = powershell_exe()
    if not powershell:
        print("\n  ERROR: powershell not found on PATH.")
        print("  The Windows build runs build_windows.ps1 and needs it.")
        return False

    print(f"\n  Script: {ps1_path}")
    print(f"  Variants: {', '.join(variants)}")
    print("  Starting build...\n")
    print("=" * 60)

    # The spec reads the variant from the environment, and build_windows.ps1
    # sets it per variant. -Variant takes one comma-joined argv token.
    result = subprocess.run(
        [
            powershell,
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            ps1_path,
            "-Variant",
            ",".join(variants),
        ],
        cwd=script_dir,
        check=False,
    )
    print("=" * 60)

    # Try to add Defender exclusion (requires admin). The whole dist root,
    # because each build adds another folder under it and none are removed.
    exe_path = "dist"
    if os.path.isdir(exe_path):
        print("\n  Adding Windows Defender exclusion...")
        exe_quoted = f'"{os.path.abspath(exe_path)}"'
        inner = (
            f'Start-Process "{powershell}" -Verb RunAs -Wait '
            f"-ArgumentList '-Command Add-MpPreference "
            f"-ExclusionPath {exe_quoted}'"
        )
        exc_result = subprocess.run(
            [powershell, "-Command", inner],
            capture_output=True,
            check=False,
        )
        if exc_result.returncode == 0:
            print("  Defender exclusion added.")
        else:
            print("  Defender exclusion skipped (admin prompt declined).")

    return result.returncode == 0


def build_outputs() -> list:
    """Return every built executable under dist, newest first.

    The build names each folder after the version and the variant it
    produced, so there is no single fixed path to look at any more. Every
    folder is reported and none is removed; the operator picks which build
    to run.
    """
    dist_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dist")
    if not os.path.isdir(dist_dir):
        return []
    found = []
    for name in os.listdir(dist_dir):
        exe = os.path.join(dist_dir, name, f"{name}.exe")
        if os.path.exists(exe):
            found.append(exe)
    found.sort(key=os.path.getmtime, reverse=True)
    return found


def write_smartscreen_help(folder: str) -> None:
    """Write the "if Windows blocks this" note beside a built executable."""
    help_path = os.path.join(folder, "IF_BLOCKED_READ_THIS.txt")
    try:
        with open(help_path, "w", encoding="utf-8") as handle:
            handle.write(SMARTSCREEN_HELP)
        print(f"  Help file: {help_path}")
    except OSError as exc:
        # Printed and not swallowed. The build succeeded; only the note
        # beside the exe is missing, and the reader must be able to see why.
        print(f"  NOTE: help file not written: {exc}")


def main() -> None:
    print(HEADER)

    try:
        variants = parse_variants()
    except ValueError as exc:
        print(f"\n  ERROR: {exc}")
        input("\nPress Enter to close...")
        return

    print("[1/3] Checking Python...")
    if not check_python():
        input("\nPress Enter to close...")
        return

    print("\n[2/3] Checking dependencies...")
    if not check_pip():
        input("\nPress Enter to close...")
        return
    if not check_and_install_deps():
        input("\nPress Enter to close...")
        return

    print("\n[3/3] Building application...")
    success = run_build(variants)

    if success:
        built = build_outputs()
        for exe in built:
            print(f"\n  Build complete: {exe}")
            write_smartscreen_help(os.path.dirname(exe))
        if built:
            print(SMARTSCREEN_NOTICE)
        else:
            print("\n  Build reported success but no executable was found in dist.")
    else:
        print("\n  Build failed. Check the output above for errors.")

    input("\nPress Enter to close...")


if __name__ == "__main__":
    main()
