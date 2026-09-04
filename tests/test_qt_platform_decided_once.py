"""The Qt platform plugin is chosen by the root conftest and by nothing else.

``test_the_root_conftest_alone_decides_the_platform`` is the positive
control for the tests that assert an absence: it drives the same probe
and reports a platform, so an empty answer from a helper is a fact
about the helper rather than about a blind instrument.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from tests.fixtures.qt_platform import (
    DEFAULT_QT_PLATFORM,
    QT_PLATFORM_ENV,
    resolve_qt_platform,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

IMPORT_CONFTEST = """
import json, os, sys
sys.path.insert(0, os.getcwd())
import tests.conftest
print(json.dumps({"platform": os.environ.get("QT_QPA_PLATFORM")}))
"""

IMPORT_QT_PLATFORM = """
import json, os, sys
sys.path.insert(0, os.getcwd())
import tests.fixtures.qt_platform
print(json.dumps({"platform": os.environ.get("QT_QPA_PLATFORM")}))
"""

IMPORT_HOST_FONTS = """
import json, os, sys
sys.path.insert(0, os.getcwd())
import tests.fixtures.host_fonts
print(json.dumps({"platform": os.environ.get("QT_QPA_PLATFORM")}))
"""

IMPORT_QT_PIXEL = """
import json, os, sys
sys.path.insert(0, os.getcwd())
import tests.qt_pixel
print(json.dumps({"platform": os.environ.get("QT_QPA_PLATFORM")}))
"""


def platform_after_importing(script: str) -> str | None:
    """Run `script` in a process that names no platform and report the one it ends with.

    The child starts with ``QT_QPA_PLATFORM`` removed, so any value it
    reports was written by the module the script imported.
    """
    child = dict(os.environ)
    child.pop(QT_PLATFORM_ENV, None)
    done = subprocess.run(
        [sys.executable, "-"],
        input=script.encode("utf-8"),
        capture_output=True,
        cwd=str(REPO_ROOT),
        timeout=300,
        check=False,
        env=child,
    )
    assert done.returncode == 0, "the probe process failed:\n%s" % done.stderr.decode(
        "utf-8", "replace"
    )
    return json.loads(done.stdout.decode("utf-8").splitlines()[-1])["platform"]


def test_a_run_that_names_no_platform_gets_the_offscreen_plugin():
    assert resolve_qt_platform(None) == DEFAULT_QT_PLATFORM
    assert resolve_qt_platform("") == DEFAULT_QT_PLATFORM
    assert resolve_qt_platform("   ") == DEFAULT_QT_PLATFORM


def test_a_run_that_names_a_platform_keeps_the_one_it_named():
    assert resolve_qt_platform("xcb") == "xcb"
    assert resolve_qt_platform("  windows  ") == "windows"


def test_the_root_conftest_alone_decides_the_platform():
    chosen = platform_after_importing(IMPORT_CONFTEST)
    assert chosen == DEFAULT_QT_PLATFORM, (
        "importing the root conftest must settle the platform with no test "
        "module collected; it reported %r" % chosen
    )


def test_importing_the_platform_fixture_decides_nothing():
    chosen = platform_after_importing(IMPORT_QT_PLATFORM)
    assert chosen is None, (
        "the platform fixture must be called, never act on import; importing "
        "it set %s=%r" % (QT_PLATFORM_ENV, chosen)
    )


def test_importing_the_font_fixture_decides_nothing():
    chosen = platform_after_importing(IMPORT_HOST_FONTS)
    assert chosen is None, (
        "the font fixture must read the platform, never choose it; importing "
        "it set %s=%r" % (QT_PLATFORM_ENV, chosen)
    )


def test_importing_the_pixel_helper_decides_nothing():
    chosen = platform_after_importing(IMPORT_QT_PIXEL)
    assert chosen is None, (
        "the pixel helper must read the platform, never choose it; importing "
        "it set %s=%r" % (QT_PLATFORM_ENV, chosen)
    )


def test_the_running_application_paints_on_the_resolved_platform():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    assert (
        app.platformName() == os.environ[QT_PLATFORM_ENV]
    ), "the process is painting on %r while the run resolved %r" % (
        app.platformName(),
        os.environ.get(QT_PLATFORM_ENV),
    )
