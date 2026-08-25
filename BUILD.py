"""
BUILD - Acervator Build Launcher
Double-click this file to build the application.
Automatically detects and installs all required dependencies.
"""

import subprocess
import sys
import os
import importlib.util

try:
    _script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(_script_dir)
except Exception:
    pass  # Fall through — run_build uses absolute paths anyway

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

# Maps: (spec_name_to_find, pip_install_name)
# spec_name is what importlib.util.find_spec() looks for
# pip_name is what pip install uses
REQUIRED_PACKAGES = [
    ("PyInstaller", "pyinstaller"),
    ("PySide6", "PySide6"),
    ("ccxt", "ccxt"),
    ("cryptography", "cryptography"),
    ("keyring", "keyring"),
    ("pandas", "pandas"),
    ("numpy", "numpy"),
    ("ta", "ta"),
    ("tomli_w", "tomli_w"),
    ("aiohttp", "aiohttp"),
    ("certifi", "certifi"),
    ("psutil", "psutil"),  # Nuclear v4 MR — system load sampling
]


def check_python():
    """Verify Python version meets minimum requirements."""
    print(f"  Python: {sys.version}")
    if sys.version_info < (3, 10):
        print("\n  ERROR: Python 3.10 or higher is required.")
        print("  Download from https://www.python.org/downloads/")
        return False
    print(f"  Path:   {sys.executable}")
    return True


def check_pip():
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
    except Exception as exc:
        print(f"  ERROR: Could not install pip: {exc}")
        print("  Manual fix: python -m ensurepip --upgrade")
        return False


def is_installed(spec_name):
    """Check if a package is installed WITHOUT importing it."""
    try:
        return importlib.util.find_spec(spec_name) is not None
    except (ModuleNotFoundError, ValueError):
        return False


def install_package(pip_name):
    """Install a single package via pip."""
    cmd = [sys.executable, "-m", "pip", "install", pip_name, "--quiet"]
    if sys.version_info >= (3, 12):
        cmd.append("--break-system-packages")
    return subprocess.run(cmd, capture_output=True).returncode == 0


def check_and_install_deps():
    """Check each required package; install if missing."""
    missing = []
    installed = []

    for spec_name, pip_name in REQUIRED_PACKAGES:
        if is_installed(spec_name):
            installed.append(spec_name)
        else:
            missing.append((spec_name, pip_name))

    if installed:
        print(f"  Installed: {', '.join(installed)}")

    if not missing:
        print("  All dependencies satisfied.")
        return True

    print(f"\n  Missing: {', '.join(s for s, _ in missing)}")
    print("  Installing...\n")

    failed = []
    for spec_name, pip_name in missing:
        print(f"    Installing {pip_name}...", end=" ", flush=True)
        if install_package(pip_name):
            print("OK")
        else:
            print("FAILED")
            failed.append(pip_name)

    if failed:
        print(f"\n  ERROR: Failed to install: {', '.join(failed)}")
        print(f"  Manual fix: pip install {' '.join(failed)}")
        return False

    print("\n  All dependencies installed.")
    return True


def run_build():
    """Execute the PowerShell build script."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    ps1_path = os.path.join(script_dir, "build_windows.ps1")

    if not os.path.exists(ps1_path):
        print(f"\n  ERROR: build_windows.ps1 not found at:\n  {ps1_path}")
        print("  Make sure BUILD.py and build_windows.ps1 are in the same folder.")
        return False

    print(f"\n  Script: {ps1_path}")
    print("  Starting build...\n")
    print("=" * 60)

    # Use absolute path and set working directory explicitly
    result = subprocess.run(
        ["powershell", "-ExecutionPolicy", "Bypass", "-File", ps1_path],
        cwd=script_dir,
    )
    print("=" * 60)

    # Try to add Defender exclusion (requires admin)
    exe_path = os.path.join("dist", "Acervator")
    if os.path.isdir(exe_path):
        print("\n  Adding Windows Defender exclusion...")
        exc_result = subprocess.run(
            [
                "powershell",
                "-Command",
                f"Start-Process powershell -Verb RunAs -Wait -ArgumentList "
                f"'-Command Add-MpPreference -ExclusionPath \"{os.path.abspath(exe_path)}\"'",
            ],
            capture_output=True,
        )
        if exc_result.returncode == 0:
            print("  Defender exclusion added.")
        else:
            print("  Defender exclusion skipped (admin prompt declined).")

    return result.returncode == 0


def main():
    print(HEADER)

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
    success = run_build()

    if success:
        exe = os.path.join("dist", "Acervator", "Acervator.exe")
        if os.path.exists(exe):
            print(f"\n  Build complete: {os.path.abspath(exe)}")

            # Create help file next to exe
            help_path = os.path.join("dist", "Acervator", "IF_BLOCKED_READ_THIS.txt")
            try:
                with open(help_path, "w") as f:
                    f.write(SMARTSCREEN_HELP)
                print(f"  Help file: {os.path.abspath(help_path)}")
            except Exception:
                pass

            print(SMARTSCREEN_NOTICE)
    else:
        print("\n  Build failed. Check the output above for errors.")

    input("\nPress Enter to close...")


if __name__ == "__main__":
    main()
