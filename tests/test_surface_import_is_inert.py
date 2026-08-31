"""Every main-tab surface must touch nothing in the world while it imports.

A surface that builds its state during import reads the clock and the
operator's runtime tree before a caller can redirect either. Each surface
is imported in its own fresh process with the clock and the file opener
counted.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SURFACE_DIR = REPO_ROOT / "src" / "gui" / "main_tabs"
SURFACE_PACKAGE = "src.gui.main_tabs"
SURFACE_NAMES = sorted(path.stem for path in SURFACE_DIR.glob("*_surface.py"))

IMPORT_PROBE = """
import builtins
import datetime
import importlib
import json
import os
import tempfile
import time
from pathlib import Path, PurePath

home = Path.home()
watched = [os.path.normcase(str(home / ".acervator")),
           os.path.normcase(str(home / ".acervator_logs"))]

clock_reads = []
opened = []
real_time = time.time
real_monotonic = time.monotonic
real_datetime = datetime.datetime
real_open = builtins.open
real_os_open = os.open


def watched_path(target):
    try:
        name = os.path.normcase(os.path.abspath(os.fspath(target)))
    except TypeError:
        return None
    for root in watched:
        if PurePath(name) == PurePath(root) or PurePath(name).is_relative_to(root):
            return name
    return None


def counted_time():
    clock_reads.append("time")
    return real_time()


def counted_monotonic():
    clock_reads.append("monotonic")
    return real_monotonic()


def counted_open(file, *args, **kwargs):
    hit = watched_path(file)
    if hit is not None:
        opened.append(hit)
    return real_open(file, *args, **kwargs)


def counted_os_open(path, *args, **kwargs):
    hit = watched_path(path)
    if hit is not None:
        opened.append(hit)
    return real_os_open(path, *args, **kwargs)


class CountedDatetime(real_datetime):
    @classmethod
    def now(cls, tz=None):
        clock_reads.append("datetime.now")
        return real_datetime.now(tz)


time.time = counted_time
time.monotonic = counted_monotonic
datetime.datetime = CountedDatetime
builtins.open = counted_open
os.open = counted_os_open

failed = ""
try:
    importlib.import_module(TARGET_MODULE)
except BaseException as error:
    failed = type(error).__name__

at_import_clock = list(clock_reads)
at_import_opened = list(opened)

clock_reads.clear()
counted_time()
counted_monotonic()
CountedDatetime.now()
control_clock = len(clock_reads)

control_root = Path(tempfile.mkdtemp(prefix="surface-import-probe-"))
watched.append(os.path.normcase(str(control_root)))
opened.clear()
with counted_open(control_root / "control", "w", encoding="utf-8") as handle:
    handle.write("control")
control_opened = len(opened)

builtins.open = real_open
os.remove(control_root / "control")
os.rmdir(control_root)

print(json.dumps({"failed": failed,
                  "at_import_clock": at_import_clock,
                  "at_import_opened": at_import_opened,
                  "control_clock": control_clock,
                  "control_opened": control_opened}))
"""


def run_import_probe(module_name):
    """Import one module in a fresh process and return what the probe saw."""
    target = json.dumps(f"{SURFACE_PACKAGE}.{module_name}")
    source = f"TARGET_MODULE = {target}" + IMPORT_PROBE
    done = subprocess.run(
        [sys.executable, "-"],
        input=source.encode("utf-8"),
        capture_output=True,
        cwd=str(REPO_ROOT),
        timeout=300,
        check=False,
    )
    assert done.returncode == 0, done.stderr.decode()
    return json.loads(done.stdout.decode().splitlines()[-1])


def test_the_folder_holds_surfaces_to_check():
    """The surface list came back empty, so every other check here is void."""
    assert SURFACE_NAMES, str(SURFACE_DIR)


@pytest.mark.parametrize("surface_name", SURFACE_NAMES)
def test_importing_a_surface_reads_no_clock_and_no_runtime_file(surface_name):
    """This surface built its state at import instead of on the first request.

    The probe carries its own control: it calls the clock and opens a file
    under a watched temporary folder after the import, so a zero from a
    dead counter cannot read as a pass.
    """
    seen = run_import_probe(surface_name)
    assert seen["control_clock"] == 3, seen
    assert seen["control_opened"] == 1, seen
    assert seen["failed"] == "", seen
    assert seen["at_import_clock"] == [], seen
    assert seen["at_import_opened"] == [], seen
