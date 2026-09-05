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
