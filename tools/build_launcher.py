"""The dependency checks and the build spawn every build entry point shares.

``launch`` runs ``check_python``, ``check_and_install_deps`` and ``run_build``
for the variants it is handed, then names the folders that run added under
``dist``. ``launch_macos`` builds the same variants on the macOS runner and
brings each one's ``.app`` and ``.dmg`` back into ``dist``. The entry points at
the repository root carry no build logic of their own; each hands its variants
to ``launch`` or ``launch_macos``.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
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
MAC_BUILDER_NAMES = ("Qt_MAC_BUILD.py", "React_MAC_BUILD.py")
DMG_SUFFIX = ".dmg"

GH_EXE_NAME = "gh"
MACOS_WORKFLOW = "macos-build.yml"
MACOS_ARTIFACT = "acervator-macos"

# `gh help` documents exit 4 as authentication required; every other non-zero
# exit from `gh api` leaves the request unanswered.
GH_NOT_SIGNED_IN_EXIT = 4
GH_REACH_ENDPOINT = "rate_limit"

GH_CALL_SECONDS = 120
DOWNLOAD_SECONDS = 1800
RUN_APPEARS_SECONDS = 180
RUN_POLL_SECONDS = 15
RUN_CEILING_SECONDS = 3600
RUN_LIST_LIMIT = "30"
SECONDS_PER_MINUTE = 60

LIVE_RUN_STATES = frozenset(
    {"queued", "in_progress", "waiting", "requested", "pending"}
)

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


NOT_SIGNED_IN_NOTICE = """
------------------------------------------------------------
  YOU ARE NOT SIGNED IN TO GITHUB

  The Mac build runs on GitHub's macOS computers, so this
  needs you signed in.

  1. Open a terminal
  2. Run:  gh auth login
  3. Choose GitHub.com, then HTTPS, then log in with a browser
  4. Double-click this builder again
------------------------------------------------------------
"""

NO_ANSWER_NOTICE = """
------------------------------------------------------------
  GITHUB DID NOT ANSWER

  The Mac build runs on GitHub's macOS computers, so this
  needs a working internet connection.

  1. Check the connection
  2. Double-click this builder again
------------------------------------------------------------
"""

DISK_IMAGE_NOTICE = """
  On a Mac, open the .dmg. A .dmg keeps the file permissions
  a Mac needs; the .app folder beside it is downloaded as
  plain files and does not.
"""


class MacBuildError(RuntimeError):
    """Carries the one line ``launch_macos`` prints when a step cannot go on."""


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


def stamp_builder_dates(
    finished_at: float, names: tuple[str, ...] = BUILDER_NAMES
) -> list[str]:
    """Set each ``names`` mtime under ``PROJECT_ROOT`` to ``finished_at``.

    ``names`` defaults to ``BUILDER_NAMES``; ``launch_macos`` passes
    ``MAC_BUILDER_NAMES`` so a Mac build never moves a Windows builder's date.
    """
    stamped = []
    for name in names:
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


def gh_exe() -> str:
    """Return the absolute gh path ``shutil.which`` resolves, or ''."""
    return shutil.which(GH_EXE_NAME) or ""


def gh_output(
    argv: list[str], timeout: int = GH_CALL_SECONDS
) -> subprocess.CompletedProcess:
    """Run gh with ``argv`` from ``PROJECT_ROOT`` and capture what it printed."""
    return subprocess.run(
        [gh_exe(), *argv],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )


def gh_said(result: subprocess.CompletedProcess) -> str:
    """Return the text ``result`` carries on either stream, stripped."""
    return (result.stderr or result.stdout or "").strip()


def github_reach() -> tuple[int, str]:
    """Return the exit code and text ``GH_REACH_ENDPOINT`` answered gh with.

    A timeout answers 1 so the caller reads it as GitHub not answering.
    """
    try:
        result = gh_output(["api", GH_REACH_ENDPOINT])
    except subprocess.TimeoutExpired:
        return 1, f"gh api did not answer within {GH_CALL_SECONDS} seconds"
    return result.returncode, gh_said(result)


def current_branch() -> str:
    """Return the branch ``git rev-parse`` names for ``PROJECT_ROOT``, or ''."""
    git = shutil.which("git")
    if not git:
        return ""
    result = subprocess.run(
        [git, "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=GH_CALL_SECONDS,
    )
    named = result.stdout.strip()
    if result.returncode != 0 or named == "HEAD":
        return ""
    return named


def macos_runs(ref: str) -> list[dict]:
    """Return the ``MACOS_WORKFLOW`` runs gh lists for ``ref``, newest first."""
    result = gh_output(
        [
            "run",
            "list",
            "--workflow",
            MACOS_WORKFLOW,
            "--branch",
            ref,
            "--limit",
            RUN_LIST_LIMIT,
            "--json",
            "databaseId,status,conclusion,url",
        ]
    )
    if result.returncode != 0:
        raise MacBuildError(gh_said(result))
    return json.loads(result.stdout or "[]")


def live_macos_run(ref: str) -> dict | None:
    """Return the newest ``macos_runs`` entry on ``ref`` still in ``LIVE_RUN_STATES``."""
    for run in macos_runs(ref):
        if run.get("status") in LIVE_RUN_STATES:
            return run
    return None


def start_macos_run(ref: str) -> dict:
    """Start ``MACOS_WORKFLOW`` on ``ref`` and return the run gh then lists for it."""
    known = {run["databaseId"] for run in macos_runs(ref)}
    started = gh_output(["workflow", "run", MACOS_WORKFLOW, "--ref", ref])
    if started.returncode != 0:
        raise MacBuildError(gh_said(started))
    deadline = time.monotonic() + RUN_APPEARS_SECONDS
    while time.monotonic() < deadline:
        for run in macos_runs(ref):
            if run["databaseId"] not in known:
                return run
        time.sleep(RUN_POLL_SECONDS)
    raise MacBuildError(
        f"the run started on {ref} but gh listed no new run "
        f"within {RUN_APPEARS_SECONDS} seconds"
    )


def wait_for_run(run_id: int) -> str:
    """Print the elapsed time and status until ``run_id`` ends, returning its conclusion.

    Raises ``MacBuildError`` once the wait passes ``RUN_CEILING_SECONDS``.
    """
    started = time.monotonic()
    while True:
        elapsed = int(time.monotonic() - started)
        if elapsed > RUN_CEILING_SECONDS:
            raise MacBuildError(
                f"run {run_id} was still going after {RUN_CEILING_SECONDS} seconds"
            )
        result = gh_output(["run", "view", str(run_id), "--json", "status,conclusion"])
        if result.returncode != 0:
            raise MacBuildError(gh_said(result))
        seen = json.loads(result.stdout or "{}")
        status = str(seen.get("status") or "unknown")
        minutes, seconds = divmod(elapsed, SECONDS_PER_MINUTE)
        print(f"  [{minutes:02d}:{seconds:02d}] the Mac build is {status}", flush=True)
        if status not in LIVE_RUN_STATES:
            return str(seen.get("conclusion") or status)
        time.sleep(RUN_POLL_SECONDS)


def bundle_bytes(path: str) -> int:
    """Return the size of ``path``, summing every file under it when it is a folder."""
    if os.path.isfile(path):
        return os.path.getsize(path)
    total = 0
    for folder, _subfolders, files in os.walk(path):
        for name in files:
            found = os.path.join(folder, name)
            if os.path.isfile(found) and not os.path.islink(found):
                total += os.path.getsize(found)
    return total


def free_dist_path(name: str) -> str:
    """Return a ``dist_dir`` path for ``name``, adding -2 before its suffix when taken.

    Only ``APP_SUFFIX`` and ``DMG_SUFFIX`` count as the suffix, so the dots in a
    version keep their place, and nothing under ``dist_dir`` is replaced.
    """
    stem, suffix = name, ""
    for known in (APP_SUFFIX, DMG_SUFFIX):
        if name.endswith(known):
            stem, suffix = name[: -len(known)], known
            break
    candidate = os.path.join(dist_dir(), name)
    ordinal = 2
    while os.path.exists(candidate):
        candidate = os.path.join(dist_dir(), f"{stem}-{ordinal}{suffix}")
        ordinal += 1
    return candidate


def collect_run_artifact(run_id: int, variant: str) -> list[str]:
    """Move ``variant``'s ``APP_SUFFIX`` and ``DMG_SUFFIX`` items from ``run_id`` into dist.

    The whole ``MACOS_ARTIFACT`` downloads to a temporary folder first, so only
    the named ``variant`` reaches ``dist_dir``.
    """
    os.makedirs(dist_dir(), exist_ok=True)
    staging = tempfile.mkdtemp(prefix="acervator-macos-")
    try:
        got = gh_output(
            [
                "run",
                "download",
                str(run_id),
                "--name",
                MACOS_ARTIFACT,
                "--dir",
                staging,
            ],
            timeout=DOWNLOAD_SECONDS,
        )
        if got.returncode != 0:
            raise MacBuildError(gh_said(got))
        wanted = (f"-{variant}{APP_SUFFIX}", f"-{variant}{DMG_SUFFIX}")
        landed = []
        for name in sorted(os.listdir(staging)):
            if not name.endswith(wanted):
                continue
            destination = free_dist_path(name)
            shutil.move(os.path.join(staging, name), destination)
            landed.append(destination)
        if not landed:
            raise MacBuildError(
                f"run {run_id} carried no {variant} application or disk image"
            )
        return landed
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def launch_macos(variants: tuple[str, ...]) -> bool:
    """Build ``variants`` on the macOS runner and land each one's items in ``dist``.

    Returns False with ``NOT_SIGNED_IN_NOTICE`` or ``NO_ANSWER_NOTICE`` when gh
    cannot reach GitHub, and False with the reason when a step raises
    ``MacBuildError``.
    """
    try:
        os.chdir(PROJECT_ROOT)
    except OSError as exc:
        print(f"  NOTE: could not change directory to {PROJECT_ROOT}: {exc}")

    print(HEADER)
    print(f"  Surface: {', '.join(variants)}   Platform: macOS")

    print("\n[1/4] Checking GitHub...")
    if not gh_exe():
        print(f"\n  ERROR: {GH_EXE_NAME} not found on PATH.")
        print("  The Mac build runs on GitHub and needs the GitHub CLI.")
        print("  Install it from https://cli.github.com/")
        return False
    code, said = github_reach()
    if code == GH_NOT_SIGNED_IN_EXIT:
        print(NOT_SIGNED_IN_NOTICE)
        print(f"  gh said: {said}")
        return False
    if code != 0:
        print(NO_ANSWER_NOTICE)
        print(f"  gh said: {said}")
        return False
    print(f"  Signed in, and GitHub answered {GH_REACH_ENDPOINT}.")

    ref = current_branch()
    if not ref:
        print("\n  ERROR: this copy is on no named branch, so there is no")
        print("  branch for GitHub to build. Check out a branch and retry.")
        return False
    print(f"  Branch: {ref}")

    try:
        print("\n[2/4] Starting the Mac build...")
        run = live_macos_run(ref)
        if run is None:
            run = start_macos_run(ref)
            print(f"  Started run {run['databaseId']}")
        else:
            print(f"  Joined run {run['databaseId']}, already building")
        print(f"  Watch it at: {run['url']}")

        print("\n[3/4] Waiting. A Mac build takes about 13 minutes.")
        conclusion = wait_for_run(run["databaseId"])
        if conclusion != "success":
            print(f"\n  The Mac build ended as: {conclusion}")
            print(f"  Read what failed at: {run['url']}")
            return False

        print(f"\n[4/4] Bringing run {run['databaseId']} into {dist_dir()}...")
        landed = []
        for variant in variants:
            landed += collect_run_artifact(run["databaseId"], variant)
    except (MacBuildError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        print(f"\n  ERROR: {exc}")
        return False

    stamped = stamp_builder_dates(time.time(), MAC_BUILDER_NAMES)
    if stamped:
        print(f"\n  Build date set on: {', '.join(stamped)}")
    for path in landed:
        print(f"\n  Build complete: {path}")
        print(f"  Size: {bundle_bytes(path):,} bytes")
    print(f"\n  From run {run['databaseId']}: {run['url']}")
    print(DISK_IMAGE_NOTICE)
    print(GATEKEEPER_NOTICE)
    return True


__all__ = [
    "APP_SUFFIX",
    "BUILDER_NAMES",
    "CONSUMER",
    "DEFENDER_PROMPT_SECONDS",
    "DISK_IMAGE_NOTICE",
    "DMG_SUFFIX",
    "GATEKEEPER_NOTICE",
    "GH_NOT_SIGNED_IN_EXIT",
    "GH_REACH_ENDPOINT",
    "HEADER",
    "LIVE_RUN_STATES",
    "MACOS_ARTIFACT",
    "MACOS_BUILDER",
    "MACOS_WORKFLOW",
    "MAC_BUILDER_NAMES",
    "NOT_SIGNED_IN_NOTICE",
    "NO_ANSWER_NOTICE",
    "PROJECT_ROOT",
    "SMARTSCREEN_HELP",
    "SMARTSCREEN_NOTICE",
    "WINDOWS_BUILDER",
    "MacBuildError",
    "add_defender_exclusion",
    "application_path",
    "bash_exe",
    "build_argv",
    "build_folder_names",
    "build_outputs",
    "builder_name",
    "bundle_bytes",
    "check_and_install_deps",
    "check_pip",
    "check_python",
    "collect_run_artifact",
    "current_branch",
    "disk_image_names",
    "disk_images",
    "dist_dir",
    "free_dist_path",
    "gh_exe",
    "gh_output",
    "gh_said",
    "github_reach",
    "install_package",
    "is_macos",
    "is_windows",
    "launch",
    "launch_macos",
    "live_macos_run",
    "macos_runs",
    "powershell_exe",
    "required_python",
    "run_build",
    "stamp_builder_dates",
    "start_macos_run",
    "wait_for_run",
    "write_smartscreen_help",
]
