"""The dependency checks and the build spawn every build entry point shares.

``launch`` runs ``check_python``, ``check_and_install_deps`` and ``run_build``
for the variants it is handed, then names the folders that run added under
``dist``. The entry points at the repository root carry no build logic of
their own; each hands its variants to ``launch``.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time

# Every argv below runs `sys.executable` or a `shutil.which` result, so no
# bare program name is resolved through PATH at build time.
# ruff: noqa: S603

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST_DIRNAME = "dist"
WINDOWS_BUILDER = "build_windows.ps1"
MACOS_BUILDER = "build_mac.sh"
APP_SUFFIX = ".app"
SMARTSCREEN_HELP_NAME = "IF_BLOCKED_READ_THIS.txt"
BUILDER_NAMES = ("Qt_BUILD.py", "React_BUILD.py")

# Selects the core dependency set plus the `build` and `report` extras, which
# is what a PyInstaller host installs.
CONSUMER = "build"

# The administrator prompt `add_defender_exclusion` raises waits for a click.
DEFENDER_PROMPT_SECONDS = 120

_PYTHON_FLOOR = re.compile(r">=\s*(\d+)\.(\d+)")

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

GATEKEEPER_NOTICE = """
------------------------------------------------------------
  IF macOS REFUSES TO OPEN THE APP:

  The bundle carries no Apple Developer signature, so
  Gatekeeper blocks a double-click the first time.

  1. Right-click (or Control-click) the .app
  2. Choose Open
  3. Choose Open again in the dialog

  That is once per build. Later launches open normally.
------------------------------------------------------------
"""


def required_python() -> tuple[int, int]:
    """Return the ``requires-python`` lower bound pyproject.toml states.

    A source stating no ``>=`` bound raises ``DependencySourceError``.
    """
    from tools.deps import DependencySourceError, load_project

    declared = str(load_project().get("requires-python", ""))
    bound = _PYTHON_FLOOR.search(declared)
    if bound is None:
        raise DependencySourceError(
            f"pyproject.toml states no requires-python lower bound: {declared!r}"
        )
    return int(bound.group(1)), int(bound.group(2))


def check_python() -> bool:
    """Report whether the running interpreter meets ``required_python``."""
    from tools.deps import DependencySourceError

    print(f"  Python: {sys.version}")
    try:
        floor = required_python()
    except DependencySourceError as exc:
        print(f"\n  ERROR: {exc}")
        print("  pyproject.toml is the only interpreter source. Restore it.")
        return False
    if sys.version_info < floor:
        print(f"\n  ERROR: Python {floor[0]}.{floor[1]} or higher is required.")
        print("  Download from https://www.python.org/downloads/")
        return False
    print(f"  Path:   {sys.executable}")
    return True


def check_pip() -> bool:
    """Ensure pip is available, installing it through ensurepip when it is not."""
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

    ``tools.deps`` raises when pyproject.toml is absent, has no ``[project]``
    table, or states an empty dependency list, and this function then refuses.
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


def is_macos() -> bool:
    """Report whether ``sys.platform`` is darwin."""
    return sys.platform == "darwin"


def is_windows() -> bool:
    """Report whether ``sys.platform`` starts with win."""
    return sys.platform.startswith("win")


def builder_name() -> str:
    """Return ``MACOS_BUILDER`` or ``WINDOWS_BUILDER`` for this platform, else ''."""
    if is_macos():
        return MACOS_BUILDER
    if is_windows():
        return WINDOWS_BUILDER
    return ""


def powershell_exe() -> str:
    """Return the absolute PowerShell path ``shutil.which`` resolves, or ''."""
    return shutil.which("powershell") or ""


def bash_exe() -> str:
    """Return the absolute bash path ``shutil.which`` resolves, or ''."""
    return shutil.which("bash") or ""


def build_argv(script: str, variants: tuple[str, ...]) -> list[str]:
    """Return the argv running ``script`` for ``variants``, or [] with no interpreter.

    ``MACOS_BUILDER`` takes one ``--variant`` per name and ``--dmg``;
    ``WINDOWS_BUILDER`` takes the names comma-joined behind one ``-Variant``.
    """
    if is_macos():
        bash = bash_exe()
        if not bash:
            return []
        argv = [bash, script, "--dmg"]
        for variant in variants:
            argv += ["--variant", variant]
        return argv
    powershell = powershell_exe()
    if not powershell:
        return []
    return [
        powershell,
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        script,
        "-Variant",
        ",".join(variants),
    ]


def application_path(root: str, entry: str) -> str:
    """Return where a build folder named ``entry`` under ``root`` holds its application.

    A name that cannot hold one for this platform answers ''.
    """
    if is_macos():
        if not entry.endswith(APP_SUFFIX):
            return ""
        return os.path.join(root, entry)
    return os.path.join(root, entry, f"{entry}.exe")


def dist_dir() -> str:
    """Return the absolute ``DIST_DIRNAME`` path under ``PROJECT_ROOT``."""
    return os.path.join(PROJECT_ROOT, DIST_DIRNAME)


def build_folder_names() -> set[str]:
    """Return the names of the folders present under ``dist_dir`` right now."""
    root = dist_dir()
    if not os.path.isdir(root):
        return set()
    return {
        name for name in os.listdir(root) if os.path.isdir(os.path.join(root, name))
    }


def build_outputs(skip: frozenset[str] = frozenset()) -> list[str]:
    """Return the ``application_path`` results under ``dist_dir`` outside ``skip``.

    Each build claims a folder of its own, so passing the ``build_folder_names``
    taken before a run leaves only what that run produced, newest first.
    """
    root = dist_dir()
    if not os.path.isdir(root):
        return []
    found = []
    for name in os.listdir(root):
        if name in skip:
            continue
        application = application_path(root, name)
        if application and os.path.exists(application):
            found.append(application)
    found.sort(key=os.path.getmtime, reverse=True)
    return found


def disk_image_names() -> set[str]:
    """Return the .dmg names present directly under ``dist_dir`` right now."""
    root = dist_dir()
    if not os.path.isdir(root):
        return set()
    return {name for name in os.listdir(root) if name.endswith(".dmg")}


def disk_images(skip: frozenset[str] = frozenset()) -> list[str]:
    """Return the .dmg paths under ``dist_dir`` whose name is outside ``skip``."""
    root = dist_dir()
    if not os.path.isdir(root):
        return []
    return sorted(
        os.path.join(root, name)
        for name in os.listdir(root)
        if name.endswith(".dmg") and name not in skip
    )


def stamp_builder_dates(finished_at: float) -> list[str]:
    """Set both ``BUILDER_NAMES`` mtimes under ``PROJECT_ROOT`` to ``finished_at``."""
    stamped = []
    for name in BUILDER_NAMES:
        path = os.path.join(PROJECT_ROOT, name)
        if not os.path.exists(path):
            print(f"  NOTE: {name} is not under {PROJECT_ROOT}; its date is unchanged.")
            continue
        try:
            # os.utime rewrites the two times only, so the tracked bytes never move.
            os.utime(path, (finished_at, finished_at))
        except OSError as exc:
            print(f"  NOTE: {name} date not set: {exc}")
            continue
        stamped.append(name)
    return stamped


def write_smartscreen_help(folder: str) -> None:
    """Write the "if Windows blocks this" note beside a built executable."""
    help_path = os.path.join(folder, SMARTSCREEN_HELP_NAME)
    try:
        with open(help_path, "w", encoding="utf-8") as handle:
            handle.write(SMARTSCREEN_HELP)
        print(f"  Help file: {help_path}")
    except OSError as exc:
        print(f"  NOTE: help file not written: {exc}")


def add_defender_exclusion(powershell: str) -> None:
    """Ask Windows Defender to exclude the whole ``dist_dir``, which builds add to.

    ``RunAs`` raises an administrator prompt, so the wait is capped at
    ``DEFENDER_PROMPT_SECONDS`` and an unanswered prompt reports as skipped.
    """
    root = dist_dir()
    if not os.path.isdir(root):
        return
    print("\n  Adding Windows Defender exclusion...")
    quoted = f'"{root}"'
    inner = (
        f'Start-Process "{powershell}" -Verb RunAs -Wait '
        f"-ArgumentList '-Command Add-MpPreference "
        f"-ExclusionPath {quoted}'"
    )
    try:
        exclusion = subprocess.run(
            [powershell, "-Command", inner],
            capture_output=True,
            check=False,
            timeout=DEFENDER_PROMPT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        print(
            f"  Defender exclusion skipped (no answer in "
            f"{DEFENDER_PROMPT_SECONDS}s)."
        )
        return
    if exclusion.returncode == 0:
        print("  Defender exclusion added.")
    else:
        print("  Defender exclusion skipped (admin prompt declined).")


def run_build(variants: tuple[str, ...]) -> bool:
    """Execute this platform's ``builder_name`` script for ``variants``."""
    script_name = builder_name()
    if not script_name:
        print(f"\n  ERROR: no build script is known for platform {sys.platform!r}.")
        print(f"  {WINDOWS_BUILDER} builds on Windows and {MACOS_BUILDER} on macOS.")
        return False

    script_path = os.path.join(PROJECT_ROOT, script_name)
    if not os.path.exists(script_path):
        print(f"\n  ERROR: {script_name} not found at:\n  {script_path}")
        print(f"  Make sure the build entry point and {script_name} are")
        print("  in the same folder.")
        return False

    argv = build_argv(script_path, variants)
    if not argv:
        interpreter = "bash" if is_macos() else "powershell"
        print(f"\n  ERROR: {interpreter} not found on PATH.")
        print(f"  This build runs {script_name} and needs it.")
        return False

    print(f"\n  Script: {script_path}")
    print(f"  Variants: {', '.join(variants)}")
    print("  Starting build...\n")
    print("=" * 60)

    result = subprocess.run(argv, cwd=PROJECT_ROOT, check=False)
    print("=" * 60)

    if is_windows():
        add_defender_exclusion(argv[0])

    return result.returncode == 0


def launch(variants: tuple[str, ...]) -> bool:
    """Build ``variants`` and report the executables the run produced.

    Returns True when ``run_build`` succeeded and left at least one new folder
    under ``dist_dir``.
    """
    try:
        os.chdir(PROJECT_ROOT)
    except OSError as exc:
        print(f"  NOTE: could not change directory to {PROJECT_ROOT}: {exc}")

    print(HEADER)
    print(f"  Surface: {', '.join(variants)}")

    print("\n[1/3] Checking Python...")
    if not check_python():
        return False

    print("\n[2/3] Checking dependencies...")
    if not check_pip():
        return False
    if not check_and_install_deps():
        return False

    print("\n[3/3] Building application...")
    before = build_folder_names()
    images_before = disk_image_names()
    if not run_build(variants):
        print("\n  Build failed. Check the output above for errors.")
        return False

    built = build_outputs(skip=frozenset(before))
    if not built:
        print(f"\n  Build reported success but added no folder under {dist_dir()}.")
        return False

    stamped = stamp_builder_dates(time.time())
    if stamped:
        print(f"\n  Build date set on: {', '.join(stamped)}")

    for application in built:
        print(f"\n  Build complete: {application}")
        if is_windows():
            write_smartscreen_help(os.path.dirname(application))
    if is_macos():
        for image in disk_images(skip=frozenset(images_before)):
            print(f"  Disk image: {image}")
        print(GATEKEEPER_NOTICE)
    else:
        print(SMARTSCREEN_NOTICE)
    return True


__all__ = [
    "APP_SUFFIX",
    "BUILDER_NAMES",
    "CONSUMER",
    "DEFENDER_PROMPT_SECONDS",
    "GATEKEEPER_NOTICE",
    "HEADER",
    "MACOS_BUILDER",
    "PROJECT_ROOT",
    "SMARTSCREEN_HELP",
    "SMARTSCREEN_NOTICE",
    "WINDOWS_BUILDER",
    "add_defender_exclusion",
    "application_path",
    "bash_exe",
    "build_argv",
    "build_folder_names",
    "build_outputs",
    "builder_name",
    "check_and_install_deps",
    "check_pip",
    "check_python",
    "disk_image_names",
    "disk_images",
    "dist_dir",
    "install_package",
    "is_macos",
    "is_windows",
    "launch",
    "powershell_exe",
    "required_python",
    "run_build",
    "stamp_builder_dates",
    "write_smartscreen_help",
]
