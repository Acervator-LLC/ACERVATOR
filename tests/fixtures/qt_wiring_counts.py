"""Runtime counters for what a Qt screen wires, waits on and subscribes to.

``connections_watched``, ``timers_watched`` and ``bus_subscriptions_watched``
record what happens while a widget is built. ``qt_free`` imports a module in
a child process with ``PySide6`` refused at the meta path, which catches a
transitive import as well as a direct one.
"""

from __future__ import annotations

import contextlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

_BLOCK_QT = (
    "import sys\n"
    "import importlib.abc\n"
    "class _Refuse(importlib.abc.MetaPathFinder):\n"
    "    def find_spec(self, name, path=None, target=None):\n"
    "        if name.split('.')[0] in ('PySide6', 'shiboken6'):\n"
    "            raise ImportError('Qt blocked')\n"
    "        return None\n"
    "sys.meta_path.insert(0, _Refuse())\n"
)


def connections(build):
    """Return ``(count, built)`` for the signal connections ``build`` makes."""
    with connections_watched() as made:
        built = build()
    return len(made), built


def timer_starts(build):
    """Return ``(count, built)`` for the timers ``build`` builds or starts."""
    with timers_watched() as seen:
        built = build()
    return len(seen), built


def bus_subscriptions(build):
    """Return ``(count, built)`` for the bus topics ``build`` subscribes to."""
    with bus_subscriptions_watched() as taken:
        built = build()
    return len(taken), built


@contextlib.contextmanager
def connections_watched():
    """One entry per signal connection made inside the block."""
    from PySide6.QtCore import SignalInstance

    made: list = []
    with pytest.MonkeyPatch.context() as patch:
        real = SignalInstance.connect

        def watched(self, *args, **kwargs):
            made.append(str(self))
            return real(self, *args, **kwargs)

        patch.setattr(SignalInstance, "connect", watched)
        yield made


def caller_in_src():
    """The repository file nearest the call that reached this, or ``""``."""
    import traceback

    source = REPO_ROOT / "src"
    for frame in reversed(traceback.extract_stack()):
        found = Path(frame.filename).resolve()
        if found.is_relative_to(source):
            return found.relative_to(REPO_ROOT).as_posix()
    return ""


@contextlib.contextmanager
def connection_origins():
    """The source file behind every signal connection made in the block."""
    from PySide6.QtCore import SignalInstance

    made: list = []
    with pytest.MonkeyPatch.context() as patch:
        real = SignalInstance.connect

        def watched(self, *args, **kwargs):
            made.append(caller_in_src())
            return real(self, *args, **kwargs)

        patch.setattr(SignalInstance, "connect", watched)
        yield made


@contextlib.contextmanager
def connection_targets():
    """The name of the slot behind every connection made in the block."""
    from PySide6.QtCore import SignalInstance

    made: list = []
    with pytest.MonkeyPatch.context() as patch:
        real = SignalInstance.connect

        def watched(self, *args, **kwargs):
            slot = args[0] if args else None
            made.append(getattr(slot, "__qualname__", type(slot).__name__))
            return real(self, *args, **kwargs)

        patch.setattr(SignalInstance, "connect", watched)
        yield made


@contextlib.contextmanager
def timers_watched():
    """One entry per timer built or started inside the block."""
    from PySide6.QtCore import QObject, QTimer

    seen: list = []
    with pytest.MonkeyPatch.context() as patch:
        built = QTimer.__init__
        start = QTimer.start
        single = QTimer.singleShot
        interval = QObject.startTimer

        def watch_built(self, *args, **kwargs):
            seen.append(("QTimer()", args))
            return built(self, *args, **kwargs)

        def watch_start(self, *args, **kwargs):
            seen.append(("QTimer.start", args))
            return start(self, *args, **kwargs)

        def watch_single(*args, **kwargs):
            seen.append(("singleShot", args))
            return single(*args, **kwargs)

        def watch_interval(self, *args, **kwargs):
            seen.append(("startTimer", args))
            return interval(self, *args, **kwargs)

        patch.setattr(QTimer, "__init__", watch_built)
        patch.setattr(QTimer, "start", watch_start)
        patch.setattr(QTimer, "singleShot", watch_single)
        patch.setattr(QObject, "startTimer", watch_interval)
        yield seen


@contextlib.contextmanager
def bus_subscriptions_watched():
    """One entry per topic subscribed on the process bus inside the block."""
    from src.core.event_bus import EventBus

    taken: list = []
    with pytest.MonkeyPatch.context() as patch:
        real = EventBus.subscribe

        def watched(self, topic, *args, **kwargs):
            taken.append(topic)
            return real(self, topic, *args, **kwargs)

        patch.setattr(EventBus, "subscribe", watched)
        yield taken


def run_probe(source):
    """Run one probe script in a fresh process and return what it printed."""
    done = subprocess.run(
        [sys.executable, "-"],
        input=source.encode("utf-8"),
        capture_output=True,
        cwd=str(REPO_ROOT),
        timeout=300,
        check=False,
    )
    assert done.returncode == 0, done.stderr.decode("utf-8", "replace")
    return json.loads(done.stdout.decode("utf-8").splitlines()[-1])


def qt_free(module, attribute=None):
    """Import ``module`` with Qt refused, and report what loaded.

    ``attribute`` names one member read after the import, so the probe
    reports the failure of a module whose contents need Qt.
    """
    read = "    getattr(m, %r)\n" % attribute if attribute else "    pass\n"
    probe = (
        _BLOCK_QT + "import importlib, json, sys\n"
        "out = {}\n"
        "try:\n"
        "    m = importlib.import_module(%r)\n" % module
        + read
        + "    out['imported'] = True\n"
        "except BaseException as exc:\n"
        "    out['imported'] = False\n"
        "    out['error'] = type(exc).__name__\n"
        "    out['detail'] = str(exc)\n"
        "out['qt'] = sorted(\n"
        "    name for name in sys.modules\n"
        "    if name.split('.')[0] in ('PySide6', 'shiboken6')\n"
        ")\n"
        "print(json.dumps(out))\n"
    )
    return run_probe(probe)


def module_pulls(module):
    """Import ``module`` alone and report the ``src`` modules it pulled in."""
    probe = (
        "import importlib, json, os, sys\n"
        "os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')\n"
        "importlib.import_module(%r)\n" % module + "print(json.dumps(sorted(\n"
        "    name for name in sys.modules if name.startswith('src.'))))\n"
    )
    return run_probe(probe)


def io_watched(module, drive=""):
    """Import ``module`` and run ``drive`` with file and socket calls trapped.

    ``touched`` names every trap that fired, so an empty list is a run
    that reached no file, socket, address or browser.
    """
    probe = (
        "import builtins, importlib, json, pathlib, socket, ssl\n"
        "import urllib.request, webbrowser\n"
        "touched = []\n"
        "def trap(name, real):\n"
        "    def fire(*a, **k):\n"
        "        touched.append(name)\n"
        "        return real(*a, **k)\n"
        "    return fire\n"
        "builtins.open = trap('open', builtins.open)\n"
        "socket.socket = trap('socket', socket.socket)\n"
        "socket.create_connection = trap('create_connection',"
        " socket.create_connection)\n"
        "ssl.create_default_context = trap('ssl', ssl.create_default_context)\n"
        "urllib.request.urlopen = trap('urlopen', urllib.request.urlopen)\n"
        "webbrowser.open = trap('webbrowser', webbrowser.open)\n"
        "pathlib.Path.read_text = trap('read_text', pathlib.Path.read_text)\n"
        "pathlib.Path.write_text = trap('write_text', pathlib.Path.write_text)\n"
        "pathlib.Path.read_bytes = trap('read_bytes', pathlib.Path.read_bytes)\n"
        "pathlib.Path.write_bytes = trap('write_bytes', pathlib.Path.write_bytes)\n"
        "pathlib.Path.mkdir = trap('mkdir', pathlib.Path.mkdir)\n"
        "m = importlib.import_module(%r)\n" % module
        + drive
        + "print(json.dumps({'touched': sorted(set(touched))}))\n"
    )
    return run_probe(probe)


def package_walk_loads(package, skip=()):
    """Import every module under ``package`` except ``skip``, and report.

    ``loaded`` lists the modules that ended up in ``sys.modules``, so a
    name absent from it is one nothing under ``package`` reaches.
    """
    probe = (
        "import importlib, json, os, pkgutil, sys\n"
        "os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')\n"
        "package = importlib.import_module(%r)\n" % package
        + "skip = set(%r)\n" % (tuple(skip),)
        + "walked = 0\n"
        "for info in pkgutil.walk_packages(package.__path__, package.__name__ + '.'):\n"
        "    if info.name in skip:\n"
        "        continue\n"
        "    try:\n"
        "        importlib.import_module(info.name)\n"
        "    except BaseException:\n"
        "        continue\n"
        "    walked += 1\n"
        "print(json.dumps({'walked': walked, 'loaded': sorted(\n"
        "    name for name in sys.modules if name.startswith('src.'))}))\n"
    )
    return run_probe(probe)
